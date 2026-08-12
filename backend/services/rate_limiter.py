"""
Token bucket rate limiter（V4.4 §13）。

    - /full: 按 IP + city 限流（build_full_bucket_key）
    - /sync: 按 user + scope 限流（build_sync_bucket_key；user 取 X-User-Id 头，
      缺省回退客户端 IP）
    - 优先 Redis（Lua 原子脚本，token bucket 语义）；Redis 不可用或未配置时
      静默降级到进程内内存实现，不阻断业务。
    - 超限返回 429 RATE_LIMITED（由调用方 / 中间件发出 JSON Error 响应）。

Token bucket 参数：
    capacity      = rate_per_minute（突发上限 = 每分钟配额）
    refill_per_sec = rate_per_minute / 60（每秒补速率）
"""

import asyncio
import time
from typing import Dict, Optional

from fastapi import Request

from backend.config import get_settings

__all__ = [
    "TokenBucketRateLimiter",
    "get_rate_limiter",
    "client_ip",
    "build_full_bucket_key",
    "build_sync_bucket_key",
]

# Redis Lua 原子 token bucket：
#   KEYS[1] = tokens 键（当前剩余 token）
#   KEYS[2] = 时间戳键
#   ARGV[1] = capacity，ARGV[2] = refill_per_sec，ARGV[3] = now(秒)
_LUA_TOKEN_BUCKET = """
local tokens_key = KEYS[1]
local ts_key = KEYS[2]
local capacity = tonumber(ARGV[1])
local refill_per_sec = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local tokens = redis.call('GET', tokens_key)
local last = redis.call('GET', ts_key)
if not tokens or not last then
    tokens = capacity
    last = now
else
    tokens = tonumber(tokens)
    last = tonumber(last)
end

local elapsed = now - last
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill_per_sec)

local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call('SET', tokens_key, tokens, 'EX', 300)
redis.call('SET', ts_key, now, 'EX', 300)
return allowed
"""

# 内存实现单个 bucket 的过期清理阈值（秒）
_MEMORY_CLEANUP_AFTER = 600
_MEMORY_MAX_ENTRIES = 5000


def client_ip(request: Request) -> str:
    """提取客户端 IP：优先可信代理头（X-Forwarded-For / X-Real-IP），回退 peer。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


def build_full_bucket_key(ip: str, city: str) -> str:
    return f"rl:full:v1:{ip}:{city}"


def build_sync_bucket_key(user: str, scope: str) -> str:
    return f"rl:sync:v1:{user}:{scope}"


class TokenBucketRateLimiter:
    """Token bucket 限流器。Redis 优先，内存降级。"""

    def __init__(self, redis_url: str = ""):
        self._redis = None
        self._mem_tokens: Dict[str, float] = {}
        self._mem_ts: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        if redis_url:
            import redis.asyncio as aioredis  # 惰性导入

            self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def allow(self, bucket_key: str, rate_per_minute: int) -> bool:
        """返回 True 放行，False 超限（429）。"""
        capacity = max(1, int(rate_per_minute))
        refill_per_sec = max(0.0, rate_per_minute / 60.0)

        if self._redis is not None:
            try:
                now = time.time()
                allowed = await self._redis.eval(
                    _LUA_TOKEN_BUCKET,
                    2,
                    f"{bucket_key}:tokens",
                    f"{bucket_key}:ts",
                    capacity,
                    refill_per_sec,
                    now,
                )
                return bool(allowed)
            except Exception:
                # Redis 故障 → 静默降级内存，不阻断业务
                return await self._allow_memory(bucket_key, capacity, refill_per_sec)

        return await self._allow_memory(bucket_key, capacity, refill_per_sec)

    async def _allow_memory(
        self, key: str, capacity: int, refill_per_sec: float
    ) -> bool:
        async with self._lock:
            now = time.time()
            tokens = self._mem_tokens.get(key)
            last = self._mem_ts.get(key, now)
            if tokens is None:
                tokens = float(capacity)
            # 补充新 token（按经过秒数）
            tokens = min(
                float(capacity), tokens + max(0.0, now - last) * refill_per_sec
            )
            allowed = tokens >= 1.0
            if allowed:
                tokens -= 1.0
            self._mem_tokens[key] = tokens
            self._mem_ts[key] = now

            # 防内存无限增长：超过阈值时清理过期 bucket
            if len(self._mem_tokens) >= _MEMORY_MAX_ENTRIES:
                self._prune_memory(now)
            return allowed

    def _prune_memory(self, now: float) -> None:
        cutoff = now - _MEMORY_CLEANUP_AFTER
        stale = [k for k, ts in self._mem_ts.items() if ts < cutoff]
        for k in stale:
            self._mem_tokens.pop(k, None)
            self._mem_ts.pop(k, None)


_limiter: Optional[TokenBucketRateLimiter] = None


def get_rate_limiter() -> TokenBucketRateLimiter:
    """惰性单例。REDIS_URL 未配置时使用内存实现。"""
    global _limiter
    if _limiter is None:
        settings = get_settings()
        _limiter = TokenBucketRateLimiter(redis_url=settings.redis_url)
    return _limiter
