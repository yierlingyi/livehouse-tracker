"""
Retention 测试（V4.4 §15.5）。

覆盖：
    1. since == retention_floor_version 有效（不返回 409）。
    2. since < retention_floor_version 返回 409 SYNC_CURSOR_EXPIRED。
    3. 无日志时仍可返回当前 high_water（空批次 cursor=since，无错误）。
    4. 清理任务更新 floor 后旧客户端会重新 /full（floor 单调推进）。

使用独立的版本区间（区别于 test_cdc.py 的 910_000_000），并在 finally 恢复
版本计数器与 floor，保证测试间隔离。
"""

from datetime import datetime, timedelta, timezone

import pytest
from asyncpg import Connection

from backend.services.retention_cleaner import clean_expired_logs, get_retention_floor

pytestmark = pytest.mark.asyncio

CITY = "RTN_CITY"
FLOOR_TEST = 1_000_000
VERSION_BASE = 920_000_000

_SCOPE_START = "2026-01-01"
_SCOPE_END = "2026-12-31"


def _sync_url(since: int) -> str:
    return (
        f"/api/v1/lives/sync?city={CITY}"
        f"&scope_start_date={_SCOPE_START}"
        f"&scope_end_date={_SCOPE_END}"
        f"&since={since}"
    )


async def _set_floor(db: Connection, floor: int) -> None:
    await db.execute(
        "UPDATE public.sync_retention_state "
        "SET retention_floor_version = $1, updated_at = now() WHERE id = TRUE",
        floor,
    )


async def test_since_at_floor_valid(db: Connection, client, sync_state):
    """since == retention_floor_version 时 cursor 有效，返回 200。"""
    start_v, floor = await sync_state.snapshot()
    try:
        await _set_floor(db, FLOOR_TEST)

        resp = await client.get(_sync_url(FLOOR_TEST))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # 空批次：cursor 保持 since，has_more=false，不报错
        assert body["cursor"] == FLOOR_TEST
        assert body["has_more"] is False
        assert body["data"] == []
        assert body["deletes"] == []
    finally:
        await sync_state.restore(start_v, floor)


async def test_since_below_floor_expired(db: Connection, client, sync_state):
    """since < retention_floor_version 返回 409 SYNC_CURSOR_EXPIRED。"""
    start_v, floor = await sync_state.snapshot()
    try:
        await _set_floor(db, FLOOR_TEST)

        resp = await client.get(_sync_url(FLOOR_TEST - 1))
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["code"] == "SYNC_CURSOR_EXPIRED"

        # 再低一点的 cursor 同样过期
        resp2 = await client.get(_sync_url(0))
        assert resp2.status_code == 409
    finally:
        await sync_state.restore(start_v, floor)


async def test_no_logs_still_returns_high_water(
    db: Connection, client, sync_state
):
    """无日志（since == high_water）时仍返回当前 high_water，无错误。"""
    start_v, floor = await sync_state.snapshot()
    try:
        await _set_floor(db, 0)  # 保证 since 不因残留 floor 过期
        high_water = await db.fetchval(
            "SELECT version FROM public.sync_version_counter WHERE id = TRUE"
        )

        resp = await client.get(_sync_url(high_water))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["cursor"] == high_water, "空批次 cursor 应等于当前 high_water"
        assert body["has_more"] is False
        assert body["data"] == []
        assert body["deletes"] == []
    finally:
        await sync_state.restore(start_v, floor)


async def test_cleanup_updates_floor(db: Connection, sync_state):
    """清理任务更新 floor 后，低于 floor 的旧 cursor 会过期（客户端需重新 /full）。"""
    start_v, floor = await sync_state.snapshot()
    try:
        await _set_floor(db, 0)

        old = datetime.now(timezone.utc) - timedelta(days=40)
        recent = datetime.now(timezone.utc)
        rows = (
            (VERSION_BASE + 1, "upsert", old),
            (VERSION_BASE + 2, "upsert", old),
            (VERSION_BASE + 3, "delete", old),
            (VERSION_BASE + 4, "upsert", recent),  # 近期日志不应被清理
        )
        for version, action, changed_at in rows:
            await db.execute(
                """
                INSERT INTO public.sync_changes
                    (version, entity_type, entity_id, action, changed_at)
                VALUES ($1, 'live', $2, $3, $4)
                """,
                version,
                VERSION_BASE + version,  # 独立 entity_id
                action,
                changed_at,
            )

        deleted = await clean_expired_logs(db, retention_days=30)
        assert deleted == 3, "只应清理 30 天前的 3 条"

        new_floor = await get_retention_floor(db)
        assert new_floor == VERSION_BASE + 3, "floor 必须等于已清理的最大 version"
        assert new_floor >= floor, "floor 单调不减"

        # 近期日志保留
        kept = await db.fetchval(
            "SELECT count(*) FROM public.sync_changes WHERE version = $1",
            VERSION_BASE + 4,
        )
        assert kept == 1
    finally:
        await db.execute("DELETE FROM public.sync_changes WHERE version > $1", start_v)
        await sync_state.restore(start_v, floor)
