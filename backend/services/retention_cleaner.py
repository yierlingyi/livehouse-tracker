"""
Retention Cleaner — 定期清理过期 CDC 日志

核心约束（V4.4 §6）：
- 不能用 MIN(version) 判断过期
- 正确语义：retention_floor_version = 已被清理掉的最大 version
- cursor 有效条件：since >= retention_floor_version
- 如果 since < retention_floor_version → 409 SYNC_CURSOR_EXPIRED

实现（V4.4 §6 参考 SQL）：
    单条原子语句完成「删除 + 取最大已删 version + 推进 floor」：

        WITH deleted AS (
            DELETE FROM sync_changes ... RETURNING version
        ),
        agg AS (
            SELECT count(*), max(version) FROM deleted
        ),
        updated AS (
            UPDATE sync_retention_state
            SET retention_floor_version = GREATEST(floor, max_deleted)
            ...
        )

幂等性：
    - 重复运行不再删行（行已删除），deleted_count = 0
    - GREATEST 保证 floor 单调不减
    - 任务本身是单条语句，天然原子
"""

from datetime import datetime, timedelta, timezone

from asyncpg import Connection

__all__ = [
    "clean_expired_logs",
    "get_retention_floor",
    "check_cursor_valid",
]


async def clean_expired_logs(conn: Connection, retention_days: int = 30) -> int:
    """
    清理 retention_days 天前的 sync_changes，返回删除的记录数。

    在单条语句中完成：
        DELETE ... RETURNING version
        → MAX(version) 作为 max_deleted
        → UPDATE retention_floor_version = GREATEST(floor, max_deleted)
    """
    if retention_days < 0:
        raise ValueError("retention_days must be non-negative")

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    row = await conn.fetchrow(
        """
        WITH deleted AS (
            DELETE FROM public.sync_changes
            WHERE changed_at < $1
            RETURNING version
        ),
        agg AS (
            SELECT
                count(*)          AS deleted_count,
                max(version)      AS max_deleted
            FROM deleted
        ),
        updated AS (
            UPDATE public.sync_retention_state
            SET retention_floor_version = GREATEST(
                    retention_floor_version,
                    COALESCE((SELECT max_deleted FROM agg), retention_floor_version)
                ),
                updated_at = now()
            WHERE id = TRUE
            RETURNING retention_floor_version
        )
        SELECT
            COALESCE((SELECT deleted_count FROM agg), 0)  AS deleted_count,
            (SELECT max_deleted FROM agg)                 AS max_deleted,
            (SELECT retention_floor_version FROM updated) AS retention_floor_version
        """,
        cutoff,
    )

    return int(row["deleted_count"])


async def get_retention_floor(conn: Connection) -> int:
    """获取当前保留底线版本号。"""
    row = await conn.fetchrow(
        """
        SELECT retention_floor_version
        FROM public.sync_retention_state
        WHERE id = TRUE
        """
    )
    if row is None:
        raise RuntimeError("sync_retention_state row (id=TRUE) is missing")
    return row["retention_floor_version"]


async def check_cursor_valid(conn: Connection, since: int) -> bool:
    """检查客户端 cursor 是否仍然有效（since >= retention_floor_version）。"""
    floor = await get_retention_floor(conn)
    return since >= floor
