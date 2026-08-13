"""密码哈希（PBKDF2-HMAC-SHA256，无第三方依赖）。

存储格式（契约要求）：`salt$hash`，均为 hex 编码文本。
    hash = pbkdf2_hmac('sha256', password, bytes.fromhex(salt), ITERATIONS)
验证使用常量 ITERATIONS，采用 hmac.compare_digest 防时序侧信道。

说明：项目无 requirements.txt，也未采用 passlib/bcrypt 依赖（bcrypt 虽已安装，
但按契约要求避免引入新依赖），故用标准库 hashlib.pbkdf2_hmac。
"""

import hashlib
import hmac
import os

__all__ = ["hash_password", "verify_password", "ITERATIONS"]

ITERATIONS = 120_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """生成 `salt$hash`（hex）口令散列。password 不应为空（由调用方校验）。"""
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, ITERATIONS
    )
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验口令；任何解析失败都按 False 处理，绝不抛出。"""
    if not isinstance(stored, str):
        return False
    try:
        salt_hex, _, hash_hex = stored.partition("$")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, ITERATIONS
    )
    return hmac.compare_digest(digest, expected)
