"""统一错误体：{code, message}（契约 v1）。"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def not_found(message: str = "资源不存在") -> ApiError:
    return ApiError(404, "not_found", message)


def forbidden(message: str = "无权限访问") -> ApiError:
    return ApiError(403, "forbidden", message)


def unauthorized(message: str = "未认证或令牌无效") -> ApiError:
    return ApiError(401, "unauthorized", message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def bad_request(code: str, message: str) -> ApiError:
    return ApiError(400, code, message)


def parse_uuid(value: str, message: str = "资源不存在") -> uuid.UUID:
    """路径参数里的 id 先校验成 UUID，避免非法字符串打到数据库变成 500。"""
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise not_found(message) from exc


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            409: "conflict",
        }.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": str(exc.detail)},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        message = f"{'.'.join(str(p) for p in first.get('loc', []))}: {first.get('msg', '参数错误')}"
        return JSONResponse(status_code=422, content={"code": "validation_error", "message": message})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover - 兜底
        return JSONResponse(status_code=500, content={"code": "internal_error", "message": str(exc)})
