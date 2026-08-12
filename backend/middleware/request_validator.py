"""
Request parameter validation middleware（V4.4 Phase 4 额外防护层）。

FastAPI Query 校验（min_length/max_length/ge/le）已覆盖大部分参数；此中间件
在进入路由 / 依赖解析之前再做一次防御性校验，并直接把畸形请求挡在业务逻辑之外。

校验项（仅作用于 /api/v1/lives/full 与 /api/v1/lives/sync）：
    city        非空且 <= 50 字符                      → 400 INVALID_CITY
    page_size   [1, 2000]（/full）                    → 400 INVALID_PAGE_TOKEN
    limit       [1, 5000]（/sync）                    → 400 INVALID_CURSOR
    since       非负整数（/sync，契约要求必填）          → 400 INVALID_CURSOR

错误码说明：
    契约 Error enum 只包含 7 个 code。page_size / limit / since 没有专属 code，
    这里复用各自端点的通用 400 错误码（/full → INVALID_PAGE_TOKEN，/sync →
    INVALID_CURSOR），保证响应始终落在契约 enum 内。FastAPI 路由层的 ge/le/解析
    逻辑与之一致（page_size/limit 越界同样 400，since 非法同样 INVALID_CURSOR）。

关键实现细节：
    中间件在 call_next 之前执行，此时位于 ExceptionMiddleware 之外；如果这里
    raise HTTPException，会被 ServerErrorMiddleware 转成 500 而非 400。
    因此本中间件直接 return JSONResponse 短路，绝不 raise。
"""

from typing import Awaitable, Callable, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

FULL_PATH = "/api/v1/lives/full"
SYNC_PATH = "/api/v1/lives/sync"

MAX_CITY_LENGTH = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 2000
MIN_LIMIT = 1
MAX_LIMIT = 5000


def _err(status: int, code: str) -> JSONResponse:
    """构造契约 Error JSON 响应。"""
    return JSONResponse(status_code=status, content={"code": code, "message": code})


def _first_param(request: Request, name: str) -> Optional[str]:
    """取查询参数第一个值（防御重复参数；缺失返回 None）。"""
    return request.query_params.get(name)


def _validate_full(request: Request) -> Optional[JSONResponse]:
    city = _first_param(request, "city")
    if city is None or city == "":
        return _err(400, "INVALID_CITY")
    if len(city) > MAX_CITY_LENGTH:
        return _err(400, "INVALID_CITY")

    page_size_raw = _first_param(request, "page_size")
    if page_size_raw is not None:
        try:
            page_size = int(page_size_raw)
        except ValueError:
            return _err(400, "INVALID_PAGE_TOKEN")
        if not (MIN_PAGE_SIZE <= page_size <= MAX_PAGE_SIZE):
            return _err(400, "INVALID_PAGE_TOKEN")
    return None


def _validate_sync(request: Request) -> Optional[JSONResponse]:
    city = _first_param(request, "city")
    if city is None or city == "":
        return _err(400, "INVALID_CITY")
    if len(city) > MAX_CITY_LENGTH:
        return _err(400, "INVALID_CITY")

    # since 为契约必填：缺失 / 空串 / 非法 / 负数均视为格式错误。
    since_raw = _first_param(request, "since")
    if since_raw is None or since_raw == "":
        return _err(400, "INVALID_CURSOR")
    try:
        since = int(since_raw)
    except ValueError:
        return _err(400, "INVALID_CURSOR")
    if since < 0:
        return _err(400, "INVALID_CURSOR")

    limit_raw = _first_param(request, "limit")
    if limit_raw is not None:
        try:
            limit = int(limit_raw)
        except ValueError:
            return _err(400, "INVALID_CURSOR")
        if not (MIN_LIMIT <= limit <= MAX_LIMIT):
            return _err(400, "INVALID_CURSOR")
    return None


def register_request_validator(app: FastAPI) -> None:
    """注册请求校验中间件（FastAPI http middleware）。"""

    @app.middleware("http")
    async def _validate_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if path == FULL_PATH:
            error = _validate_full(request)
            if error is not None:
                return error
        elif path == SYNC_PATH:
            error = _validate_sync(request)
            if error is not None:
                return error
        return await call_next(request)
