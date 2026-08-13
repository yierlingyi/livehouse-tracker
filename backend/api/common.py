"""三端扩展接口的公共 helper：DB 依赖、错误码映射、响应序列化。

错误统一 {code, message}（api_contract.md §0）。SECURITY DEFINER 函数以
RAISE EXCEPTION '<CODE>' 拒绝非法操作；本模块将 asyncpg 抛出的 PostgresError
首行错误码映射为契约 HTTP 错误。
"""

import json as _json
from datetime import date, time
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import HTTPException

# 数据库 RAISE EXCEPTION 错误码 → (HTTP 状态, 对外 code, 用户提示)
_DB_ERROR_MAP: Dict[str, tuple] = {
    "USERNAME_TAKEN": (409, "ACCOUNT_EXISTS", "账号已存在"),
    "INVALID_USERNAME": (400, "VALIDATION_ERROR", "用户名不合法"),
    "INVALID_PASSWORD": (400, "VALIDATION_ERROR", "密码不合法"),
    "INVALID_BAND_NAME": (400, "VALIDATION_ERROR", "乐队名称不能为空"),
    "INVALID_TITLE": (400, "VALIDATION_ERROR", "请填写 Live 名称"),
    "INVALID_LIVE_DATE": (400, "VALIDATION_ERROR", "请选择演出日期"),
    "INVALID_LIVEHOUSE": (400, "VALIDATION_ERROR", "请选择演出场地"),
    "INVALID_CITY": (400, "INVALID_CITY", "城市不能为空"),
    "INVALID_VENUE_NAME": (400, "VALIDATION_ERROR", "请填写场地名称"),
    "INVALID_PLATFORM": (400, "VALIDATION_ERROR", "平台不合法"),
    "INVALID_GROUP_ID": (400, "VALIDATION_ERROR", "请填写群号"),
    "INVALID_STATUS": (400, "VALIDATION_ERROR", "状态不合法"),
    "INVALID_ACTION": (400, "VALIDATION_ERROR", "操作不合法"),
    "INVALID_BANDS": (400, "VALIDATION_ERROR", "乐队阵容不合法"),
    "UNKNOWN_BAND_ID": (400, "VALIDATION_ERROR", "阵容包含未知乐队"),
    "TOO_MANY_BANDS": (400, "VALIDATION_ERROR", "阵容乐队数超限"),
    "FORBIDDEN": (403, "FORBIDDEN", "无权限操作"),
    "NOT_FOUND": (404, "NOT_FOUND", "资源不存在"),
    "USER_NOT_FOUND": (404, "USER_NOT_FOUND", "乐队账号不存在"),
    "CANNOT_INVITE_SELF": (400, "CANNOT_INVITE_SELF", "不能邀请自己"),
}


async def get_db():
    """Primary 连接依赖（惰性引用 backend.main，避免循环导入）。"""
    from backend.main import get_primary_db as _main_get_primary_db

    async for conn in _main_get_primary_db():
        yield conn


def raise_db_error(exc: BaseException) -> None:
    """把 SECURITY DEFINER 函数抛出的 PostgresError 映射为契约 HTTPException。

    asyncpg 对 RAISE EXCEPTION 'CODE' 的报错信息形如：
        CODE
        CONTEXT: PL/pgSQL function ...
    取首行作为错误码。
    """
    message = str(exc)
    code = message.splitlines()[0].strip() if message.strip() else "INTERNAL_ERROR"
    mapping = _DB_ERROR_MAP.get(code)
    if mapping:
        status, out_code, out_msg = mapping
        raise HTTPException(status_code=status, detail={"code": out_code, "message": out_msg})
    raise HTTPException(
        status_code=500,
        detail={"code": "INTERNAL_ERROR", "message": "internal server error"},
    )


async def db_fetchval(conn: asyncpg.Connection, query: str, *args) -> Any:
    try:
        return await conn.fetchval(query, *args)
    except asyncpg.exceptions.PostgresError as exc:
        raise_db_error(exc)


async def db_fetchrow(conn: asyncpg.Connection, query: str, *args) -> Any:
    try:
        return await conn.fetchrow(query, *args)
    except asyncpg.exceptions.PostgresError as exc:
        raise_db_error(exc)


async def db_fetch(conn: asyncpg.Connection, query: str, *args) -> List[Any]:
    try:
        return await conn.fetch(query, *args)
    except asyncpg.exceptions.PostgresError as exc:
        raise_db_error(exc)


async def db_execute(conn: asyncpg.Connection, query: str, *args) -> str:
    try:
        return await conn.execute(query, *args)
    except asyncpg.exceptions.PostgresError as exc:
        raise_db_error(exc)


# ============================================================
# 序列化
# ============================================================

def parse_jsonb(value: Any) -> List[Any]:
    """把 jsonb 列规范化为 list；兼容 str（PG 文本回传）与 dict 等异常形态。"""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = _json.loads(value)
        except ValueError:
            return []
    if isinstance(value, list):
        return value
    return [value] if isinstance(value, dict) else []


def _iso_d(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, (date, time)) else str(value)


def _dt_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def public_account(row: Any) -> Dict[str, Any]:
    """band_accounts 行 → 公开账号对象（不含 password_hash）。"""
    return {
        "id": row["id"],
        "username": row["username"],
        "band_name": row["band_name"],
        "intro": row["intro"] or "",
        "qq_bind": row["qq_bind"] or None,
        "cover_url": row["cover_url"] or None,
        "members": parse_jsonb(row["members"]),
        "role": row["role"],
        "status": row["status"],
        "created_at": _dt_iso(row["created_at"]),
    }


def serialize_band_live(
    row: Any,
    setlist: Optional[List[Dict[str, Any]]] = None,
    livehouse_name: str = "",
    owner_username: str = "",
) -> Dict[str, Any]:
    """乐队端 Live 投影（与 frontend/shared/mock/band.mock.js serializeBandLive 对齐）。"""
    return {
        "id": row["id"],
        "owner": owner_username or "",
        "title": row["title"],
        "livehouse_id": row["livehouse_id"],
        "livehouse_name": livehouse_name or "",
        "live_date": _iso_d(row["live_date"]),
        "start_time": _iso_d(row["start_time"]),
        "ticket_price": row["ticket_price"],
        "ticket_url": row["ticket_url"] or "",
        "poster_image_url": row["poster_image_url"] or "",
        "city": row["city"] or "",
        "band_names": parse_jsonb(row["band_names"]),
        "status": row["status"],
        "kind": row["kind"] if "kind" in row else "normal",
        "review_status": row["review_status"],
        "updated_at": _dt_iso(row["updated_at"]),
        "setlist": setlist or [],
    }


def serialize_admin_live(row: Any) -> Dict[str, Any]:
    """Admin 端 Live 投影（与 venues.mock.js adminLiveItem 对齐）。"""
    return {
        "id": row["id"],
        "title": row["title"],
        "live_date": _iso_d(row["live_date"]),
        "kind": row["kind"] if "kind" in row else "normal",
        "review_status": row["review_status"],
        "status": row["status"],
        "band_names": parse_jsonb(row["band_names"]),
        "city": row["city"],
        "livehouse_id": row["livehouse_id"],
    }


# ============================================================
# 字段解析 / 归一化
# ============================================================

def parse_date_value(value: Any) -> Optional[date]:
    """把日期字符串归一为 date；None/'' → None；非法 → 400 VALIDATION_ERROR。"""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "日期格式不合法"},
        )


def parse_time_value(value: Any) -> Optional[time]:
    """把时间字符串归一为 time；None/'' → None；非法 → 400 VALIDATION_ERROR。"""
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    try:
        return time.fromisoformat(str(value))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "时间格式不合法"},
        )


def normalize_setlist(value: Any) -> List[Dict[str, Any]]:
    """setlist 归一：仅保留含 song_title 的条目，band_id 非 int → None。"""
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for s in value:
        if not isinstance(s, dict):
            continue
        song = str(s.get("song_title") or "").strip()
        if not song:
            continue
        band_id = s.get("band_id")
        if not isinstance(band_id, int):
            band_id = None
        out.append({"song_title": song, "band_id": band_id})
    return out


def normalize_songs(value: Any) -> List[Dict[str, Any]]:
    """拼盘曲目归一：仅保留含 song_title 的条目。"""
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for s in value:
        if isinstance(s, dict) and str(s.get("song_title") or "").strip():
            out.append({"song_title": str(s["song_title"]).strip()})
    return out


def normalize_members(value: Any) -> List[Dict[str, Any]]:
    """乐队成员归一：[{name, role?}]。"""
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for m in value:
        if isinstance(m, dict) and str(m.get("name") or "").strip():
            out.append({
                "name": str(m["name"]).strip(),
                "role": str(m.get("role") or "").strip() if m.get("role") is not None else None,
            })
    return out


def _int_or_none(value: Any) -> Optional[int]:
    if value is None or value == "" or value == 0:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "id 格式不合法"},
        )


def _price_str(value: Any) -> Optional[str]:
    """ticket_price 归一为 VARCHAR 文本；None/'' → None。"""
    if value is None or value == "" or isinstance(value, bool):
        return None
    return str(value)


def _pick_str(body: Dict[str, Any], key: str, existing: Any) -> str:
    """body 含 key → 取其字符串（可能清空）；否则保留 existing。"""
    if key in body:
        return str(body.get(key) or "").strip()
    return "" if existing is None else str(existing).strip()


def serialize_livehouse(row: Any) -> Dict[str, Any]:
    """livehouses 行 → 公开场地对象（与 livehouse.mock.js 对齐）。"""
    return {
        "id": row["id"],
        "name": row["name"],
        "city": row["city"],
        "address": row["address"] or "",
        "phone": row["phone"] or "",
        "image_url": row["image_url"] or "",
        "intro": row["intro"] or "",
        "floorplan_url": row["floorplan_url"] or "",
    }


def serialize_band_item(row: Any) -> Dict[str, Any]:
    """band_accounts 行 → 公开乐队列表项（与 bands.mock.js 对齐）。"""
    return {
        "id": row["id"],
        "name": row["band_name"],
        "cover_url": row["cover_url"] or "",
    }


def serialize_band_detail(row: Any) -> Dict[str, Any]:
    """band_accounts 行 → 公开乐队详情（与 bands.mock.js 对齐）。"""
    return {
        "id": row["id"],
        "name": row["band_name"],
        "intro": row["intro"] or "",
        "cover_url": row["cover_url"] or "",
        "members": parse_jsonb(row["members"]),
    }


def serialize_admin_band_item(row: Any) -> Dict[str, Any]:
    """Admin 乐队列表项（与 venues.mock.js bandItem 对齐）。"""
    return {
        "id": row["id"],
        "username": row["username"],
        "band_name": row["band_name"],
        "status": row["status"],
        "created_at": _dt_iso(row["created_at"]),
    }


async def resolve_venue(conn: asyncpg.Connection, livehouse_id: Optional[int]):
    return await db_fetchrow(
        conn, "SELECT * FROM public.livehouses WHERE id = $1", livehouse_id
    )


async def load_setlist(conn: asyncpg.Connection, live_id: int) -> List[Dict[str, Any]]:
    rows = await db_fetch(
        conn,
        """
        SELECT song_title, band_id
        FROM public.live_setlist
        WHERE live_id = $1
        ORDER BY position ASC
        """,
        live_id,
    )
    return [
        {"song_title": r["song_title"], "band_id": r["band_id"]}
        for r in rows
    ]


async def load_live_with_venue(conn: asyncpg.Connection, live_id: int):
    return await db_fetchrow(
        conn,
        """
        SELECT l.*, v.name AS livehouse_name, ba.username AS owner_username
        FROM public.lives l
        LEFT JOIN public.livehouses v ON v.id = l.livehouse_id
        LEFT JOIN public.band_accounts ba ON ba.id = l.created_by
        WHERE l.id = $1
        """,
        live_id,
    )
