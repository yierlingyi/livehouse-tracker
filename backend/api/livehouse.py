"""场地 Livehouse（api_contract.md §4.4）。

- GET    /api/v1/livehouses       场地列表（公开）→ {items:[{id,name,intro,image_url}]}
- GET    /api/v1/livehouses/{id}  场地详情（公开）
- POST   /api/v1/livehouses       新增场地（admin）
- PATCH  /api/v1/livehouses/{id}  编辑场地（admin）
- DELETE /api/v1/livehouses/{id}  删除场地（admin）

公开 GET 不鉴权；写操作要求管理员（get_current_admin）。
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.api.common import (
    _int_or_none,
    db_execute,
    db_fetch,
    db_fetchrow,
    db_fetchval,
    get_db,
    serialize_livehouse,
)
from backend.api.deps import get_current_admin

logger = logging.getLogger("bandlive")

router = APIRouter()


def _validation(message: str) -> HTTPException:
    return HTTPException(
        status_code=400, detail={"code": "VALIDATION_ERROR", "message": message}
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "场地不存在"})


def _to_params(body: dict) -> dict:
    name = str(body.get("name") or "").strip()
    if not name:
        raise _validation("请填写场地名称")
    return {
        "name": name,
        "city": str(body.get("city") or "青岛").strip(),
        "address": str(body.get("address") or "").strip(),
        "phone": str(body.get("phone") or "").strip(),
        "image_url": str(body.get("image_url") or "").strip(),
        "intro": str(body.get("intro") or "").strip(),
        "floorplan_url": str(body.get("floorplan_url") or "").strip(),
    }


@router.get("/api/v1/livehouses")
async def list_livehouses(conn=Depends(get_db)):
    rows = await db_fetch(
        conn,
        "SELECT * FROM public.livehouses ORDER BY id ASC",
    )
    return {
        "items": [
            {"id": r["id"], "name": r["name"], "intro": r["intro"] or "", "image_url": r["image_url"] or ""}
            for r in rows
        ]
    }


@router.get("/api/v1/livehouses/{livehouse_id}")
async def get_livehouse(livehouse_id: int, conn=Depends(get_db)):
    row = await db_fetchrow(
        conn, "SELECT * FROM public.livehouses WHERE id = $1", livehouse_id
    )
    if row is None:
        raise _not_found()
    return serialize_livehouse(row)


@router.post("/api/v1/livehouses")
async def create_livehouse(
    body: dict = Body(...),
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    p = _to_params(body)
    vid = await db_fetchval(
        conn,
        "SELECT public.safe_livehouse_upsert($1, $2, $3, $4, $5, $6, $7, $8)",
        None, p["name"], p["city"], p["address"], p["phone"],
        p["image_url"], p["intro"], p["floorplan_url"],
    )
    row = await db_fetchrow(
        conn, "SELECT * FROM public.livehouses WHERE id = $1", vid
    )
    return serialize_livehouse(row)


@router.patch("/api/v1/livehouses/{livehouse_id}")
async def update_livehouse(
    livehouse_id: int,
    body: dict = Body(...),
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    existing = await db_fetchrow(
        conn, "SELECT * FROM public.livehouses WHERE id = $1", livehouse_id
    )
    if existing is None:
        raise _not_found()
    merged = {
        "name": existing["name"],
        "city": existing["city"],
        "address": existing["address"],
        "phone": existing["phone"],
        "image_url": existing["image_url"],
        "intro": existing["intro"],
        "floorplan_url": existing["floorplan_url"],
    }
    for key in ("name", "city", "address", "phone", "image_url", "intro", "floorplan_url"):
        if key in body:
            merged[key] = body[key]
    p = _to_params(merged)
    await db_execute(
        conn,
        "SELECT public.safe_livehouse_upsert($1, $2, $3, $4, $5, $6, $7, $8)",
        livehouse_id, p["name"], p["city"], p["address"], p["phone"],
        p["image_url"], p["intro"], p["floorplan_url"],
    )
    row = await db_fetchrow(
        conn, "SELECT * FROM public.livehouses WHERE id = $1", livehouse_id
    )
    return serialize_livehouse(row)


@router.delete("/api/v1/livehouses/{livehouse_id}")
async def delete_livehouse(
    livehouse_id: int,
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    existing = await db_fetchrow(
        conn, "SELECT * FROM public.livehouses WHERE id = $1", livehouse_id
    )
    if existing is None:
        raise _not_found()
    await db_execute(conn, "SELECT public.safe_livehouse_delete($1)", livehouse_id)
    return {"ok": True}
