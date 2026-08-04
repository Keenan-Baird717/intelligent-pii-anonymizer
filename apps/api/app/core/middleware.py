from __future__ import annotations

import re
import secrets
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

# Safe request IDs: alphanumeric, hyphen, underscore only. No control chars / separators.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]+$")

_SENSITIVE_PATH_PREFIXES = (
    "/api/v1/jobs/",
    "/api/v1/documents",
    "/api/v1/analyze/",
    "/api/v1/anonymize/",
)


def sanitize_request_id(raw: str | None, *, max_length: int | None = None) -> str:
    """Validate a client-supplied request ID or generate a cryptographically random one.

    Rejects / replaces IDs containing newlines, tabs, ANSI escapes, path separators,
    or other control characters so they cannot inject log entries.
    """
    limit = max_length if max_length is not None else settings.max_request_id_length
    if raw is None:
        return _generate_request_id()
    candidate = raw.strip()
    if not candidate or len(candidate) > limit:
        return _generate_request_id()
    if not _SAFE_REQUEST_ID.fullmatch(candidate):
        return _generate_request_id()
    # Extra defense: reject any residual control characters.
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in candidate):
        return _generate_request_id()
    return candidate


def _generate_request_id() -> str:
    # secrets + uuid4 hex keeps IDs opaque and log-safe.
    return f"{secrets.token_hex(8)}-{uuid.uuid4().hex[:12]}"


def _should_apply_no_store(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _SENSITIVE_PATH_PREFIXES)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = sanitize_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply conservative HTTP security headers for the local MVP API."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        path = request.url.path

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()",
        )
        # API responses do not need script execution; keep CSP tight for the API origin.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )

        if _should_apply_no_store(path) or path.startswith("/api/v1/"):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers.setdefault("Pragma", "no-cache")

        # HSTS only when explicitly enabled for HTTPS production mode.
        if settings.enable_hsts and settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response
