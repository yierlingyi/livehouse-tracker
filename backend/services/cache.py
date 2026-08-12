"""
Redis cache helper（V4.4 §12）— 只缓存 /full 热点页，绝不缓存 /sync。

约束：
    1. /sync 绝不缓存：set_cached_full 硬校验 key 必须以 full:lives:v1: 开头，
       任何非 /full 前缀的 key 都被拒绝，从机制上杜绝 /sync 进入缓存。
    2. 缓存 key 格式：full:lives:v1:{city}:{scope_start_date}:{scope_end_date}:{token_hash}
       token_hash = sha256(page_token)[:16]；第一页 page_token 为空串。
    3. TTL 含随机 jitter（cache_ttl_base + [0, cache_ttl_jitter]），避免集中失效。
    4. 缓存失败静默降级：get 返回 None，set 忽略异常，绝不阻断业务。
    5. Redis 不参与一致性判定（全局原则 9）：缓存命中返回的响应必须与原始响应
       完全一致（含固定 Scope / snapshot_cursor），调用方负责原样序列化。

未配置 REDIS_URL 时，本模块所有函数均为安全空操作（返回 None / 直接返回）。
"""

import hashlib
import json
import random
from typing import Any, Dict, Optional

from backend.config import get_settings

FULL_PREFIX = "full:lives:v1"

_client: Optional[Any] = None


def _get_client():
    """惰性创建 redis.asyncio.Redis 客户端。未配置 REDIS_URL 时返回 None。"""
    global _client
    settings = get_settings()
    if not settings.redis_url:
        return None
    if _client is None:
        import redis.asyncio as aioredis  # 惰性导入，避免未安装 redis 时模块导入失败

        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


def build_full_cache_key(
    city: str,
    scope_start_date: str,
    scope_end_date: str,
    page_token: Optional[str] = None,
) -> str:
    """构造 /full 缓存 key。

    page_token 为 None（第一页）时取空串 hash，因此首末页不会共用 key。
    """
    token_hash = hashlib.sha256((page_token or "").encode("utf-8")).hexdigest()[:16]
    return f"{FULL_PREFIX}:{city}:{scope_start_date}:{scope_end_date}:{token_hash}"


async def get_cached_full(key: str) -> Optional[Dict[str, Any]]:
    """读取 /full 缓存。未配置 Redis / 非 full key / 未命中 / 出错一律返回 None。"""
    if not key.startswith(FULL_PREFIX):
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        # 静默降级：缓存故障不影响业务
        return None


async def set_cached_full(key: str, payload: Dict[str, Any]) -> None:
    """写入 /full 缓存，TTL 带 jitter。任何失败静默忽略。"""
    if not key.startswith(FULL_PREFIX):
        return  # 非 /full 响应一律拒绝写入（机制上杜绝 /sync 入缓存）
    client = _get_client()
    if client is None:
        return
    settings = get_settings()
    try:
        ttl = settings.cache_ttl_base + random.randint(0, settings.cache_ttl_jitter)
        await client.set(key, json.dumps(payload, ensure_ascii=False), ex=ttl)
    except Exception:
        pass


async def invalidate_full_cache(
    city: str, scope_start_date: str, scope_end_date: str
) -> None:
    """按前缀失效某 city+scope 的全部分页缓存（可选维护能力，失败静默）。"""
    client = _get_client()
    if client is None:
        return
    prefix = f"{FULL_PREFIX}:{city}:{scope_start_date}:{scope_end_date}:"
    try:
        keys = await client.keys(prefix + "*")
        if keys:
            await client.delete(*keys)
    except Exception:
        pass
