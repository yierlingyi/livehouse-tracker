"""内容管理 CMS（api_contract.md §4.6）。

- GET    /api/v1/cms/groups        同好群列表（公开）
- POST   /api/v1/cms/groups        新增（admin）
- PATCH  /api/v1/cms/groups/{id}   编辑（admin）
- DELETE /api/v1/cms/groups/{id}   删除（admin）
- GET    /api/v1/cms/sponsor       赞助（公开）
- PUT    /api/v1/cms/sponsor       更新（admin）
- GET    /api/v1/cms/project       项目声明（公开）
- PUT    /api/v1/cms/project       更新（admin）

公开 GET 不鉴权；写操作要求管理员。
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.api.common import (
    db_execute,
    db_fetch,
    db_fetchrow,
    db_fetchval,
    get_db,
    parse_jsonb,
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
# 同好群
# ============================================================
@router.get("/api/v1/cms/groups")
async def list_groups(conn=Depends(get_db)):
    rows = await db_fetch(
        conn,
        "SELECT id, city, platform, group_id FROM public.community_groups ORDER BY id ASC",
    )
    return {"items": [dict(r) for r in rows]}


@router.post("/api/v1/cms/groups")
async def create_group(
    body: dict = Body(...),
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    city = str(body.get("city") or "").strip()
    platform = str(body.get("platform") or "").strip()
    group_id = str(body.get("group_id") or "").strip()
    if not city or not platform or not group_id:
        raise _validation("请填写城市、平台与群号")
    gid = await db_fetchval(
        conn,
        "SELECT public.safe_cms_upsert_group($1, $2, $3, $4)",
        None, city, platform, group_id,
    )
    row = await db_fetchrow(
        conn,
        "SELECT id, city, platform, group_id FROM public.community_groups WHERE id = $1",
        gid,
    )
    return dict(row)


@router.patch("/api/v1/cms/groups/{group_id}")
async def update_group(
    group_id: int,
    body: dict = Body(...),
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    existing = await db_fetchrow(
        conn,
        "SELECT * FROM public.community_groups WHERE id = $1",
        group_id,
    )
    if existing is None:
        raise _not_found("群组不存在")
    city = str(body.get("city") if "city" in body else existing["city"] or "").strip()
    platform = str(body.get("platform") if "platform" in body else existing["platform"] or "").strip()
    group_id_val = str(body.get("group_id") if "group_id" in body else existing["group_id"] or "").strip()
    if not city or not platform or not group_id_val:
        raise _validation("请填写城市、平台与群号")
    await db_execute(
        conn,
        "SELECT public.safe_cms_upsert_group($1, $2, $3, $4)",
        group_id, city, platform, group_id_val,
    )
    row = await db_fetchrow(
        conn,
        "SELECT id, city, platform, group_id FROM public.community_groups WHERE id = $1",
        group_id,
    )
    return dict(row)


@router.delete("/api/v1/cms/groups/{group_id}")
async def delete_group(
    group_id: int,
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    existing = await db_fetchrow(
        conn,
        "SELECT * FROM public.community_groups WHERE id = $1",
        group_id,
    )
    if existing is None:
        raise _not_found("群组不存在")
    await db_execute(conn, "SELECT public.safe_cms_delete_group($1)", group_id)
    return {"ok": True}


# ============================================================
# 赞助
# ============================================================
@router.get("/api/v1/cms/sponsor")
async def get_sponsor(conn=Depends(get_db)):
    row = await db_fetchrow(
        conn, "SELECT * FROM public.sponsor_content WHERE id = 1"
    )
    if row is None:
        return {"thanks_text": "", "qr_image_urls": []}
    return {
        "thanks_text": row["thanks_text"] or "",
        "qr_image_urls": parse_jsonb(row["qr_image_urls"]),
    }


@router.put("/api/v1/cms/sponsor")
async def update_sponsor(
    body: dict = Body(...),
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    thanks_text = str(body.get("thanks_text") or "").strip()
    qr = body.get("qr_image_urls")
    qr = qr if isinstance(qr, list) else []
    qr = [str(x) for x in qr if x]
    await db_execute(
        conn,
        "SELECT public.safe_cms_upsert_sponsor($1, $2)",
        thanks_text, qr,
    )
    return {"thanks_text": thanks_text, "qr_image_urls": qr}


# ============================================================
# 项目声明
# ============================================================
@router.get("/api/v1/cms/project")
async def get_project(conn=Depends(get_db)):
    row = await db_fetchrow(
        conn, "SELECT * FROM public.project_declaration WHERE id = 1"
    )
    if row is None:
        return {"intro": "", "github_url": "", "author": "", "license": ""}
    return {
        "intro": row["intro"] or "",
        "github_url": row["github_url"] or "",
        "author": row["author"] or "",
        "license": row["license"] or "",
    }


@router.put("/api/v1/cms/project")
async def update_project(
    body: dict = Body(...),
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    intro = str(body.get("intro") or "").strip()
    github_url = str(body.get("github_url") or "").strip()
    author = str(body.get("author") or "").strip()
    license_ = str(body.get("license") or "").strip()
    await db_execute(
        conn,
        "SELECT public.safe_cms_upsert_project($1, $2, $3, $4)",
        intro, github_url, author, license_,
    )
    return {"intro": intro, "github_url": github_url, "author": author, "license": license_}
