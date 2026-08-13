"""公开演出详情（api_contract.md §4.4）。

- GET /api/v1/lives/{id} 演出详情（公开，含场地信息+setlist+海报）
     → {live, venue, setlist, poster_image_url}

公开接口，无需鉴权。仅返回已发布（review_status='published'）的演出，
避免草稿/下架内容泄露。`/lives/full`、`/lives/sync` 由既有路由先注册且为
字面路径，不受 `/{id}`（int 类型转换）影响。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.common import (
    _iso_d,
    _dt_iso,
    db_fetchrow,
    get_db,
    load_setlist,
    parse_jsonb,
    serialize_livehouse,
)

logger = logging.getLogger("bandlive")

router = APIRouter()


def _serialize_public_live(row) -> dict:
    return {
        "id": row["id"],
        "livehouse_id": row["livehouse_id"],
        "live_date": _iso_d(row["live_date"]),
        "start_time": _iso_d(row["start_time"]),
        "sort_start_time": _iso_d(row["sort_start_time"]),
        "title": row["title"],
        "ticket_price": row["ticket_price"],
        "ticket_url": row["ticket_url"] or "",
        "poster_image_url": row["poster_image_url"] or "",
        "city": row["city"] or "",
        "band_names": parse_jsonb(row["band_names"]),
        "status": row["status"],
        "updated_at": _dt_iso(row["updated_at"]),
    }


@router.get("/api/v1/lives/{live_id}")
async def get_live_detail(live_id: int, conn=Depends(get_db)):
    row = await db_fetchrow(
        conn,
        """
        SELECT l.*, v.name AS livehouse_name, v.address AS livehouse_address,
               v.phone AS livehouse_phone
        FROM public.lives l
        LEFT JOIN public.livehouses v ON v.id = l.livehouse_id
        WHERE l.id = $1 AND l.review_status = 'published'
        """,
        live_id,
    )
    if row is None:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "演出不存在"}
        )
    setlist = await load_setlist(conn, live_id)
    venue = None
    if row["livehouse_id"]:
        venue_row = await db_fetchrow(
            conn, "SELECT * FROM public.livehouses WHERE id = $1", row["livehouse_id"]
        )
        if venue_row is not None:
            venue = serialize_livehouse(venue_row)
    return {
        "live": _serialize_public_live(row),
        "venue": venue,
        "setlist": setlist,
        "poster_image_url": row["poster_image_url"] or "",
    }
