"""
Error handler（V4.4 §14）— 将 HTTPException 的 detail 字符串映射为契约 Error JSON。

V4.4 §14 错误码 → 状态码映射：
    INVALID_CITY            400
    INVALID_PAGE_TOKEN      400
    INVALID_CURSOR          400
    FULL_PAGE_TOKEN_EXPIRED 409
    SYNC_CURSOR_EXPIRED     409
    RATE_LIMITED            429
    SYNC_INVARIANT_BROKEN   500

响应体遵循 contracts/shared.json#/definitions/Error：{"code", "message"}。

- detail 是已知错误码 → 使用映射表状态码，返回 {code, message: str(detail)}。
- 未知 detail / 普通 HTTPException → 保留原状态码，code 回退 UNKNOWN_ERROR。
- RequestValidationError（FastAPI Query 校验 422）→ code VALIDATION_ERROR。
- 未处理异常 → 500 INTERNAL_ERROR（记录日志，不向客户端泄漏内部细节）。

register_error_handlers(app) 使用 FastAPI exception_handler 装饰器挂载处理器。
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("bandlive.errors")

# V4.4 §14 错误码 → HTTP 状态码（契约唯一权威映射）。
ERROR_CODE_STATUS = {
    "INVALID_CITY": 400,
    "INVALID_PAGE_TOKEN": 400,
    "INVALID_CURSOR": 400,
    "FULL_PAGE_TOKEN_EXPIRED": 409,
    "SYNC_CURSOR_EXPIRED": 409,
    "RATE_LIMITED": 429,
    "SYNC_INVARIANT_BROKEN": 500,
    # 三端扩展业务错误码（api_contract.md §0 错误统一 {code, message}）
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "INVALID_CREDENTIALS": 400,
    "PENDING": 403,
    "ACCOUNT_DISABLED": 403,
    "ACCOUNT_EXISTS": 409,
    "USER_NOT_FOUND": 404,
    "CANNOT_INVITE_SELF": 400,
    "VALIDATION_ERROR": 422,
    "INVALID_ACTION": 400,
    "INVALID_STATUS": 400,
    "INVALID_TITLE": 400,
    "INVALID_LIVE_DATE": 400,
    "INVALID_LIVEHOUSE": 400,
    "INVALID_VENUE_NAME": 400,
    "INVALID_PLATFORM": 400,
    "INVALID_GROUP_ID": 400,
    "INVALID_USERNAME": 400,
    "INVALID_PASSWORD": 400,
    "INVALID_BAND_NAME": 400,
    "INVALID_BANDS": 400,
    "UNKNOWN_BAND_ID": 400,
    "TOO_MANY_BANDS": 400,
}


async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTPException 处理器：按 detail 错误码映射为 {code, message} JSON。

    detail 支持两种形式：
        - str：契约错误码（在 ERROR_CODE_STATUS 中映射状态码，message=code）。
        - dict {code, message[, status_code]}：完整业务错误，直接透出。
    """
    detail = exc.detail
    if isinstance(detail, dict):
        code = detail.get("code", "UNKNOWN_ERROR")
        message = detail.get("message") or str(code)
        status = detail.get("status_code") or exc.status_code
        return JSONResponse(
            status_code=status,
            content={"code": code, "message": message},
            headers=exc.headers,
        )
    if isinstance(detail, str) and detail in ERROR_CODE_STATUS:
        return JSONResponse(
            status_code=ERROR_CODE_STATUS[detail],
            content={"code": detail, "message": str(detail)},
            headers=exc.headers,
        )
    # 未知 code：保留原始状态码，code 回退 UNKNOWN_ERROR。
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": "UNKNOWN_ERROR", "message": str(detail)},
        headers=exc.headers,
    )


async def request_validation_handler(request: Request, exc: RequestValidationError):
    """FastAPI Query/路径参数校验失败（422）→ 结构化 JSON。"""
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "request validation failed",
            "errors": exc.errors(),
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底：未处理异常 → 500 INTERNAL_ERROR，不泄漏内部细节。"""
    logger.exception(
        "Unhandled error on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "internal server error"},
    )


def register_error_handlers(app: FastAPI) -> None:
    """把三个异常处理器挂到 app（使用 exception_handler 装饰器）。"""

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(
        request: Request, exc: RequestValidationError
    ):
        return await request_validation_handler(request, exc)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        return await unhandled_exception_handler(request, exc)
