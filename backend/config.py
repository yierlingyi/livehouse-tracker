"""
Application settings（V4.4 Phase 4 集成）。

所有敏感值（数据库密码 / token 密钥）只从环境变量读取，禁止硬编码：

    DATABASE_URL_PRIMARY            必填，Primary 数据库连接串
    DATABASE_URL_REPLICA            可选，Replica 连接串；留空则 replica 读回退 Primary
    TOKEN_SECRET                    必填，HMAC-SHA256 签名密钥（token_manager.set_secret）
    TOKEN_TTL_MINUTES               默认 30，分页 token 有效期
    DB_POOL_MIN / DB_POOL_MAX       连接池上下限（默认 5 / 50）
    REDIS_URL                       可选，Redis 连接串；留空则缓存 / 限流走内存降级
    CACHE_TTL_BASE / CACHE_TTL_JITTER   缓存 TTL 及其随机抖动（避免集中失效）
    RATE_LIMIT_FULL_PER_MINUTE / RATE_LIMIT_SYNC_PER_MINUTE  限流配额
    SCOPE_DEFAULT_DAYS              默认 90，/full 固定 scope 长度
    RETENTION_DAYS                  默认 30，CDC 日志保留天数

get_settings() 返回进程内缓存的单例；main.py / 各 service 惰性引用。
"""

import os
from dataclasses import dataclass
from typing import Optional

__all__ = ["Settings", "get_settings"]


def _env_str(name: str, default: str = "") -> str:
    """读取字符串环境变量，去空白；未设置或空串返回 default。"""
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_int(name: str, default: int) -> int:
    """读取整型环境变量；非法值直接抛错，避免静默吞掉配置错误。"""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}")


@dataclass
class Settings:
    database_url_primary: str
    database_url_replica: str = ""
    db_pool_min: int = 5
    db_pool_max: int = 50
    token_secret: str = ""
    token_ttl_minutes: int = 30
    redis_url: str = ""
    cache_ttl_base: int = 60
    cache_ttl_jitter: int = 30
    rate_limit_full_per_minute: int = 30
    rate_limit_sync_per_minute: int = 60
    scope_default_days: int = 90
    retention_days: int = 30

    def __post_init__(self) -> None:
        if not self.database_url_primary:
            raise ValueError("database_url_primary must not be empty")
        if not self.token_secret:
            raise ValueError("token_secret must not be empty")
        if self.db_pool_min < 1:
            raise ValueError("db_pool_min must be >= 1")
        if self.db_pool_max < self.db_pool_min:
            raise ValueError("db_pool_max must be >= db_pool_min")
        if self.token_ttl_minutes < 1:
            raise ValueError("token_ttl_minutes must be >= 1")
        if self.cache_ttl_base < 1:
            raise ValueError("cache_ttl_base must be >= 1")
        if self.cache_ttl_jitter < 0:
            raise ValueError("cache_ttl_jitter must be >= 0")
        if self.rate_limit_full_per_minute < 1:
            raise ValueError("rate_limit_full_per_minute must be >= 1")
        if self.rate_limit_sync_per_minute < 1:
            raise ValueError("rate_limit_sync_per_minute must be >= 1")
        if self.scope_default_days < 1:
            raise ValueError("scope_default_days must be >= 1")
        if self.retention_days < 0:
            raise ValueError("retention_days must be >= 0")

    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量构造 Settings（敏感值只来自环境，禁止硬编码）。"""
        return cls(
            database_url_primary=_env_str("DATABASE_URL_PRIMARY", ""),
            database_url_replica=_env_str("DATABASE_URL_REPLICA", ""),
            db_pool_min=_env_int("DB_POOL_MIN", 5),
            db_pool_max=_env_int("DB_POOL_MAX", 50),
            token_secret=_env_str("TOKEN_SECRET", ""),
            token_ttl_minutes=_env_int("TOKEN_TTL_MINUTES", 30),
            redis_url=_env_str("REDIS_URL", ""),
            cache_ttl_base=_env_int("CACHE_TTL_BASE", 60),
            cache_ttl_jitter=_env_int("CACHE_TTL_JITTER", 30),
            rate_limit_full_per_minute=_env_int("RATE_LIMIT_FULL_PER_MINUTE", 30),
            rate_limit_sync_per_minute=_env_int("RATE_LIMIT_SYNC_PER_MINUTE", 60),
            scope_default_days=_env_int("SCOPE_DEFAULT_DAYS", 90),
            retention_days=_env_int("RETENTION_DAYS", 30),
        )


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """返回进程内缓存的 Settings 单例（首次调用时从环境变量加载）。"""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings
