"""乐队资料（公开只读，api_contract.md §4.4）。

- GET /api/v1/bands      列表 → {items:[{id,name,cover_url}]}
- GET /api/v1/bands/{id} 详情 → {id,name,intro,cover_url,members:[{name,role?}]}

公开接口，无需鉴权。仅返回 active 乐队账号（pending/rejected/disabled 隐藏）。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.common import (
    db_fetch,
    db_fetchrow,
    get_db,
    serialize_band_detail,
    serialize_band_item,
)

logger = logging.getLogger("bandlive")

router = APIRouter()


@router.get("/api/v1/bands")
async def list_bands(conn=Depends(get_db)):
    rows = await db_fetch(
        conn,
        """
        SELECT * FROM public.band_accounts
        WHERE role = 'band' AND status = 'active'
        ORDER BY id ASC
        """,
    )
    return {"items": [serialize_band_item(r) for r in rows]}


@router.get("/api/v1/bands/{band_id}")
async def get_band(band_id: int, conn=Depends(get_db)):
    row = await db_fetchrow(
        conn,
        """
        SELECT * FROM public.band_accounts
        WHERE id = $1 AND role = 'band' AND status = 'active'
        """,
        band_id,
    )
    if row is None:
        raise HTTPException(
            status_code=404, detail={"code": "NOT_FOUND", "message": "乐队不存在"}
        )
    return serialize_band_detail(row)
