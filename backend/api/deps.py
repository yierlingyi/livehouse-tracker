"""鉴权依赖（Band Portal / Admin Console）。

Bearer token（v=2，见 services/token_manager.verify_auth_token）：
    - get_current_account → {aid, role}，401 未登录/失效
    - get_current_band      → 仅乐队账号，否则 403
    - get_current_admin     → 仅管理员，否则 403

错误统一 {code, message}（error_handler 将 dict detail 原样透出）。
"""

from typing import Any, Dict

from fastapi import Header, HTTPException

from backend.services.token_manager import (
    AuthTokenExpiredError,
    InvalidAuthTokenError,
    verify_auth_token,
)

UNAUTHORIZED = {"code": "UNAUTHORIZED", "message": "未登录或登录已过期"}
FORBIDDEN = {"code": "FORBIDDEN", "message": "无权限操作"}


def _parse_bearer(authorization: str) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail=UNAUTHORIZED)
    return token.strip()


async def get_current_account(
    authorization: str = Header(None),
) -> Dict[str, Any]:
    token = _parse_bearer(authorization)
    try:
        return verify_auth_token(token)
    except InvalidAuthTokenError:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED)
    except AuthTokenExpiredError:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "登录已过期，请重新登录"},
        )


async def get_current_band(
    authorization: str = Header(None),
) -> Dict[str, Any]:
    account = await get_current_account(authorization)
    if account["role"] != "band":
        raise HTTPException(status_code=403, detail=FORBIDDEN)
    return account


async def get_current_admin(
    authorization: str = Header(None),
) -> Dict[str, Any]:
    account = await get_current_account(authorization)
    if account["role"] != "admin":
        raise HTTPException(status_code=403, detail=FORBIDDEN)
    return account
