"""Admin 管理（api_contract.md §4.5）。

- GET    /api/v1/admin/lives         所有 Live（?kind=all|normal|coop）
- PATCH  /api/v1/admin/lives/{id}    强制编辑（全字段含 setlist/阵容）
- POST   /api/v1/admin/lives/{id}/offline  强制下架（status+review_status→draft）
- GET    /api/v1/admin/bands         乐队账号库（?filter=pending|all）
- GET    /api/v1/admin/bands/{id}    账号详情
- PATCH  /api/v1/admin/bands/{id}    通过/拒绝/改资料
- DELETE /api/v1/admin/bands/{id}    删除账号

全部要求管理员鉴权（get_current_admin）。写操作走 V3 SECURITY DEFINER 函数。
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.api.common import (
    _int_or_none,
    db_execute,
    db_fetch,
    db_fetchrow,
    get_db,
    load_live_with_venue,
    load_setlist,
    normalize_setlist,
    parse_date_value,
    parse_time_value,
    parse_jsonb,
    public_account,
    resolve_venue,
    serialize_admin_band_item,
    serialize_admin_live,
    serialize_band_live,
    serialize_livehouse,
)
from backend.api.deps import get_current_admin

logger = logging.getLogger("bandlive")

router = APIRouter()


def _validation(message: str) -> HTTPException:
    return HTTPException(
        status_code=400, detail={"code": "VALIDATION_ERROR", "message": message}
    )


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": message})


# ============================================================
# 所有 Live
# ============================================================
@router.get("/api/v1/admin/lives")
async def admin_list_lives(
    kind: str = "all",
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    sql = """
        SELECT l.*, v.name AS livehouse_name, ba.username AS owner_username
        FROM public.lives l
        LEFT JOIN public.livehouses v ON v.id = l.livehouse_id
        LEFT JOIN public.band_accounts ba ON ba.id = l.created_by
    """
    params: list = []
    if kind == "normal":
        sql += " WHERE l.kind = 'normal'"
    elif kind == "coop":
        sql += " WHERE l.kind = 'coop'"
    sql += " ORDER BY l.id DESC"
    rows = await db_fetch(conn, sql, *params)
    return {"items": [serialize_admin_live(r) for r in rows]}


@router.patch("/api/v1/admin/lives/{live_id}")
async def admin_update_live(
    live_id: int,
    body: dict = Body(...),
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    live = await load_live_with_venue(conn, live_id)
    if live is None:
        raise _not_found("演出不存在")

    title = str(body.get("title") if "title" in body else live["title"] or "").strip()
    if not title:
        title = live["title"]

    if "livehouse_id" in body:
        livehouse_id = _int_or_none(body.get("livehouse_id"))
        city = ""
        if livehouse_id:
            venue = await resolve_venue(conn, livehouse_id)
            if venue is None:
                raise _validation("所选场地不存在")
            city = venue["city"] or ""
    else:
        livehouse_id = live["livehouse_id"]
        city = live["city"] or ""

    live_date = parse_date_value(body.get("live_date")) if body.get("live_date") else live["live_date"]
    if "start_time" in body:
        start_time = parse_time_value(body.get("start_time"))
    else:
        start_time = live["start_time"]

    ticket_price = str(body["ticket_price"]) if "ticket_price" in body and body["ticket_price"] not in (None, "") else live["ticket_price"]
    ticket_url = str(body["ticket_url"]).strip() if "ticket_url" in body else (live["ticket_url"] or "")
    poster_image_url = str(body["poster_image_url"]).strip() if "poster_image_url" in body else (live["poster_image_url"] or "")
    if isinstance(body.get("setlist"), list):
        setlist = normalize_setlist(body["setlist"])
    else:
        setlist = await load_setlist(conn, live_id)
    if isinstance(body.get("band_names"), list):
        band_names = body["band_names"]
    else:
        band_names = parse_jsonb(live["band_names"])

    kind = body.get("kind") if body.get("kind") in ("normal", "coop") else live["kind"]
    status = body.get("status") if body.get("status") in ("draft", "announced", "on_sale", "completed", "cancelled") else live["status"]
    review_status = body.get("review_status") if body.get("review_status") in ("draft", "published", "hidden") else live["review_status"]

    bands = body.get("bands") if isinstance(body.get("bands"), list) else None

    await db_execute(
        conn,
        """
        SELECT public.safe_admin_update_live(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
        )
        """,
        live_id, livehouse_id, live_date, start_time, title, ticket_price,
        ticket_url, poster_image_url, city, status, review_status, kind,
        band_names, setlist, bands,
    )
    row = await load_live_with_venue(conn, live_id)
    return {"live": serialize_admin_live(row)}


@router.post("/api/v1/admin/lives/{live_id}/offline")
async def admin_offline_live(
    live_id: int,
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    live = await load_live_with_venue(conn, live_id)
    if live is None:
        raise _not_found("演出不存在")
    await db_execute(conn, "SELECT public.safe_admin_offline_live($1)", live_id)
    row = await load_live_with_venue(conn, live_id)
    return {"live": serialize_admin_live(row)}


@router.get("/api/v1/admin/lives/{live_id}")
async def admin_get_live(
    live_id: int,
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    """单条详情（任意 review_status，强制编辑页不再对草稿 404）。与 mock
    adminLiveDetail 对齐：live 内嵌 setlist + 顶层 venue/setlist/poster_image_url。"""
    row = await load_live_with_venue(conn, live_id)
    if row is None:
        raise _not_found("演出不存在")
    setlist = await load_setlist(conn, live_id)
    venue = None
    if row["livehouse_id"]:
        venue_row = await db_fetchrow(
            conn, "SELECT * FROM public.livehouses WHERE id = $1", row["livehouse_id"]
        )
        if venue_row is not None:
            venue = serialize_livehouse(venue_row)
    return {
        "live": serialize_band_live(
            row, setlist, row["livehouse_name"] or "", row["owner_username"] or ""
        ),
        "venue": venue,
        "setlist": setlist,
        "poster_image_url": row["poster_image_url"] or "",
    }


# ============================================================
# 乐队账号库 / 审核队列
# ============================================================
@router.get("/api/v1/admin/bands")
async def admin_list_bands(
    filter: str = "all",
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    sql = "SELECT * FROM public.band_accounts WHERE role = 'band'"
    params: list = []
    if filter == "pending":
        sql += " AND status = 'pending'"
    sql += " ORDER BY created_at DESC"
    rows = await db_fetch(conn, sql, *params)
    return {"items": [serialize_admin_band_item(r) for r in rows]}


@router.get("/api/v1/admin/bands/{band_id}")
async def admin_get_band(
    band_id: int,
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    row = await db_fetchrow(
        conn,
        "SELECT * FROM public.band_accounts WHERE id = $1 AND role = 'band'",
        band_id,
    )
    if row is None:
        raise _not_found("账号不存在")
    return {
        "account": public_account(row),
        "band": {"id": row["id"], "band_name": row["band_name"], "intro": row["intro"] or ""},
    }


@router.patch("/api/v1/admin/bands/{band_id}")
async def admin_update_band(
    band_id: int,
    body: dict = Body(...),
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    row = await db_fetchrow(
        conn,
        "SELECT * FROM public.band_accounts WHERE id = $1 AND role = 'band'",
        band_id,
    )
    if row is None:
        raise _not_found("账号不存在")

    action = body.get("action")
    if action == "approve":
        status = "active"
    elif action == "reject":
        status = "rejected"
    elif action in ("pending", "disabled"):
        status = action
    else:
        status = row["status"]

    band_name = body.get("band_name") if "band_name" in body else None
    intro = body.get("intro") if "intro" in body else None

    await db_execute(
        conn,
        "SELECT public.safe_admin_band_status($1, $2, $3, $4)",
        band_id, status, band_name, intro,
    )
    new_row = await db_fetchrow(
        conn,
        "SELECT * FROM public.band_accounts WHERE id = $1",
        band_id,
    )
    return {
        "account": public_account(new_row),
        "band": {"id": new_row["id"], "band_name": new_row["band_name"], "intro": new_row["intro"] or ""},
    }


@router.delete("/api/v1/admin/bands/{band_id}")
async def admin_delete_band(
    band_id: int,
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    row = await db_fetchrow(
        conn,
        "SELECT * FROM public.band_accounts WHERE id = $1 AND role = 'band'",
        band_id,
    )
    if row is None:
        raise _not_found("账号不存在")
    await db_execute(conn, "SELECT public.safe_admin_delete_band($1)", band_id)
    return {"ok": True}
