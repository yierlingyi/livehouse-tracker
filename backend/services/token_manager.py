"""
Token Manager — 签名 keyset page token（V4.4 §9.1）

Token 载荷（v + 8 个业务字段，共 9 个字段）：
{
  "v": 1,
  "city": "Tokyo",
  "scope_start_date": "2026-08-12",
  "scope_end_date": "2026-11-10",
  "snapshot_cursor": "123456",
  "last_date": "2026-09-15",
  "last_time": "23:59:59",
  "last_id": 9988,
  "exp": 1786600000
}

约束：
- last_time 永远使用生成列 sort_start_time，禁止使用原始 start_time。
- Token 过期建议 30 分钟（可通过 ttl_minutes 调整）。
- 使用 HMAC-SHA256 签名，base64(urlsafe) 编码。
- 校验失败抛 ValueError 子类 InvalidPageTokenError（API 层映射 400 INVALID_PAGE_TOKEN）。
- 过期抛 ValueError 子类 PageTokenExpiredError（API 层映射 409 FULL_PAGE_TOKEN_EXPIRED）。

密钥由 config.py / main.py 通过 set_secret() 注入，禁止硬编码。
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

__all__ = [
    "set_secret",
    "sign_token",
    "verify_token",
    "build_first_page_token",
    "InvalidPageTokenError",
    "PageTokenExpiredError",
    "DEFAULT_TTL_MINUTES",
    "sign_auth_token",
    "verify_auth_token",
    "InvalidAuthTokenError",
    "AuthTokenExpiredError",
    "AUTH_TOKEN_TTL_SECONDS",
]

TOKEN_VERSION = 1
DEFAULT_TTL_MINUTES = 30

# 认证 token（v=2）：短时有效，载荷 {v:2, aid, role, exp}。
AUTH_TOKEN_VERSION = 2
AUTH_TOKEN_TTL_SECONDS = 24 * 3600

# Token 必填字段（openapi 契约 components.schemas.PageToken.required）
_REQUIRED_FIELDS = (
    "city",
    "scope_start_date",
    "scope_end_date",
    "snapshot_cursor",
    "last_date",
    "last_time",
    "last_id",
    "exp",
)

_SECRET: Optional[bytes] = None


class InvalidPageTokenError(ValueError):
    """Token 非法：格式错误 / 签名不匹配 / v 非 1 / 字段缺失或类型错误。"""


class PageTokenExpiredError(ValueError):
    """Token 已过期（exp < 当前时间）。"""


class InvalidAuthTokenError(ValueError):
    """认证 token 非法：格式错误 / 签名不匹配 / v 非 2 / 字段缺失或类型错误。"""


class AuthTokenExpiredError(ValueError):
    """认证 token 已过期（exp < 当前时间）。"""


def set_secret(secret: str) -> None:
    """设置 HMAC 签名密钥。secret 由环境/KMS 注入，禁止硬编码。"""
    global _SECRET
    if not secret:
        raise ValueError("token secret must not be empty")
    _SECRET = secret.encode("utf-8")


def _require_secret() -> bytes:
    if _SECRET is None:
        raise RuntimeError(
            "token secret not set; call token_manager.set_secret() at startup"
        )
    return _SECRET


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64url_decode(data: str) -> bytes:
    # 容忍客户端去掉 padding 的情况（urlsafe base64 的 '=' 可以省略）
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _sign(payload_bytes: bytes) -> bytes:
    secret = _require_secret()
    return hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest().encode("ascii")


def sign_token(payload: Dict[str, Any]) -> str:
    """签名 token 载荷并编码为 base64。

    返回格式：urlsafe-base64( json(payload) + "." + hex(hmac_sha256) )
    """
    payload_bytes = json.dumps(
        payload, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    sig = _sign(payload_bytes)
    return _b64url_encode(payload_bytes + b"." + sig)


def verify_token(token_str: str) -> Dict[str, Any]:
    """验证并解码 token，返回载荷 dict。

    异常：
        InvalidPageTokenError — 格式错误 / 签名不匹配 / v 非 1 / 字段缺失或类型错误
        PageTokenExpiredError — exp 已过

    验签顺序（安全）：
        1. base64 解码
        2. HMAC 验签（先验签，绝不信任未签名载荷）
        3. 解析 JSON 载荷
        4. 校验 v / 必填字段 / 字段类型
        5. 校验过期
    """
    if not isinstance(token_str, str) or not token_str:
        raise InvalidPageTokenError("INVALID_PAGE_TOKEN")

    try:
        decoded = _b64url_decode(token_str)
    except Exception:
        raise InvalidPageTokenError("INVALID_PAGE_TOKEN")

    if b"." not in decoded:
        raise InvalidPageTokenError("INVALID_PAGE_TOKEN")

    payload_bytes, sig_bytes = decoded.rsplit(b".", 1)
    if not payload_bytes or not sig_bytes:
        raise InvalidPageTokenError("INVALID_PAGE_TOKEN")

    # 1) 先验签，防止伪造 / 重放 / 载荷注入
    expected_sig = _sign(payload_bytes)
    if not hmac.compare_digest(sig_bytes, expected_sig):
        raise InvalidPageTokenError("INVALID_PAGE_TOKEN")

    # 2) 签名通过后才解析载荷
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise InvalidPageTokenError("INVALID_PAGE_TOKEN")

    if not isinstance(payload, dict):
        raise InvalidPageTokenError("INVALID_PAGE_TOKEN")

    # 3) 校验版本
    if payload.get("v") != TOKEN_VERSION:
        raise InvalidPageTokenError("INVALID_PAGE_TOKEN")

    # 4) 校验必填字段
    if any(key not in payload for key in _REQUIRED_FIELDS):
        raise InvalidPageTokenError("INVALID_PAGE_TOKEN")

    # 5) 校验字段类型，防止类型混淆（如 last_id 传字符串）
    if (
        not isinstance(payload["city"], str)
        or not isinstance(payload["scope_start_date"], str)
        or not isinstance(payload["scope_end_date"], str)
        or not isinstance(payload["snapshot_cursor"], str)
        or not isinstance(payload["last_date"], str)
        or not isinstance(payload["last_time"], str)
        or not isinstance(payload["last_id"], int)
        or not isinstance(payload["exp"], int)
    ):
        raise InvalidPageTokenError("INVALID_PAGE_TOKEN")

    # 6) 校验过期
    if payload["exp"] < int(time.time()):
        raise PageTokenExpiredError("FULL_PAGE_TOKEN_EXPIRED")

    return payload


def build_first_page_token(
    city: str,
    scope_start_date: str,
    scope_end_date: str,
    snapshot_cursor: int,
    last_row: Dict[str, Any],
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> str:
    """从本页结果构建下一页 token。

    参数：
        city: 客户端 scope 城市。
        scope_start_date / scope_end_date: 第一页生成的固定 scope（后续页沿用）。
        snapshot_cursor: 第一页事务中读取的 sync_version_counter.version。
        last_row: 本页最后一行，必须包含 live_date / sort_start_time / id。
                  last_row["sort_start_time"] 必须来自生成列，禁止传入原始 start_time。
        ttl_minutes: token 有效分钟数，默认 30。

    返回：签名 base64 token 字符串。
    """
    if ttl_minutes <= 0:
        raise ValueError("ttl_minutes must be positive")

    payload = {
        "v": TOKEN_VERSION,
        "city": city,
        "scope_start_date": str(scope_start_date),
        "scope_end_date": str(scope_end_date),
        "snapshot_cursor": str(snapshot_cursor),
        "last_date": str(last_row["live_date"]),
        # 必须使用生成列 sort_start_time，绝不能用原始 start_time。
        # sort_start_time 对 start_time IS NULL 的行恒为 '23:59:59'，永不为 NULL，
        # 因此 next_token.last_time 非 NULL（V4.4 §15.1 验收）。
        "last_time": str(last_row["sort_start_time"]),
        "last_id": int(last_row["id"]),
        "exp": int(time.time()) + ttl_minutes * 60,
    }
    return sign_token(payload)


def sign_auth_token(
    account_id: int, role: str, ttl_seconds: int = AUTH_TOKEN_TTL_SECONDS
) -> str:
    """签发认证 token（v=2，HMAC-SHA256 签名）。

    载荷：{v:2, aid: 账号 id, role: 'band'|'admin', exp}。
    复用 v=1 的签名/编码路径，仅版本与字段不同。
    """
    payload = {
        "v": AUTH_TOKEN_VERSION,
        "aid": int(account_id),
        "role": str(role),
        "exp": int(time.time()) + ttl_seconds,
    }
    return sign_token(payload)


def verify_auth_token(token_str: str) -> Dict[str, Any]:
    """验证认证 token，返回载荷 dict {aid, role, exp}。

    异常：
        InvalidAuthTokenError — 格式错误 / 签名不匹配 / v 非 2 / 字段缺失或类型错误
        AuthTokenExpiredError — exp 已过

    验签顺序与 v=1 一致：先验签，再解析，再校验版本/字段/过期。
    """
    if not isinstance(token_str, str) or not token_str:
        raise InvalidAuthTokenError("INVALID_AUTH_TOKEN")

    try:
        decoded = _b64url_decode(token_str)
    except Exception:
        raise InvalidAuthTokenError("INVALID_AUTH_TOKEN")

    if b"." not in decoded:
        raise InvalidAuthTokenError("INVALID_AUTH_TOKEN")

    payload_bytes, sig_bytes = decoded.rsplit(b".", 1)
    if not payload_bytes or not sig_bytes:
        raise InvalidAuthTokenError("INVALID_AUTH_TOKEN")

    expected_sig = _sign(payload_bytes)
    if not hmac.compare_digest(sig_bytes, expected_sig):
        raise InvalidAuthTokenError("INVALID_AUTH_TOKEN")

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise InvalidAuthTokenError("INVALID_AUTH_TOKEN")

    if not isinstance(payload, dict):
        raise InvalidAuthTokenError("INVALID_AUTH_TOKEN")

    if payload.get("v") != AUTH_TOKEN_VERSION:
        raise InvalidAuthTokenError("INVALID_AUTH_TOKEN")

    if not isinstance(payload.get("aid"), int) or not isinstance(
        payload.get("role"), str
    ):
        raise InvalidAuthTokenError("INVALID_AUTH_TOKEN")

    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise InvalidAuthTokenError("INVALID_AUTH_TOKEN")

    if exp < int(time.time()):
        raise AuthTokenExpiredError("AUTH_TOKEN_EXPIRED")

    return {"aid": payload["aid"], "role": payload["role"], "exp": exp}
