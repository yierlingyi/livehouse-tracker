"""
FastAPI 应用入口（V4.4 Phase 4 集成）。

启动（lifespan）：
    - 创建 Primary 连接池；DATABASE_URL_REPLICA 存在时创建 Replica 池。
    - 注入 token secret：token_manager.set_secret(settings.token_secret)。

挂载：
    - /api/v1/lives/full（backend.api.full.router）
    - /api/v1/lives/sync（backend.api.sync.router）

中间件（注册顺序 = 执行顺序，后注册的中间件更外层、先执行）：
    1) 请求校验 register_request_validator（外层，先执行）→ 畸形请求直接 400，
       不消耗限流配额。
    2) 限流 @app.middleware("http")（内层）→ 按 IP+city / user+scope 限流。

模块级依赖生成器（full.py / sync.py 惰性引用，必须在这里定义）：
    get_primary_db()    — /full、/sync 强制 Primary（全局原则 1）
    get_replica_db()    — 副本读；未配置 Replica 时回退 Primary

一致性：
    Redis 缓存 / 限流不参与 /sync 或一致性判定（全局原则 9）。
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.api.full import router as full_router
from backend.api.sync import router as sync_router
from backend.config import get_settings
from backend.middleware.error_handler import register_error_handlers
from backend.middleware.request_validator import register_request_validator
from backend.services.rate_limiter import (
    build_full_bucket_key,
    build_sync_bucket_key,
    client_ip,
    get_rate_limiter,
)
from backend.services.token_manager import set_secret

logger = logging.getLogger("bandlive")

# 模块级连接池（lifespan 中创建/关闭）。
primary_pool: Optional[asyncpg.Pool] = None
replica_pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global primary_pool, replica_pool

    settings = get_settings()
    # token 签名密钥由环境注入，绝不硬编码。
    set_secret(settings.token_secret)

    primary_pool = await asyncpg.create_pool(
        settings.database_url_primary,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )
    logger.info(
        "primary pool ready (min=%s max=%s)",
        settings.db_pool_min,
        settings.db_pool_max,
    )

    if settings.database_url_replica:
        replica_pool = await asyncpg.create_pool(
            settings.database_url_replica,
            min_size=settings.db_pool_min,
            max_size=settings.db_pool_max,
        )
        logger.info("replica pool ready")
    else:
        logger.info("DATABASE_URL_REPLICA not set; replica reads fall back to primary")

    try:
        yield
    finally:
        if primary_pool is not None:
            await primary_pool.close()
            primary_pool = None
        if replica_pool is not None:
            await replica_pool.close()
            replica_pool = None
        logger.info("database pools closed")


async def get_primary_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """Primary 连接依赖。/full、/sync 强制走 Primary（全局原则 1）。"""
    if primary_pool is None:
        raise HTTPException(status_code=503, detail="PRIMARY_DB_UNAVAILABLE")
    async with primary_pool.acquire() as conn:
        yield conn


async def get_replica_db() -> AsyncGenerator[asyncpg.Connection, None]:
    """Replica 连接依赖；未配置 Replica 时回退 Primary。"""
    pool = replica_pool or primary_pool
    if pool is None:
        raise HTTPException(status_code=503, detail="DB_UNAVAILABLE")
    async with pool.acquire() as conn:
        yield conn


app = FastAPI(title="Band Live API", version="4.4.0", lifespan=lifespan)

# --- 错误处理（HTTPException 错误码 → 契约 Error JSON） ---
register_error_handlers(app)

# --- 限流中间件（V4.4 §13）---
# 注意注册顺序：这里先注册限流（内层），下方再注册请求校验（外层，先执行），
# 使非法请求先被 400 拦截、不消耗限流配额。


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    settings = get_settings()
    limiter = get_rate_limiter()

    if path == "/api/v1/lives/full":
        city = request.query_params.get("city", "")
        key = build_full_bucket_key(client_ip(request), city)
        if not await limiter.allow(key, settings.rate_limit_full_per_minute):
            return JSONResponse(
                status_code=429,
                content={"code": "RATE_LIMITED", "message": "RATE_LIMITED"},
            )
    elif path == "/api/v1/lives/sync":
        user = request.headers.get("X-User-Id") or client_ip(request)
        scope = (
            f"{request.query_params.get('scope_start_date', '')}:"
            f"{request.query_params.get('scope_end_date', '')}"
        )
        key = build_sync_bucket_key(user, scope)
        if not await limiter.allow(key, settings.rate_limit_sync_per_minute):
            return JSONResponse(
                status_code=429,
                content={"code": "RATE_LIMITED", "message": "RATE_LIMITED"},
            )

    return await call_next(request)


# --- 请求校验（后注册 → 外层 → 先执行） ---
register_request_validator(app)

# --- 路由挂载 ---
app.include_router(full_router)
app.include_router(sync_router)
