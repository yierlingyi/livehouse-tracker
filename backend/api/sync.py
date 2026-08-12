"""
GET /api/v1/lives/sync — 增量同步接口（V4.4 §10）

核心约束（V4.4 §10 + 终审结论）：
- /sync 强制读 Primary（get_primary_db 依赖，惰性引用 backend.main 避免循环导入）
- repeatable_read 事务内读取 retention floor / high_water / sync_changes / lives，
  保证批次是一个一致的快照；retention floor 检查必须在事务内执行，
  否则并发清理任务推进 floor 并删除日志时，会读到不完整批次（漏读）。
- high_water 来自 sync_version_counter（客户端同步水位只来自服务端版本计数器）。
- cursor = max(本批次返回的 version)，绝不直接返回 high_water（除非批次覆盖到 high_water）。
- has_more = (cursor < high_water)，只有批次覆盖到 high_water 时才返回 false。
- 空批次：cursor == since，has_more=false，不报错（防止无限循环，客户端已追平）。
- Entity 去重：DISTINCT ON (entity_type, entity_id) ORDER BY version DESC
  → 同一实体在本批次只出现一次，只输出其最终动作。
- Scope 投影：读取 lives 当前行，逐条检查
    实体不存在 / review_status != 'published' / city 不匹配 / live_date 出范围 → delete
    全部通过 → upsert（返回完整 Live 对象）
- 同一实体不会同时出现在 data 和 deletes（DISTINCT ON 保证 + 防御性校验）。
- 返回按 version ASC 排序（回放顺序），deletes 数组仅含 id。
- limit 默认 1000，最大 5000。
- since >= retention_floor_version 才有效，否则 409 SYNC_CURSOR_EXPIRED。

错误响应按 V4.4 §14 约定以 detail 字符串承载 code，由 Phase 4 错误处理中间件
（backend/middleware/error_handler.py）映射为 {code, message} JSON：
    400 INVALID_CURSOR        since 缺失 / 格式错误 / 负数
    409 SYNC_CURSOR_EXPIRED   since 低于 retention floor
    429 RATE_LIMITED          由 Phase 4 限流中间件发出，本端点不直接触发
    500 SYNC_INVARIANT_BROKEN 数据不变量被破坏（同实体同时出现在 data 与 deletes 等）
"""

import json as _json
from datetime import date, time
from typing import Any, Dict, List, Optional, Tuple

from asyncpg import Connection
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter()

DEFAULT_LIMIT = 1000
MAX_LIMIT = 5000

# 与 shared.json#/definitions/Live 对齐；额外读取 review_status 用于 Scope 投影。
_SELECT_COLUMNS = """
    id,
    livehouse_id,
    live_date,
    start_time,
    sort_start_time,
    title,
    ticket_price,
    ticket_url,
    poster_image_url,
    city,
    band_names,
    status,
    updated_at,
    review_status
"""

# V4.4 §10.2：Entity 去重，同一实体只保留 version 最大的最终动作。
#
# 两层结构，缺一不可：
#   内层 DISTINCT ON (entity_type, entity_id) ... ORDER BY entity_id, version DESC
#     → 每个实体只保留其最终动作（version 最大的一条）。
#   外层 ORDER BY version ASC LIMIT
#     → 本批按回放顺序（version ASC）截取前 limit 个实体。
#
# 为什么不能照搬计划书示例把 LIMIT 直接放在内层（按 entity_id 排序截断）：
#   若内层按 entity_id 排序截断，返回集内 version 可能不是最小的 limit 个，
#   则 cursor = max(返回 version) 会「跳过」那些最终版本低于 cursor 但
#   尚未返回的实体 → 客户端永久漏读（破坏 §15.4「循环到 has_more=false 后数据完整」）。
#   例如 A(id=1,@90)、B(id=2,@95)、C(id=3,@80)、limit=2：
#     按 entity_id 截断返回 A、B，cursor=95，下次 since=95 时 C@80 被跳过。
#   改为「先去重，再按 version ASC 截断」后，返回的是 version 最小的 limit 个实体，
#   cursor 即本批最大 version，是安全水位：任何未返回实体的最终版本 >= cursor
#   （version 是 sync_changes 主键，全局唯一，故无边界并列问题）。
_QUERY_DEDUP = """
    SELECT version, entity_type, entity_id, action
    FROM (
        SELECT DISTINCT ON (entity_type, entity_id)
            version,
            entity_type,
            entity_id,
            action
        FROM public.sync_changes
        WHERE version > $1
          AND version <= $2
          AND entity_type = 'live'
        ORDER BY entity_type, entity_id, version DESC
    ) AS latest
    ORDER BY version ASC
    LIMIT $3
"""

# V4.4 §10.3：读取候选实体的当前快照（repeatable_read 事务内与 changes 一致）。
_QUERY_LIVES = f"""
    SELECT {_SELECT_COLUMNS}
    FROM public.lives
    WHERE id = ANY($1::bigint[])
"""

_QUERY_RETENTION_FLOOR = """
    SELECT retention_floor_version
    FROM public.sync_retention_state
    WHERE id = TRUE
"""

_QUERY_HIGH_WATER = """
    SELECT version
    FROM public.sync_version_counter
    WHERE id = TRUE
"""


async def get_primary_db():
    """Primary 数据库连接依赖（惰性引用 backend.main，避免循环导入）。

    /sync 强制走 Primary（V4.4 §2 全局原则 1）。backend.main 中的
    primary_pool 由 Phase 4 创建；此依赖在请求时才解析，避免模块导入期循环依赖。
    """
    from backend.main import get_primary_db as _main_get_primary_db

    async for conn in _main_get_primary_db():
        yield conn


def _parse_cursor(since_raw: Optional[str]) -> int:
    """解析 since 查询参数。

    缺失 / 非整数 / 负数均视为格式错误 → 400 INVALID_CURSOR（V4.4 §14）。
    返回非负整数。
    """
    if since_raw is None:
        raise HTTPException(status_code=400, detail="INVALID_CURSOR")
    try:
        since = int(since_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="INVALID_CURSOR")
    if since < 0:
        raise HTTPException(status_code=400, detail="INVALID_CURSOR")
    return since


def _time_to_str(value: Optional[time]) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _serialize_live(row: Any) -> Dict[str, Any]:
    """把 asyncpg 行转换为契约 Live 对象（shared.json#/definitions/Live）。"""
    band_names = row["band_names"]
    if isinstance(band_names, str):
        try:
            band_names = _json.loads(band_names)
        except ValueError:
            band_names = []
    if not isinstance(band_names, list):
        band_names = []

    live_date = row["live_date"]
    updated_at = row["updated_at"]

    return {
        "id": row["id"],
        "livehouse_id": row["livehouse_id"],
        "live_date": live_date.isoformat()
        if isinstance(live_date, date)
        else str(live_date),
        "start_time": _time_to_str(row["start_time"]),
        "sort_start_time": _time_to_str(row["sort_start_time"]),
        "title": row["title"],
        "ticket_price": row["ticket_price"],
        "ticket_url": row["ticket_url"],
        "poster_image_url": row["poster_image_url"],
        "city": row["city"],
        "band_names": band_names,
        "status": row["status"],
        "updated_at": updated_at.isoformat()
        if hasattr(updated_at, "isoformat")
        else str(updated_at),
    }


async def _project_scope(
    db: Connection,
    changes: List[Any],
    city: str,
    scope_start_date: date,
    scope_end_date: date,
) -> Tuple[List[Dict[str, Any]], List[int]]:
    """Scope 投影（V4.4 §10.3）。

    对折叠后的每个实体（每实体在批次内仅出现一次）：
      - action == 'delete' 或实体不存在 → delete
      - review_status != 'published' → delete
      - city 不匹配 → delete
      - live_date 超出 [scope_start_date, scope_end_date] → delete
      - 全部通过 → upsert（返回完整 Live 对象）

    返回 (data, deletes)，均按 version ASC 回放顺序。
    """
    if not changes:
        return [], []

    # 回放顺序：version ASC。
    changes = sorted(changes, key=lambda c: c["version"])

    candidate_ids = [c["entity_id"] for c in changes]
    rows = await db.fetch(_QUERY_LIVES, candidate_ids)
    rows_by_id = {row["id"]: row for row in rows}

    data: List[Dict[str, Any]] = []
    deletes: List[int] = []
    deleted_ids = set()
    data_ids = set()

    for change in changes:
        entity_id = change["entity_id"]
        action = change["action"]
        row = rows_by_id.get(entity_id)

        # DB CHECK 约束（action IN ('upsert','delete')）已保证，此处防御。
        if action not in ("upsert", "delete"):
            raise HTTPException(status_code=500, detail="SYNC_INVARIANT_BROKEN")

        in_scope = (
            action == "upsert"
            and row is not None
            and row["review_status"] == "published"
            and row["city"] == city
            and scope_start_date <= row["live_date"] <= scope_end_date
        )

        if in_scope:
            # 同一实体不得同时出现在 data 与 deletes（V4.4 §15.4）。
            if entity_id in deleted_ids or entity_id in data_ids:
                raise HTTPException(status_code=500, detail="SYNC_INVARIANT_BROKEN")
            data_ids.add(entity_id)
            data.append(_serialize_live(row))
        else:
            if entity_id in data_ids:
                raise HTTPException(status_code=500, detail="SYNC_INVARIANT_BROKEN")
            if entity_id not in deleted_ids:
                deleted_ids.add(entity_id)
                deletes.append(entity_id)

    return data, deletes


@router.get("/api/v1/lives/sync")
async def incremental_sync(
    city: str = Query(..., min_length=1, max_length=50),
    scope_start_date: date = Query(...),
    scope_end_date: date = Query(...),
    since: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Connection = Depends(get_primary_db),
) -> Dict[str, Any]:
    """/sync 增量回放：按固定 Scope 投影 sync_changes 变更日志。"""
    cursor = _parse_cursor(since)

    # repeatable_read 强快照（V4.4 §10.2）。floor 检查必须在事务内执行，
    # 否则与 retention 清理任务并发时可能读到不完整批次。
    async with db.transaction(isolation="repeatable_read"):
        retention_floor = await db.fetchval(_QUERY_RETENTION_FLOOR)
        if retention_floor is None:
            raise HTTPException(status_code=500, detail="SYNC_INVARIANT_BROKEN")
        if cursor < retention_floor:
            raise HTTPException(status_code=409, detail="SYNC_CURSOR_EXPIRED")

        high_water = await db.fetchval(_QUERY_HIGH_WATER)
        if high_water is None:
            raise HTTPException(status_code=500, detail="SYNC_INVARIANT_BROKEN")

        changes = await db.fetch(_QUERY_DEDUP, cursor, high_water, limit)

        data, deletes = await _project_scope(
            db, changes, city, scope_start_date, scope_end_date
        )

    if changes:
        # 批次覆盖到 high_water 时才返回 has_more=false；否则 cursor 必须为本批最大 version。
        batch_high = max(c["version"] for c in changes)
        return_cursor = batch_high
        has_more = batch_high < high_water
    else:
        # 空批次：cursor == since，has_more=false（客户端已追平，避免无限循环）。
        return_cursor = cursor
        has_more = False

    return {
        "data": data,
        "deletes": deletes,
        "cursor": return_cursor,
        "has_more": has_more,
    }
