"""城市（运行时城市数据源，三端城市选择从此接口读取）。

- GET    /api/v1/cities            城市列表（公开，无鉴权）→ {"items":[{"id","name"}...]} 按 id 升序
- POST   /api/v1/admin/cities      新增城市（admin）→ {"id","name"}
- DELETE /api/v1/admin/cities/{id} 删除城市（admin）→ {"ok":true}

契约（docs/api_contract.md）：错误统一 {code, message}。
空名/重复在 Python 层直接按契约返回（VALIDATION_ERROR / CITIES_DUPLICATE）；
DB 函数（safe_cities_upsert/safe_cities_delete）RAISE EXCEPTION 仅作兜底，
经 common._DB_ERROR_MAP 映射为同一契约码，不外透 DB 原始错误码。
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.api.common import (
    db_execute,
    db_fetch,
    db_fetchrow,
    db_fetchval,
    get_db,
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
# 城市列表（公开，无鉴权）
# ============================================================
@router.get("/api/v1/cities")
async def list_cities(conn=Depends(get_db)):
    rows = await db_fetch(
        conn, "SELECT id, name FROM public.cities ORDER BY id ASC"
    )
    return {"items": [{"id": r["id"], "name": r["name"]} for r in rows]}


# ============================================================
# 新增城市（admin）
# ============================================================
@router.post("/api/v1/admin/cities")
async def create_city(
    body: dict = Body(...),
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    name = str(body.get("name") or "").strip()
    if not name:
        raise _validation("请填写城市名")
    existing = await db_fetchrow(
        conn, "SELECT id FROM public.cities WHERE name = $1", name
    )
    if existing is not None:
        raise HTTPException(
            status_code=400,
            detail={"code": "CITIES_DUPLICATE", "message": "该城市已存在"},
        )
    cid = await db_fetchval(
        conn, "SELECT public.safe_cities_upsert($1)", name
    )
    row = await db_fetchrow(
        conn, "SELECT id, name FROM public.cities WHERE id = $1", cid
    )
    return {"id": row["id"], "name": row["name"]}


# ============================================================
# 删除城市（admin）
# ============================================================
@router.delete("/api/v1/admin/cities/{city_id}")
async def delete_city(
    city_id: int,
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    existing = await db_fetchrow(
        conn, "SELECT id FROM public.cities WHERE id = $1", city_id
    )
    if existing is None:
        raise _not_found("城市不存在")
    await db_execute(conn, "SELECT public.safe_cities_delete($1)", city_id)
    return {"ok": True}
