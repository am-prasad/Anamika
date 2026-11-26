"""Authentication and HTTP security headers.

API keys are never stored: the service holds only their SHA-256 hashes
(``ANAMIKA_API_KEYS_SHA256``) and compares in constant time. The authenticated
principal id is a short prefix of the key hash, used for job ownership and rate limits.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .config import Settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller."""

    id: str


def hash_key(raw: str) -> str:
    """SHA-256 hex of an API key (what goes into ``ANAMIKA_API_KEYS_SHA256``)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def require_principal(request: Request,
                            api_key: str | None = Depends(API_KEY_HEADER)) -> Principal:
    """Resolve the caller from ``X-API-Key``; 401 when missing or unknown."""
    settings: Settings = request.app.state.settings
    if settings.auth_disabled:
        principal = Principal("dev")
    else:
        if not api_key or len(api_key) > 256:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_or_invalid_api_key",
                                headers={"WWW-Authenticate": "APIKey"})
        digest = hash_key(api_key)
        match = None
        for known in settings.api_keys:  # constant-time against every key
            if hmac.compare_digest(digest, known):
                match = known
        if match is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing_or_invalid_api_key",
                                headers={"WWW-Authenticate": "APIKey"})
        principal = Principal("key_" + match[:12])
    request.state.principal = principal
    return principal


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cache-Control": "no-store",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
DOCS_CSP = ("default-src 'self'; img-src 'self' data: https://fastapi.tiangolo.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; frame-ancestors 'none'")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds hardening headers to every response (HSTS in production only)."""

    def __init__(self, app, hsts: bool) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        for k, v in getattr(request.state, "ratelimit_headers", {}).items():
            response.headers.setdefault(k, v)
        is_docs = request.url.path in ("/docs", "/redoc", "/openapi.json")
        response.headers.setdefault("Content-Security-Policy", DOCS_CSP if is_docs else API_CSP)
        if self.hsts:
            response.headers.setdefault("Strict-Transport-Security",
                                        "max-age=63072000; includeSubDomains")
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects requests whose declared or streamed body exceeds ``max_bytes`` (413)."""

    def __init__(self, app, max_bytes: int) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                too_big = int(declared) > self.max_bytes
            except ValueError:
                return Response('{"error":"bad_content_length"}', 400,
                                media_type="application/json")
            if too_big:
                return Response('{"error":"request_too_large"}', 413,
                                media_type="application/json")
        elif request.method in ("POST", "PUT", "PATCH"):
            return Response('{"error":"length_required"}', 411, media_type="application/json")
        return await call_next(request)
