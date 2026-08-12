"""
CDC Writer — 事务内 sync_changes 写入服务

核心约束（V4.4 §5.2）：
- 业务写入 + version 递增 + sync_changes 写入在同一 BEGIN...COMMIT
- Version 来自 UPDATE sync_version_counter...RETURNING version，禁止使用 sequence
- 同一事务内同一实体多次修改折叠为最终动作
- 版本计数器单行（id=TRUE），UPDATE 持锁保证唯一递增

使用约定（折叠）：
    cdc_transaction() 对每个（事务, 实体）只调用一次。业务写入全部完成后，
    先用 determine_action() 计算实体最终对普通用户的动作，再调用
    cdc_transaction()。因此同一事务内对同一实体的多次修改只会产生一条
    sync_changes，version 只消耗一个。

安全（V4.4 §7.3）：
    本服务不直接暴露给 API 层。api_role 对 sync_changes / sync_version_counter
    无写权限（V2__permissions.sql 已 REVOKE），唯一写路径是后端业务服务在同一
    事务内调用本模块。本模块仅接收 Connection，不依赖任何 HTTP / API 上下文。
"""

from datetime import date
from typing import Awaitable, Callable, Optional

from asyncpg import Connection

__all__ = [
    "next_version",
    "write_sync_change",
    "determine_action",
    "cdc_transaction",
]


async def next_version(conn: Connection) -> int:
    """原子递增并返回新版本号。必须与业务写入在同一事务中调用。"""
    row = await conn.fetchrow(
        """
        UPDATE public.sync_version_counter
        SET version = version + 1
        WHERE id = TRUE
        RETURNING version
        """
    )
    if row is None:
        raise RuntimeError("sync_version_counter row (id=TRUE) is missing")
    return row["version"]


async def write_sync_change(
    conn: Connection,
    version: int,
    entity_type: str,
    entity_id: int,
    action: str,
) -> None:
    """写入一条同步变更记录。action 必须为 'upsert' 或 'delete'。"""
    if action not in ("upsert", "delete"):
        raise ValueError(f"invalid action: {action!r} (expected 'upsert' or 'delete')")
    await conn.execute(
        """
        INSERT INTO public.sync_changes (version, entity_type, entity_id, action)
        VALUES ($1, $2, $3, $4)
        """,
        version,
        entity_type,
        entity_id,
        action,
    )


async def determine_action(
    conn: Connection,
    entity_id: int,
    city: Optional[str] = None,
    scope_start_date: Optional[date] = None,
    scope_end_date: Optional[date] = None,
) -> str:
    """
    计算实体最终对普通用户的动作。

    规则（V4.4 §5.2）：
    - 新增已发布 → upsert
    - 更新（仍可见） → upsert
    - published → hidden → delete
    - hidden → published → upsert
    - city 移出 scope → delete
    - live_date 移出 scope → delete
    - 物理删除 → delete

    参数：
        city: 当前客户端 scope 城市。为 None 时不按城市过滤。
        scope_start_date / scope_end_date: 当前客户端 scope 日期区间。
            必须同时传入 datetime.date 对象才启用日期范围检查。
    """
    row = await conn.fetchrow(
        """
        SELECT review_status, city, live_date
        FROM public.lives
        WHERE id = $1
        """,
        entity_id,
    )

    if row is None:
        return "delete"

    if row["review_status"] != "published":
        return "delete"

    if city is not None and row["city"] != city:
        return "delete"

    if scope_start_date is not None and scope_end_date is not None:
        if not (scope_start_date <= row["live_date"] <= scope_end_date):
            return "delete"

    return "upsert"


async def cdc_transaction(
    conn: Connection,
    entity_id: int,
    final_action: str,
    business_write_fn: Callable[[Connection], Awaitable[None]],
) -> int:
    """
    完整的 CDC 事务包装器。

    业务写入先执行，然后获取版本号，最后写入 sync_changes。
    必须在调用方已开启的事务中调用（`async with conn.transaction()`）。

    返回新分配的版本号。

    用法：
        async with pool.acquire() as conn:
            async with conn.transaction():
                version = await cdc_transaction(
                    conn, live_id, "upsert",
                    lambda c: c.execute(
                        "UPDATE public.lives SET title = $1 WHERE id = $2",
                        title, live_id,
                    ),
                )

    注意：
        - final_action 应在业务写入全部完成后计算（通常用 determine_action）。
        - 每个（事务, 实体）只调用一次，以保证同一实体的多次修改折叠为一条日志。
    """
    await business_write_fn(conn)
    version = await next_version(conn)
    await write_sync_change(conn, version, "live", entity_id, final_action)
    return version
