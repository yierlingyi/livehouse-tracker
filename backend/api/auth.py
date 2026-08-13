"""认证与账号（api_contract.md §2）。

- POST /api/v1/auth/register            乐队注册 → status=pending
- POST /api/v1/auth/login               乐队登录（pending 拒绝）
- POST /api/v1/auth/logout              注销（无状态 token，返回 ok）
- GET  /api/v1/auth/me                  当前账号
- POST /api/v1/admin/login              管理员登录
- POST /api/v1/admin/accounts           新增管理员（admin）
- GET  /api/v1/accounts/{username}/exists  拼盘邀请实时校验（仅 active 乐队）

鉴权：services/token_manager.sign_auth_token（v=2，24h）。
密码：services/passwords（PBKDF2-HMAC-SHA256，salt$hash）。
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.api.common import db_fetchrow, db_fetchval, get_db, public_account
from backend.api.deps import get_current_account, get_current_admin
from backend.services.passwords import hash_password, verify_password
from backend.services.token_manager import sign_auth_token

logger = logging.getLogger("bandlive")

router = APIRouter()


@router.post("/api/v1/auth/register")
async def register(
    body: dict = Body(...),
    conn=Depends(get_db),
):
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    band_name = str(body.get("band_name") or "").strip()

    if not username or not password or not band_name:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "请填写完整的账号、密码与乐队名称"},
        )

    account_id = await db_fetchval(
        conn,
        "SELECT public.safe_register_band($1, $2, $3)",
        username,
        hash_password(password),
        band_name,
    )
    row = await db_fetchrow(
        conn,
        "SELECT * FROM public.band_accounts WHERE id = $1",
        account_id,
    )
    return {"account": public_account(row)}


@router.post("/api/v1/auth/login")
async def login(
    body: dict = Body(...),
    conn=Depends(get_db),
):
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    row = await db_fetchrow(
        conn,
        "SELECT * FROM public.band_accounts WHERE username = $1",
        username,
    )
    if row is None or not verify_password(password, row["password_hash"]):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CREDENTIALS", "message": "账号或密码错误"},
        )
    if row["role"] != "band":
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CREDENTIALS", "message": "该账号为管理员账号，请使用管理员入口登录"},
        )
    if row["status"] == "pending":
        raise HTTPException(
            status_code=403,
            detail={"code": "PENDING", "message": "账号审核中，请等待管理员审核"},
        )
    if row["status"] != "active":
        raise HTTPException(
            status_code=403,
            detail={"code": "ACCOUNT_DISABLED", "message": "账号不可用，请联系管理员"},
        )
    token = sign_auth_token(row["id"], row["role"])
    return {"token": token, "account": public_account(row)}


@router.post("/api/v1/auth/logout")
async def logout():
    # 无状态 token：客户端丢弃即可。
    return {"ok": True}


@router.get("/api/v1/auth/me")
async def me(
    account=Depends(get_current_account),
    conn=Depends(get_db),
):
    row = await db_fetchrow(
        conn,
        "SELECT * FROM public.band_accounts WHERE id = $1",
        account["aid"],
    )
    if row is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "未登录或登录已过期"},
        )
    return {"account": public_account(row)}


@router.post("/api/v1/admin/login")
async def admin_login(
    body: dict = Body(...),
    conn=Depends(get_db),
):
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    row = await db_fetchrow(
        conn,
        "SELECT * FROM public.band_accounts WHERE username = $1",
        username,
    )
    if row is None or not verify_password(password, row["password_hash"]):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CREDENTIALS", "message": "账号或密码错误"},
        )
    if row["role"] != "admin":
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_CREDENTIALS", "message": "该账号为乐队账号，请使用乐队入口登录"},
        )
    token = sign_auth_token(row["id"], row["role"])
    return {"token": token, "account": public_account(row)}


@router.post("/api/v1/admin/accounts")
async def create_admin(
    body: dict = Body(...),
    account=Depends(get_current_admin),
    conn=Depends(get_db),
):
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "请填写用户名和密码"},
        )
    admin_id = await db_fetchval(
        conn,
        "SELECT public.safe_create_admin($1, $2)",
        username,
        hash_password(password),
    )
    return {"account": {"id": admin_id, "username": username, "role": "admin"}}


@router.get("/api/v1/accounts/{username}/exists")
async def account_exists(
    username: str,
    conn=Depends(get_db),
):
    """拼盘邀请实时校验：仅 active 乐队账号返回 true（公开 GET）。"""
    exists = await db_fetchval(
        conn,
        """
        SELECT EXISTS (
            SELECT 1 FROM public.band_accounts
            WHERE username = $1 AND role = 'band' AND status = 'active'
        )
        """,
        username,
    )
    return {"exists": bool(exists)}
