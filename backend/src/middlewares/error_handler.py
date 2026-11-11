"""统一异常收敛：AppError / RequestValidationError / 未捕获异常。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.constants import error_codes as codes
from src.utils.errors import AppError
from src.utils.logger import get_logger

logger = get_logger("cdcmerge.error")


def _trace_id(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_payload(_trace_id(request)))

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        detail = f"{'.'.join(str(p) for p in first.get('loc', []))}: {first.get('msg', '')}"
        return JSONResponse(
            status_code=422,
            content={
                "code": codes.VALIDATION_ERROR,
                "message": codes.ERROR_MESSAGES[codes.VALIDATION_ERROR],
                "detail": detail,
                "trace_id": _trace_id(request),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = codes.NOT_FOUND if exc.status_code == 404 else codes.INTERNAL_ERROR
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": code,
                "message": str(exc.detail),
                "detail": "",
                "trace_id": _trace_id(request),
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error path=%s error=%s", request.url.path, exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "code": codes.INTERNAL_ERROR,
                "message": codes.ERROR_MESSAGES[codes.INTERNAL_ERROR],
                "detail": str(exc),
                "trace_id": _trace_id(request),
            },
        )
