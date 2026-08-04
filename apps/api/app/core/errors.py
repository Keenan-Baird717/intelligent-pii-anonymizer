from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers
        super().__init__(message)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


def _error_body(code: str, message: str, request_id: str) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message, _request_id(request)),
        headers=exc.headers,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        error_code="INTERNAL_ERROR",
        exception_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content=_error_body(
            "INTERNAL_ERROR",
            "An unexpected error occurred.",
            _request_id(request),
        ),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # TrustedHostMiddleware and similar Starlette errors.
    detail = exc.detail
    if exc.status_code == 400 and isinstance(detail, str) and "Invalid host header" in detail:
        code, message = "INVALID_HOST", "Invalid Host header."
    elif exc.status_code == 429:
        code, message = "RESOURCE_BUSY", "Too many requests. Please retry shortly."
    elif exc.status_code == 404:
        code, message = "NOT_FOUND", "Resource not found."
    elif exc.status_code == 405:
        code, message = "METHOD_NOT_ALLOWED", "Method not allowed."
    else:
        code, message = "HTTP_ERROR", "The request could not be completed."
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, message, _request_id(request)),
        headers=dict(headers) if headers else None,
    )


def _safe_validation_code(errors: Sequence[Any]) -> tuple[str, str]:
    """Map validation errors to stable codes without echoing request values."""
    for err in errors:
        if not isinstance(err, dict):
            continue
        loc = err.get("loc") or ()
        err_type = str(err.get("type") or "")
        loc_str = ".".join(str(part) for part in loc)
        if "uuid" in err_type or "uuid" in loc_str.lower():
            return "INVALID_UUID", "One or more identifiers are malformed."
        if "json" in err_type or err_type == "json_invalid":
            return "INVALID_JSON", "The request body is not valid JSON."
        if "enum" in err_type:
            return "INVALID_ENUM", "One or more fields have an unsupported value."
        if "extra_forbidden" in err_type:
            return "UNEXPECTED_FIELD", "The request contains unsupported fields."
        if "string_too_long" in err_type or "too_long" in err_type:
            return "VALUE_TOO_LONG", "One or more fields exceed the maximum allowed length."
        if "too_short" in err_type:
            return "VALUE_TOO_SHORT", "One or more fields are below the minimum allowed length."
        if "greater_than" in err_type or "less_than" in err_type or "finite" in err_type:
            return "INVALID_NUMBER", "One or more numeric fields are invalid."
        if "list_type" in err_type or "list" in err_type:
            return "INVALID_LIST", "One or more list fields are invalid."
    return "VALIDATION_ERROR", "The request failed validation."


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Never echo request bodies, field values, or submitted text.
    errors = exc.errors()
    code, message = _safe_validation_code(errors)
    logger.info(
        "request_validation_failed",
        error_code=code,
        error_count=len(errors),
        # Locations only — no input values.
        field_paths=[
            ".".join(str(part) for part in (err.get("loc") or ()))
            for err in errors
            if isinstance(err, dict)
        ][:20],
    )
    return JSONResponse(
        status_code=422,
        content=_error_body(code, message, _request_id(request)),
    )
