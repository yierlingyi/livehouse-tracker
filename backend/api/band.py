"""乐队资料与 Live 管理 — Band Portal（api_contract.md §3）。

- GET   /api/v1/band/me                  我的资料/设置（含草稿/已发布计数）
- PATCH /api/v1/band/me                  更新资料/QQ 绑定/成员/封面
- POST  /api/v1/band/lives               创建 Live（action: save_draft | publish）
- GET   /api/v1/band/lives               ?status=draft|published 过滤
- GET   /api/v1/band/lives/{id}          详情（含 setlist）
- PATCH /api/v1/band/lives/{id}          编辑（已发布内容 → 回 draft）
- DELETE /api/v1/band/lives/{id}         删除草稿
- POST  /api/v1/band/lives/{id}/publish  发布（→ published 直接上线）
- POST  /api/v1/band/lives/{id}/offline  下架（status+review_status→draft）

写操作全部走 SECURITY DEFINER 函数（V3），并在发布/下架/编辑时写 CDC，
保证 /full /sync 联动。列表/详情仅查询当前账号自建的 Live。
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.api.common import (
    _int_or_none,
    _pick_str,
    _price_str,
    db_execute,
    db_fetch,
    db_fetchrow,
    db_fetchval,
    get_db,
    load_live_with_venue,
    load_setlist,
    normalize_members,
    normalize_setlist,
    parse_date_value,
    parse_time_value,
    public_account,
    resolve_venue,
    serialize_band_live,
)
from backend.api.deps import get_current_band

logger = logging.getLogger("bandlive")

router = APIRouter()


def _validation(message: str) -> HTTPException:
    return HTTPException(
        status_code=400, detail={"code": "VALIDATION_ERROR", "message": message}
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "演出不存在"})


def _assert_publish_ready(title, livehouse_id, live_date, start_time) -> None:
    if not title:
        raise _validation("请填写 Live 名称")
    if not livehouse_id:
        raise _validation("请选择演出场地")
    if live_date is None:
        raise _validation("请选择演出日期")
    if start_time is None:
        raise _validation("请选择演出时间")


async def _fetch_my_live(conn, live_id: int, account_id: int):
    live = await load_live_with_venue(conn, live_id)
    if live is None or live["created_by"] != account_id:
        raise _not_found()
    return live


# ============================================================
# 我的资料 / 设置
# ============================================================
@router.get("/api/v1/band/me")
async def band_me(
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    row = await db_fetchrow(
        conn, "SELECT * FROM public.band_accounts WHERE id = $1", account["aid"]
    )
    if row is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "未登录或登录已过期"},
        )
    counts = await db_fetchrow(
        conn,
        """
        SELECT
            count(*) FILTER (WHERE review_status = 'published') AS published,
            count(*) FILTER (WHERE review_status <> 'published') AS draft
        FROM public.lives WHERE created_by = $1
        """,
        account["aid"],
    )
    return {
        "account": public_account(row),
        "band": {"id": row["id"], "name": row["band_name"], "qq_bind": row["qq_bind"] or None},
        "lives": {
            "draft": int(counts["draft"] or 0),
            "published": int(counts["published"] or 0),
        },
    }


@router.patch("/api/v1/band/me")
async def band_me_update(
    body: dict = Body(...),
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    band_name = body.get("band_name") if "band_name" in body else None
    intro = body.get("intro") if "intro" in body else None
    qq_bind = body.get("qq_bind") if "qq_bind" in body else None
    members = body.get("members") if isinstance(body.get("members"), list) else None
    cover_url = body.get("cover_url") if "cover_url" in body else None

    # safe_update_band_profile：NULL 字段 = 不修改
    await db_execute(
        conn,
        "SELECT public.safe_update_band_profile($1, $2, $3, $4)",
        account["aid"], band_name, intro, qq_bind,
    )
    if members is not None or cover_url is not None:
        await db_execute(
            conn,
            "SELECT public.safe_update_band_profile_extra($1, $2, $3)",
            account["aid"], cover_url, normalize_members(members),
        )

    row = await db_fetchrow(
        conn, "SELECT * FROM public.band_accounts WHERE id = $1", account["aid"]
    )
    return {
        "account": public_account(row),
        "band": {"id": row["id"], "name": row["band_name"], "qq_bind": row["qq_bind"] or None},
    }


# ============================================================
# 我的 Live
# ============================================================
@router.post("/api/v1/band/lives")
async def create_live(
    body: dict = Body(...),
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    action = "publish" if body.get("action") == "publish" else "save_draft"
    title = str(body.get("title") or "").strip()
    if not title:
        raise _validation("请填写 Live 名称")

    livehouse_id = _int_or_none(body.get("livehouse_id"))
    live_date = parse_date_value(body.get("live_date"))
    start_time = parse_time_value(body.get("start_time"))
    ticket_price = _price_str(body.get("ticket_price"))
    ticket_url = str(body.get("ticket_url") or "").strip()
    poster_image_url = str(body.get("poster_image_url") or "").strip()
    setlist = normalize_setlist(body.get("setlist"))
    kind = "coop" if body.get("kind") == "coop" else "normal"

    city = ""
    if livehouse_id:
        venue = await resolve_venue(conn, livehouse_id)
        if venue is None:
            raise _validation("所选场地不存在")
        city = venue["city"] or ""

    if action == "publish":
        _assert_publish_ready(title, livehouse_id, live_date, start_time)

    acc = await db_fetchrow(
        conn, "SELECT * FROM public.band_accounts WHERE id = $1", account["aid"]
    )
    band_names = [acc["band_name"] or acc["username"]]

    review_status = "published" if action == "publish" else "draft"
    status = "announced" if action == "publish" else "draft"

    live_id = await db_fetchval(
        conn,
        """
        SELECT public.safe_create_live(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        """,
        account["aid"], livehouse_id, live_date, start_time, title,
        ticket_price, ticket_url, poster_image_url, city, status, review_status,
        kind, band_names, setlist,
    )
    row = await load_live_with_venue(conn, live_id)
    setlist_rows = await load_setlist(conn, live_id)
    return {"live": serialize_band_live(
        row, setlist_rows, row["livehouse_name"] or "", row["owner_username"] or ""
    )}


@router.get("/api/v1/band/lives")
async def list_lives(
    status: str = "",
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    sql = """
        SELECT l.*, v.name AS livehouse_name, ba.username AS owner_username
        FROM public.lives l
        LEFT JOIN public.livehouses v ON v.id = l.livehouse_id
        LEFT JOIN public.band_accounts ba ON ba.id = l.created_by
        WHERE l.created_by = $1
    """
    params = [account["aid"]]
    if status == "published":
        sql += " AND l.review_status = 'published'"
    elif status == "draft":
        sql += " AND l.review_status <> 'published'"
    sql += " ORDER BY l.live_date ASC NULLS LAST, l.sort_start_time ASC, l.id ASC"
    rows = await db_fetch(conn, sql, *params)
    items = []
    for r in rows:
        sl = await load_setlist(conn, r["id"])
        items.append(serialize_band_live(
            r, sl, r["livehouse_name"] or "", r["owner_username"] or ""
        ))
    return {"items": items}


@router.get("/api/v1/band/lives/{live_id}")
async def get_live(
    live_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    live = await _fetch_my_live(conn, live_id, account["aid"])
    setlist = await load_setlist(conn, live_id)
    return {
        "live": serialize_band_live(
            live, setlist, live["livehouse_name"] or "", live["owner_username"] or ""
        ),
        "setlist": setlist,
    }


@router.patch("/api/v1/band/lives/{live_id}")
async def update_live(
    live_id: int,
    body: dict = Body(...),
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    live = await _fetch_my_live(conn, live_id, account["aid"])

    title = _pick_str(body, "title", live["title"])
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

    ticket_price = _price_str(body.get("ticket_price")) if "ticket_price" in body else live["ticket_price"]
    ticket_url = _pick_str(body, "ticket_url", live["ticket_url"])
    poster_image_url = _pick_str(body, "poster_image_url", live["poster_image_url"])
    if isinstance(body.get("setlist"), list):
        setlist = normalize_setlist(body["setlist"])
    else:
        setlist = await load_setlist(conn, live_id)

    kind = body.get("kind") if body.get("kind") in ("normal", "coop") else live["kind"]
    band_names = list(live["band_names"]) if isinstance(live["band_names"], list) else []

    # 编辑已发布内容 → 回 draft（需重新发布）；lifecycle status 保持不变
    review_status = "draft"
    status = live["status"] if live["status"] in ("draft", "announced", "on_sale", "completed", "cancelled") else "draft"

    await db_execute(
        conn,
        """
        SELECT public.safe_update_live(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
        )
        """,
        account["aid"], live_id, livehouse_id, live_date, start_time, title,
        ticket_price, ticket_url, poster_image_url, city, status, review_status,
        kind, band_names, setlist,
    )
    row = await load_live_with_venue(conn, live_id)
    setlist_rows = await load_setlist(conn, live_id)
    return {"live": serialize_band_live(
        row, setlist_rows, row["livehouse_name"] or "", row["owner_username"] or ""
    )}


@router.delete("/api/v1/band/lives/{live_id}")
async def delete_live(
    live_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    await _fetch_my_live(conn, live_id, account["aid"])
    await db_execute(conn, "SELECT public.safe_delete_live($1, $2)", account["aid"], live_id)
    return {"ok": True}


@router.post("/api/v1/band/lives/{live_id}/publish")
async def publish_live(
    live_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    live = await _fetch_my_live(conn, live_id, account["aid"])
    _assert_publish_ready(live["title"], live["livehouse_id"], live["live_date"], live["start_time"])
    await db_execute(conn, "SELECT public.safe_publish_live($1, $2)", account["aid"], live_id)
    row = await load_live_with_venue(conn, live_id)
    setlist_rows = await load_setlist(conn, live_id)
    return {"live": serialize_band_live(
        row, setlist_rows, row["livehouse_name"] or "", row["owner_username"] or ""
    )}


@router.post("/api/v1/band/lives/{live_id}/offline")
async def offline_live(
    live_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    live = await _fetch_my_live(conn, live_id, account["aid"])
    await db_execute(conn, "SELECT public.safe_offline_live($1, $2)", account["aid"], live_id)
    row = await load_live_with_venue(conn, live_id)
    setlist_rows = await load_setlist(conn, live_id)
    return {"live": serialize_band_live(
        row, setlist_rows, row["livehouse_name"] or "", row["owner_username"] or ""
    )}
