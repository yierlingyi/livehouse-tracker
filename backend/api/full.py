"""
GET /api/v1/lives/full — 全量同步接口（V4.4 §9）

核心要求：
- 第一页：固定 scope_start_date = business_today()，scope_end_date = scope_start_date + 90 天
- 后续页：从签名 token 读取固定 scope，禁止动态 CURRENT_DATE
- 分页：signed keyset token，禁止 offset
- last_time 永远使用生成列 sort_start_time，绝不用原始 start_time
- ORDER BY 精确匹配 keyset 索引：(live_date, sort_start_time, id) ASC
- snapshot_cursor 在第一页事务中从 sync_version_counter 读取
- page_size 上限 2000，默认 500
- Token 非法 → 400 INVALID_PAGE_TOKEN；过期 → 409 FULL_PAGE_TOKEN_EXPIRED
- Token 中 city 必须与请求参数 city 一致
- 仅读 Primary（使用 get_primary_db 依赖）
- 返回：{data, scope{city, scope_start_date, scope_end_date}, snapshot_cursor, has_more, next_token}
- 末页：has_more=false, next_token=null
- 使用 page_size+1 技巧判断 has_more

错误响应按 V4.4 §14 约定以 detail 字符串承载 code，
由 Phase 4 的错误处理中间件（backend/middleware/error_handler.py）映射为
{code, message} JSON（contracts/shared.json#/definitions/Error）。
"""

import json as _json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Optional

from asyncpg import Connection
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.services.token_manager import (
    InvalidPageTokenError,
    PageTokenExpiredError,
    build_first_page_token,
    verify_token,
)

router = APIRouter()

DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 2000
SCOPE_DEFAULT_DAYS = 90
TOKEN_TTL_MINUTES = 30

# 业务时区（V4.4 §3 推荐）。config.py（Phase 4）可按城市配置覆盖。
BUSINESS_TZ = "Asia/Shanghai"

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
    updated_at
"""

# 与 keyset 索引 idx_lives_full_scope_keyset
# (city, live_date, sort_start_time, id) WHERE review_status='published' 精确匹配。
_QUERY_FIRST_PAGE = f"""
    SELECT {_SELECT_COLUMNS}
    FROM public.lives
    WHERE review_status = 'published'
      AND city = $1
      AND live_date >= $2
      AND live_date <= $3
    ORDER BY live_date ASC, sort_start_time ASC, id ASC
    LIMIT $4
"""

_QUERY_NEXT_PAGE = f"""
    SELECT {_SELECT_COLUMNS}
    FROM public.lives
    WHERE review_status = 'published'
      AND city = $1
      AND live_date >= $2
      AND live_date <= $3
      AND (live_date, sort_start_time, id) > ($4, $5, $6)
    ORDER BY live_date ASC, sort_start_time ASC, id ASC
    LIMIT $7
"""


async def get_primary_db():
    """Primary 数据库连接依赖（惰性引用 backend.main，避免循环导入）。

    /full 强制走 Primary（V4.4 §2 全局原则 1）。backend.main 中的
    primary_pool 由 Phase 4 创建；此依赖在请求时才解析，避免模块导入期循环依赖。
    """
    from backend.main import get_primary_db as _main_get_primary_db

    async for conn in _main_get_primary_db():
        yield conn


def business_today() -> date:
    """服务端业务日期，固定业务时区（默认 Asia/Shanghai）。

    缺少 IANA tzdata 时回退 UTC，保证接口不因时区数据缺失而失败。
    """
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(BUSINESS_TZ)).date()
    except Exception:
        return datetime.now(timezone.utc).date()


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


def _build_response(
    city: str,
    scope_start_date: date,
    scope_end_date: date,
    snapshot_cursor: Any,
    rows: Any,
    page_size: int,
) -> Dict[str, Any]:
    """构造 /full 响应。rows 为 page_size+1 的查询结果，据此判断 has_more。"""
    has_more = len(rows) > page_size
    if has_more:
        rows = rows[:page_size]

    data = [_serialize_live(r) for r in rows]

    next_token = None
    if has_more:
        next_token = build_first_page_token(
            city=city,
            scope_start_date=str(scope_start_date),
            scope_end_date=str(scope_end_date),
            snapshot_cursor=int(snapshot_cursor),
            last_row=rows[-1],  # asyncpg Record：last_row["sort_start_time"] 为生成列值
            ttl_minutes=TOKEN_TTL_MINUTES,
        )

    return {
        "data": data,
        "scope": {
            "city": city,
            "scope_start_date": str(scope_start_date),
            "scope_end_date": str(scope_end_date),
        },
        "snapshot_cursor": str(snapshot_cursor),
        "has_more": has_more,
        "next_token": next_token,
    }


@router.get("/api/v1/lives/full")
async def full_sync(
    city: str = Query(..., min_length=1, max_length=50),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    page_token: Optional[str] = Query(None),
    db: Connection = Depends(get_primary_db),
) -> Dict[str, Any]:
    """/full 全量同步：第一页生成固定 scope，后续页从签名 token 恢复 scope。"""
    if page_token is None:
        return await _first_page(db, city, page_size)
    return await _next_page(db, city, page_size, page_token)


async def _first_page(db: Connection, city: str, page_size: int) -> Dict[str, Any]:
    # 第一页：一次性生成固定 scope，后续分页 / /sync 必须沿用同一组值。
    scope_start_date = business_today()
    scope_end_date = scope_start_date + timedelta(days=SCOPE_DEFAULT_DAYS)

    # snapshot_cursor 必须与第一页查询在同一事务内读取（V4.4 §9.2）。
    async with db.transaction(isolation="read_committed"):
        snapshot_cursor = await db.fetchval(
            """
            SELECT version
            FROM public.sync_version_counter
            WHERE id = TRUE
            """
        )

        rows = await db.fetch(
            _QUERY_FIRST_PAGE,
            city,
            scope_start_date,
            scope_end_date,
            page_size + 1,  # page_size+1 技巧：判断 has_more
        )

    return _build_response(
        city, scope_start_date, scope_end_date, snapshot_cursor, rows, page_size
    )


async def _next_page(
    db: Connection, city: str, page_size: int, page_token: str
) -> Dict[str, Any]:
    try:
        payload = verify_token(page_token)
    except InvalidPageTokenError:
        raise HTTPException(status_code=400, detail="INVALID_PAGE_TOKEN")
    except PageTokenExpiredError:
        raise HTTPException(status_code=409, detail="FULL_PAGE_TOKEN_EXPIRED")

    # Token 中的 city 必须与请求参数一致（V4.4 §9.1）。
    if payload["city"] != city:
        raise HTTPException(status_code=400, detail="INVALID_PAGE_TOKEN")

    # 从 token 恢复固定 scope——禁止动态 CURRENT_DATE（V4.4 §3 跨午夜漂移）。
    try:
        scope_start_date = date.fromisoformat(payload["scope_start_date"])
        scope_end_date = date.fromisoformat(payload["scope_end_date"])
        last_date = date.fromisoformat(payload["last_date"])
        last_time = time.fromisoformat(payload["last_time"])  # 生成列 sort_start_time
    except ValueError:
        raise HTTPException(status_code=400, detail="INVALID_PAGE_TOKEN")

    snapshot_cursor = payload["snapshot_cursor"]
    last_id = payload["last_id"]

    rows = await db.fetch(
        _QUERY_NEXT_PAGE,
        city,
        scope_start_date,
        scope_end_date,
        last_date,
        last_time,
        last_id,
        page_size + 1,  # page_size+1 技巧：判断 has_more
    )

    return _build_response(
        city, scope_start_date, scope_end_date, snapshot_cursor, rows, page_size
    )
