"""
CDC / Retention 单元与集成测试（V4.4 §5-6、§15.3、§15.5）

依赖约定：
- 需要 conftest.py 提供 `db` fixture，返回一个 asyncpg.Connection。
  建议由 asyncpg.Pool 获取（pool-backed），这样 test_version_monotonic 的
  并发路径（asyncio.gather + pool.acquire）才会真正生效。
- 测试直接操作数据库，不 mock；每个测试独立运行、自清理。
- 使用高位测试 ID / 版本区间，避免与业务数据或版本计数器冲突。
"""

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pytest
from asyncpg import Connection

from backend.services.cdc_writer import (
    cdc_transaction,
    determine_action,
    next_version,
    write_sync_change,
)
from backend.services.retention_cleaner import (
    check_cursor_valid,
    clean_expired_logs,
    get_retention_floor,
)

pytestmark = pytest.mark.asyncio

# 高位测试常量：避免与业务数据 / 版本计数器冲突
LIVE_ID_BASE = 2_000_000
VERSION_BASE = 910_000_000
VERSION_END = VERSION_BASE + 1000


async def _insert_live(
    conn: Connection,
    live_id: int,
    *,
    title: str = "TEST_CDC",
    city: str = "Tokyo",
    live_date: Optional[date] = None,
    review_status: str = "published",
    status: str = "announced",
) -> None:
    """插入一条测试 lives 行（created_by 留空，避免依赖 users 表）。"""
    if live_date is None:
        live_date = datetime.now(timezone.utc).date()
    await conn.execute(
        """
        INSERT INTO public.lives
            (id, livehouse_id, live_date, title, city, status, review_status)
        VALUES ($1, 1, $2, $3, $4, $5, $6)
        """,
        live_id,
        live_date,
        title,
        city,
        status,
        review_status,
    )


async def _cleanup_live(conn: Connection, live_id: int) -> None:
    """清理测试 lives 行及其产生的 sync_changes（尽力而为）。"""
    await conn.execute(
        "DELETE FROM public.sync_changes WHERE entity_type = 'live' AND entity_id = $1",
        live_id,
    )
    await conn.execute("DELETE FROM public.lives WHERE id = $1", live_id)


async def _reset_retention_state(conn: Connection, floor: int = 0) -> None:
    """把 retention floor 重置为指定值，并清空测试版本区间内的 sync_changes。"""
    await conn.execute(
        "DELETE FROM public.sync_changes WHERE version BETWEEN $1 AND $2",
        VERSION_BASE,
        VERSION_END,
    )
    await conn.execute(
        """
        UPDATE public.sync_retention_state
        SET retention_floor_version = $1, updated_at = now()
        WHERE id = TRUE
        """,
        floor,
    )


# ============================================================
# CDC — 事务原子性 / 版本 / 折叠
# ============================================================

async def test_cdc_transaction_atomic(db: Connection):
    """业务写入和 sync_changes 在同一事务中——回滚后均不可见。"""
    live_id = LIVE_ID_BASE + 1
    original_title = "TEST_CDC_Atomic"
    await _insert_live(db, live_id, title=original_title)

    before = await db.fetchval(
        "SELECT version FROM public.sync_version_counter WHERE id = TRUE"
    )

    try:
        async with db.transaction():
            await db.execute(
                "UPDATE public.lives SET title = $1 WHERE id = $2",
                "TEST_CDC_Atomic_Updated",
                live_id,
            )
            version = await next_version(db)
            await write_sync_change(db, version, "live", live_id, "upsert")
            raise RuntimeError("forced rollback")
    except RuntimeError:
        pass

    after = await db.fetchval(
        "SELECT version FROM public.sync_version_counter WHERE id = TRUE"
    )

    try:
        assert after == before, "version counter must roll back with the transaction"
        change = await db.fetchrow(
            "SELECT 1 FROM public.sync_changes WHERE version = $1", version
        )
        assert change is None, "rolled-back sync_changes must be invisible"
        row = await db.fetchrow(
            "SELECT title FROM public.lives WHERE id = $1", live_id
        )
        assert row["title"] == original_title, "rolled-back business write must be invisible"
    finally:
        await _cleanup_live(db, live_id)


async def test_version_monotonic(db: Connection):
    """10 个并发事务获得 10 个唯一且递增（无间隙）的版本号。"""
    pool = db.get_pool()

    if pool is not None:
        # db 本身已占用 1 个连接，实际可并发数 = max_size - 1；上限 10。
        concurrency = min(10, max(1, pool.get_max_size() - 1))

        async def _worker(_):
            async with pool.acquire() as conn:
                async with conn.transaction():
                    return await next_version(conn)

        versions = await asyncio.gather(*(_worker(i) for i in range(concurrency)))
    else:
        # conftest 未提供 pool-backed fixture 时的回退：顺序事务仍然必须得到
        # 唯一、无间隙的版本号。真实并发需要 pool-backed 的 db fixture。
        concurrency = 10
        versions = []
        for _ in range(concurrency):
            async with db.transaction():
                versions.append(await next_version(db))

    assert len(versions) == concurrency
    assert len(set(versions)) == concurrency, "versions must be unique"
    assert sorted(versions) == list(range(min(versions), min(versions) + concurrency)), (
        "versions must be monotonically increasing without gaps"
    )


async def test_entity_folding(db: Connection):
    """同一事务内对同一实体的多次修改只产生一条 sync_changes。"""
    live_id = LIVE_ID_BASE + 2
    await _insert_live(db, live_id, title="TEST_CDC_Fold")

    async def business_write(c: Connection) -> None:
        await c.execute(
            "UPDATE public.lives SET title = $1 WHERE id = $2",
            "TEST_CDC_Fold_1",
            live_id,
        )
        await c.execute(
            "UPDATE public.lives SET title = $1 WHERE id = $2",
            "TEST_CDC_Fold_2",
            live_id,
        )

    try:
        async with db.transaction():
            version = await cdc_transaction(db, live_id, "upsert", business_write)

        rows = await db.fetch(
            """
            SELECT version, action
            FROM public.sync_changes
            WHERE entity_type = 'live' AND entity_id = $1
            """,
            live_id,
        )
        assert len(rows) == 1, "multiple modifications must fold into one sync_changes"
        assert rows[0]["version"] == version
        assert rows[0]["action"] == "upsert"

        title = await db.fetchval(
            "SELECT title FROM public.lives WHERE id = $1", live_id
        )
        assert title == "TEST_CDC_Fold_2", "final business state must reflect the last write"
    finally:
        await _cleanup_live(db, live_id)


# ============================================================
# CDC — determine_action 各场景
# ============================================================

async def test_action_published_to_hidden(db: Connection):
    """published → hidden 返回 delete。"""
    live_id = LIVE_ID_BASE + 3
    await _insert_live(db, live_id, title="TEST_CDC_P2H", review_status="published")
    try:
        assert await determine_action(db, live_id) == "upsert"
        await db.execute(
            "UPDATE public.lives SET review_status = 'hidden' WHERE id = $1", live_id
        )
        assert await determine_action(db, live_id) == "delete"
    finally:
        await _cleanup_live(db, live_id)


async def test_action_hidden_to_published(db: Connection):
    """hidden → published 返回 upsert。"""
    live_id = LIVE_ID_BASE + 4
    await _insert_live(db, live_id, title="TEST_CDC_H2P", review_status="hidden")
    try:
        assert await determine_action(db, live_id) == "delete"
        await db.execute(
            "UPDATE public.lives SET review_status = 'published' WHERE id = $1", live_id
        )
        assert await determine_action(db, live_id) == "upsert"
    finally:
        await _cleanup_live(db, live_id)


async def test_action_city_change(db: Connection):
    """city 从 Tokyo 变为 Osaka。对 Tokyo scope 返回 delete。"""
    live_id = LIVE_ID_BASE + 5
    await _insert_live(db, live_id, title="TEST_CDC_CITY", city="Tokyo")
    try:
        assert await determine_action(db, live_id, city="Tokyo") == "upsert"
        await db.execute(
            "UPDATE public.lives SET city = 'Osaka' WHERE id = $1", live_id
        )
        assert await determine_action(db, live_id, city="Tokyo") == "delete"
        assert await determine_action(db, live_id, city="Osaka") == "upsert"
    finally:
        await _cleanup_live(db, live_id)


async def test_action_date_out_of_scope(db: Connection):
    """live_date 移出 scope → delete。"""
    live_id = LIVE_ID_BASE + 6
    today = datetime.now(timezone.utc).date()
    scope_start = today - timedelta(days=10)
    scope_end = today + timedelta(days=10)
    await _insert_live(db, live_id, title="TEST_CDC_DATE", live_date=today)
    try:
        assert await determine_action(
            db,
            live_id,
            city="Tokyo",
            scope_start_date=scope_start,
            scope_end_date=scope_end,
        ) == "upsert"

        await db.execute(
            "UPDATE public.lives SET live_date = $1 WHERE id = $2",
            today - timedelta(days=30),
            live_id,
        )
        assert await determine_action(
            db,
            live_id,
            city="Tokyo",
            scope_start_date=scope_start,
            scope_end_date=scope_end,
        ) == "delete"
    finally:
        await _cleanup_live(db, live_id)


async def test_action_physical_delete(db: Connection):
    """实体不存在 → delete。"""
    live_id = LIVE_ID_BASE + 7
    await _insert_live(db, live_id, title="TEST_CDC_DEL")
    try:
        await db.execute("DELETE FROM public.lives WHERE id = $1", live_id)
        assert await determine_action(db, live_id) == "delete"
        # 从未存在的 ID 同样返回 delete
        assert await determine_action(db, LIVE_ID_BASE + 9999) == "delete"
    finally:
        await _cleanup_live(db, live_id)


# ============================================================
# Retention — floor 语义 / cursor 有效性 / 幂等
# ============================================================

async def test_retention_floor_update(db: Connection):
    """清理后 retention_floor_version 正确更新（= 已清理的最大 version）。"""
    await _reset_retention_state(db, floor=0)

    v1 = VERSION_BASE + 1
    v2 = VERSION_BASE + 2
    v3 = VERSION_BASE + 3
    v4 = VERSION_BASE + 4
    old = datetime.now(timezone.utc) - timedelta(days=40)
    recent = datetime.now(timezone.utc)

    rows = (
        (v1, "upsert", old),
        (v2, "upsert", old),
        (v3, "delete", old),
        (v4, "upsert", recent),  # 近期日志不应被清理
    )
    for version, action, changed_at in rows:
        await db.execute(
            """
            INSERT INTO public.sync_changes
                (version, entity_type, entity_id, action, changed_at)
            VALUES ($1, 'live', $2, $3, $4)
            """,
            version,
            LIVE_ID_BASE + 10 + (version - VERSION_BASE),
            action,
            changed_at,
        )

    try:
        deleted = await clean_expired_logs(db, retention_days=30)
        assert deleted == 3

        floor = await get_retention_floor(db)
        assert floor == v3, "floor must equal the largest cleaned version"

        remaining_old = await db.fetchval(
            "SELECT count(*) FROM public.sync_changes WHERE version IN ($1, $2, $3)",
            v1,
            v2,
            v3,
        )
        assert remaining_old == 0, "expired rows must be removed"

        keep = await db.fetchval(
            "SELECT count(*) FROM public.sync_changes WHERE version = $1", v4
        )
        assert keep == 1, "recent logs must survive cleanup"
    finally:
        await _reset_retention_state(db, floor=0)


async def test_cursor_at_floor_valid(db: Connection):
    """since == retention_floor_version 时 cursor 仍有效。"""
    await db.execute(
        """
        UPDATE public.sync_retention_state
        SET retention_floor_version = $1, updated_at = now()
        WHERE id = TRUE
        """,
        5000,
    )
    try:
        assert await check_cursor_valid(db, 5000) is True
        assert await check_cursor_valid(db, 5001) is True  # 高于 floor 同样有效
    finally:
        await db.execute(
            """
            UPDATE public.sync_retention_state
            SET retention_floor_version = 0, updated_at = now()
            WHERE id = TRUE
            """
        )


async def test_cursor_below_floor_expired(db: Connection):
    """since < retention_floor_version 时返回过期。"""
    await db.execute(
        """
        UPDATE public.sync_retention_state
        SET retention_floor_version = $1, updated_at = now()
        WHERE id = TRUE
        """,
        5000,
    )
    try:
        assert await check_cursor_valid(db, 4999) is False
        assert await check_cursor_valid(db, 0) is False
    finally:
        await db.execute(
            """
            UPDATE public.sync_retention_state
            SET retention_floor_version = 0, updated_at = now()
            WHERE id = TRUE
            """
        )


async def test_retention_idempotent(db: Connection):
    """retention 清理任务幂等：重复运行不重复删除、floor 单调不减。"""
    await _reset_retention_state(db, floor=0)

    v1 = VERSION_BASE + 1
    old = datetime.now(timezone.utc) - timedelta(days=40)
    await db.execute(
        """
        INSERT INTO public.sync_changes
            (version, entity_type, entity_id, action, changed_at)
        VALUES ($1, 'live', $2, 'upsert', $3)
        """,
        v1,
        LIVE_ID_BASE + 20,
        old,
    )

    try:
        assert await clean_expired_logs(db, retention_days=30) == 1
        floor1 = await get_retention_floor(db)
        assert floor1 == v1

        assert await clean_expired_logs(db, retention_days=30) == 0
        floor2 = await get_retention_floor(db)
        assert floor2 == floor1, "second run must not move the floor"
    finally:
        await _reset_retention_state(db, floor=0)
