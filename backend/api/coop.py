"""拼盘 Co-op（api_contract.md §4）。

状态机：invited → agreed / rejected / exit_requested → removed

- POST   /api/v1/coop/events                    创建拼盘（可存草稿）
- GET    /api/v1/coop/events                    我关联的所有拼盘+实时状态
- GET    /api/v1/coop/events/invites            我收到的邀请（字面路由先注册）
- GET    /api/v1/coop/events/{id}               拼盘详情（含 participants + 计数）
- PATCH  /api/v1/coop/events/{id}               发起方编辑/存草稿
- DELETE /api/v1/coop/events/{id}               发起方删草稿（仅 draft）
- POST   /api/v1/coop/events/{id}/invites       追加邀请（发起方）
- POST   /api/v1/coop/events/{id}/invites/{invite_id}/accept        同意
- POST   /api/v1/coop/events/{id}/invites/{invite_id}/reject        拒绝
- PATCH  /api/v1/coop/events/{id}/invites/{invite_id}/songs         改本队曲目
- POST   /api/v1/coop/events/{id}/invites/{invite_id}/revoke        撤销同意
- POST   /api/v1/coop/events/{id}/invites/{invite_id}/exit-request  申请退出
- POST   /api/v1/coop/events/{id}/invites/{invite_id}/approve-exit  发起方审批退出
- POST   /api/v1/coop/events/{id}/offline       发起方下架拼盘

写操作全部走 V3 SECURITY DEFINER 函数；拼盘 live 下架/发布会写 CDC。
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.api.common import (
    _int_or_none,
    _price_str,
    db_execute,
    db_fetch,
    db_fetchrow,
    get_db,
    load_setlist,
    normalize_songs,
    parse_date_value,
    parse_time_value,
    parse_jsonb,
    resolve_venue,
)
from backend.api.deps import get_current_band

logger = logging.getLogger("bandlive")

router = APIRouter()


def _validation(message: str) -> HTTPException:
    return HTTPException(
        status_code=400, detail={"code": "VALIDATION_ERROR", "message": message}
    )


def _not_found(message: str = "拼盘不存在") -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": message})


def _forbidden(message: str = "无权限操作") -> HTTPException:
    return HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": message})


def _invite_public(row) -> dict:
    return {
        "invite_id": row["invite_id"],
        "username": row["username"],
        "band_name": row["band_name"],
        "invite_status": row["invite_status"],
        "songs": parse_jsonb(row["songs"]),
        "is_initiator": bool(row["is_initiator"]),
    }


async def _load_event_row(conn, event_id: int):
    return await db_fetchrow(
        conn,
        """
        SELECT e.id, e.status, e.live_id, e.initiator_account_id,
               l.title, l.live_date, l.start_time, l.ticket_price,
               l.poster_image_url, l.livehouse_id, l.city,
               v.name AS venue_name, v.address AS venue_address,
               ba.username AS initiator_username, ba.band_name AS initiator_band
        FROM public.coop_events e
        JOIN public.lives l ON l.id = e.live_id
        LEFT JOIN public.livehouses v ON v.id = l.livehouse_id
        JOIN public.band_accounts ba ON ba.id = e.initiator_account_id
        WHERE e.id = $1
        """,
        event_id,
    )


def _public_event(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "live_date": row["live_date"].isoformat() if row["live_date"] else None,
        "status": row["status"],
        "initiator_band": row["initiator_band"] or row["initiator_username"],
        "initiator_username": row["initiator_username"],
        "venue_name": row["venue_name"] or "",
        "venue_address": row["venue_address"] or "",
        "start_time": row["start_time"].isoformat() if row["start_time"] else None,
        "ticket_price": row["ticket_price"],
        "poster_image_url": row["poster_image_url"] or "",
    }


async def _load_participants(conn, event_id: int):
    rows = await db_fetch(
        conn,
        """
        SELECT i.id AS invite_id, i.band_account_id, i.invite_status, i.songs,
               ba.username, ba.band_name,
               (i.band_account_id = (SELECT initiator_account_id FROM public.coop_events WHERE id = i.event_id)) AS is_initiator
        FROM public.coop_invites i
        JOIN public.band_accounts ba ON ba.id = i.band_account_id
        WHERE i.event_id = $1
        ORDER BY i.id ASC
        """,
        event_id,
    )
    return [
        {
            "invite_id": r["invite_id"],
            "username": r["username"],
            "band_name": r["band_name"],
            "invite_status": r["invite_status"],
            "songs": parse_jsonb(r["songs"]),
            "is_initiator": bool(r["is_initiator"]),
        }
        for r in rows
    ]


async def _load_invite(conn, event_id: int, invite_id: int):
    row = await db_fetchrow(
        conn,
        """
        SELECT i.id AS invite_id, i.band_account_id, i.invite_status, i.songs,
               ba.username, ba.band_name,
               (i.band_account_id = (SELECT initiator_account_id FROM public.coop_events WHERE id = i.event_id)) AS is_initiator
        FROM public.coop_invites i
        JOIN public.band_accounts ba ON ba.id = i.band_account_id
        WHERE i.event_id = $1 AND i.id = $2
        """,
        event_id, invite_id,
    )
    if row is None:
        raise _not_found("邀请不存在")
    return _invite_public(row)


def _normalize_invites(value) -> list:
    """[{username, songs?}] 归一：仅保留含 username 的条目。"""
    if not isinstance(value, list):
        return []
    out = []
    for it in value:
        if isinstance(it, dict) and str(it.get("username") or "").strip():
            out.append({
                "username": str(it["username"]).strip(),
                "songs": normalize_songs(it.get("songs")),
            })
    return out


# ============================================================
# 创建拼盘
# ============================================================
@router.post("/api/v1/coop/events")
async def create_event(
    body: dict = Body(...),
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    action = "publish" if body.get("action") == "publish" else "save_draft"
    title = str(body.get("title") or "").strip()
    if not title:
        raise _validation("请填写拼盘名称")
    livehouse_id = _int_or_none(body.get("livehouse_id"))
    live_date = parse_date_value(body.get("live_date"))
    start_time = parse_time_value(body.get("start_time"))
    ticket_price = _price_str(body.get("ticket_price"))
    poster_image_url = str(body.get("poster_image_url") or "").strip()
    own_songs = normalize_songs(body.get("own_songs"))
    invites = _normalize_invites(body.get("invites"))

    city = ""
    if livehouse_id:
        venue = await resolve_venue(conn, livehouse_id)
        if venue is None:
            raise _validation("所选场地不存在")
        city = venue["city"] or ""

    if action == "publish":
        if not title:
            raise _validation("请填写拼盘名称")
        if not livehouse_id:
            raise _validation("请选择演出场地")
        if live_date is None:
            raise _validation("请选择演出日期")
        if start_time is None:
            raise _validation("请选择演出时间")

    event_id = await db_fetchrow(
        conn,
        """
        SELECT public.safe_coop_create_event(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
        ) AS id
        """,
        account["aid"], livehouse_id, live_date, start_time, title,
        ticket_price, poster_image_url, city, action, own_songs, invites,
    )
    event_id = event_id["id"]
    row = await _load_event_row(conn, event_id)
    return _public_event(row)


# ============================================================
# 我关联的拼盘（含实时状态）
# ============================================================
@router.get("/api/v1/coop/events")
async def list_events(
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    rows = await db_fetch(
        conn,
        """
        SELECT e.id, e.status, e.live_id, e.initiator_account_id,
               l.title, l.live_date,
               i.id AS invite_id, i.band_account_id, i.invite_status, i.songs,
               ba.username, ba.band_name
        FROM public.coop_events e
        JOIN public.lives l ON l.id = e.live_id
        JOIN public.coop_invites i ON i.event_id = e.id
        JOIN public.band_accounts ba ON ba.id = i.band_account_id
        WHERE i.band_account_id = $1
        ORDER BY e.id DESC, i.id ASC
        """,
        account["aid"],
    )
    events: dict = {}
    order = []
    for r in rows:
        eid = r["id"]
        if eid not in events:
            events[eid] = {
                "id": eid,
                "title": r["title"],
                "live_date": r["live_date"].isoformat() if r["live_date"] else None,
                "status": r["status"],
                "invites": [],
            }
            order.append(eid)
        events[eid]["invites"].append({
            "band_name": r["band_name"],
            "username": r["username"],
            "invite_status": r["invite_status"],
            "songs": parse_jsonb(r["songs"]),
            "is_me": r["band_account_id"] == account["aid"],
            "is_initiator": r["band_account_id"] == r["initiator_account_id"],
        })
    return {"items": [events[eid] for eid in order]}


# ============================================================
# 我收到的邀请（字面路由必须先于 /{id} 注册）
# ============================================================
@router.get("/api/v1/coop/events/invites")
async def list_invites(
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    rows = await db_fetch(
        conn,
        """
        SELECT e.id AS event_id, l.title, l.live_date,
               v.address AS venue_address,
               i.songs AS assigned_songs, i.invite_status,
               ba.band_name AS initiator_band
        FROM public.coop_events e
        JOIN public.lives l ON l.id = e.live_id
        LEFT JOIN public.livehouses v ON v.id = l.livehouse_id
        JOIN public.coop_invites i ON i.event_id = e.id
        JOIN public.band_accounts ba ON ba.id = e.initiator_account_id
        WHERE i.band_account_id = $1
          AND i.band_account_id <> e.initiator_account_id
          AND i.invite_status IN ('invited', 'agreed')
        ORDER BY e.id DESC
        """,
        account["aid"],
    )
    items = [
        {
            "event_id": r["event_id"],
            "initiator_band": r["initiator_band"],
            "title": r["title"],
            "live_date": r["live_date"].isoformat() if r["live_date"] else None,
            "venue_address": r["venue_address"] or "",
            "assigned_songs": parse_jsonb(r["assigned_songs"]),
            "invite_status": r["invite_status"],
        }
        for r in rows
    ]
    return {"items": items}


# ============================================================
# 拼盘详情
# ============================================================
@router.get("/api/v1/coop/events/{event_id}")
async def get_event(
    event_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    row = await _load_event_row(conn, event_id)
    if row is None:
        raise _not_found()
    participants = await _load_participants(conn, event_id)
    agreed = sum(1 for p in participants if p["invite_status"] == "agreed")
    rejected = sum(1 for p in participants if p["invite_status"] == "rejected")
    exit_req = sum(1 for p in participants if p["invite_status"] == "exit_requested")
    detail = _public_event(row)
    detail["participants"] = participants
    detail["agreed_count"] = agreed
    detail["total_count"] = len(participants)
    detail["rejected_count"] = rejected
    detail["exit_requested_count"] = exit_req
    return detail


# ============================================================
# 发起方编辑 / 存草稿
# ============================================================
@router.patch("/api/v1/coop/events/{event_id}")
async def update_event(
    event_id: int,
    body: dict = Body(...),
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    row = await _load_event_row(conn, event_id)
    if row is None:
        raise _not_found()
    if row["initiator_account_id"] != account["aid"]:
        raise _forbidden("仅发起方可编辑")

    action = "publish" if body.get("action") == "publish" else "save_draft"
    title = str(body.get("title") if "title" in body else row["title"] or "").strip()
    if not title:
        title = row["title"]
    if "livehouse_id" in body:
        livehouse_id = _int_or_none(body.get("livehouse_id"))
        city = ""
        if livehouse_id:
            venue = await resolve_venue(conn, livehouse_id)
            if venue is None:
                raise _validation("所选场地不存在")
            city = venue["city"] or ""
    else:
        livehouse_id = row["livehouse_id"]
        city = row["city"] or ""
    live_date = parse_date_value(body.get("live_date")) if body.get("live_date") else row["live_date"]
    if "start_time" in body:
        start_time = parse_time_value(body.get("start_time"))
    else:
        start_time = row["start_time"]
    ticket_price = _price_str(body.get("ticket_price")) if "ticket_price" in body else row["ticket_price"]
    poster_image_url = str(body["poster_image_url"]).strip() if "poster_image_url" in body else row["poster_image_url"]
    own_songs = normalize_songs(body.get("own_songs")) if "own_songs" in body else None
    invites = _normalize_invites(body.get("invites")) if "invites" in body else None

    if action == "publish":
        if not title:
            raise _validation("请填写拼盘名称")
        if not livehouse_id:
            raise _validation("请选择演出场地")
        if live_date is None:
            raise _validation("请选择演出日期")
        if start_time is None:
            raise _validation("请选择演出时间")

    await db_execute(
        conn,
        """
        SELECT public.safe_coop_update_event(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        )
        """,
        account["aid"], event_id, livehouse_id, live_date, start_time, title,
        ticket_price, poster_image_url, city, action, own_songs, invites,
    )
    row = await _load_event_row(conn, event_id)
    return _public_event(row)


# ============================================================
# 发起方删草稿
# ============================================================
@router.delete("/api/v1/coop/events/{event_id}")
async def delete_event(
    event_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    await db_execute(
        conn,
        "SELECT public.safe_coop_delete_event($1, $2)",
        event_id, account["aid"],
    )
    return {"ok": True}


# ============================================================
# 追加邀请
# ============================================================
@router.post("/api/v1/coop/events/{event_id}/invites")
async def add_invite(
    event_id: int,
    body: dict = Body(...),
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    username = str(body.get("username") or "").strip()
    if not username:
        raise _validation("请填写乐队账号")
    songs = normalize_songs(body.get("songs"))
    await db_execute(
        conn,
        "SELECT public.safe_coop_add_invite($1, $2, $3, $4)",
        event_id, account["aid"], username, songs,
    )
    row = await _load_event_row(conn, event_id)
    return _public_event(row)


# ============================================================
# 状态动作
# ============================================================
@router.post("/api/v1/coop/events/{event_id}/invites/{invite_id}/accept")
async def accept_invite(
    event_id: int,
    invite_id: int,
    body: dict = Body(...),
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    songs = normalize_songs(body.get("songs")) if body else None
    await db_execute(
        conn,
        "SELECT public.safe_coop_accept_invite($1, $2, $3, $4)",
        event_id, invite_id, account["aid"], songs,
    )
    return {"invite": await _load_invite(conn, event_id, invite_id)}


@router.post("/api/v1/coop/events/{event_id}/invites/{invite_id}/reject")
async def reject_invite(
    event_id: int,
    invite_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    await db_execute(
        conn,
        "SELECT public.safe_coop_reject_invite($1, $2, $3)",
        event_id, invite_id, account["aid"],
    )
    return {"invite": await _load_invite(conn, event_id, invite_id)}


@router.patch("/api/v1/coop/events/{event_id}/invites/{invite_id}/songs")
async def update_songs(
    event_id: int,
    invite_id: int,
    body: dict = Body(...),
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    songs = normalize_songs(body.get("songs")) if body else []
    await db_execute(
        conn,
        "SELECT public.safe_coop_update_songs($1, $2, $3, $4)",
        event_id, invite_id, account["aid"], songs,
    )
    return {"invite": await _load_invite(conn, event_id, invite_id)}


@router.post("/api/v1/coop/events/{event_id}/invites/{invite_id}/revoke")
async def revoke_agree(
    event_id: int,
    invite_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    await db_execute(
        conn,
        "SELECT public.safe_coop_revoke($1, $2, $3)",
        event_id, invite_id, account["aid"],
    )
    return {"invite": await _load_invite(conn, event_id, invite_id)}


@router.post("/api/v1/coop/events/{event_id}/invites/{invite_id}/exit-request")
async def exit_request(
    event_id: int,
    invite_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    await db_execute(
        conn,
        "SELECT public.safe_coop_exit_request($1, $2, $3)",
        event_id, invite_id, account["aid"],
    )
    return {"invite": await _load_invite(conn, event_id, invite_id)}


@router.post("/api/v1/coop/events/{event_id}/invites/{invite_id}/approve-exit")
async def approve_exit(
    event_id: int,
    invite_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    await db_execute(
        conn,
        "SELECT public.safe_coop_approve_exit($1, $2, $3)",
        event_id, invite_id, account["aid"],
    )
    return {"invite": await _load_invite(conn, event_id, invite_id)}


# ============================================================
# 发起方下架拼盘
# ============================================================
@router.post("/api/v1/coop/events/{event_id}/offline")
async def offline_event(
    event_id: int,
    account=Depends(get_current_band),
    conn=Depends(get_db),
):
    await db_execute(
        conn,
        "SELECT public.safe_coop_offline_event($1, $2)",
        event_id, account["aid"],
    )
    row = await _load_event_row(conn, event_id)
    return _public_event(row)
