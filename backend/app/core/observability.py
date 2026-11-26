"""PII-free access logging, request ids and error handlers.

Access logs contain the HTTP method, the **route template** (``/api/v1/jobs/{job_id}``,
never the concrete path, which could hold a file name), status, duration and a request
id. Error bodies never echo request input: validation errors report field locations
only, and unhandled exceptions return a generic code.
"""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

log = logging.getLogger("anamika.api")


def configure_logging(level: str = "INFO") -> None:
    """Plain, single-line logs to stderr; uvicorn's access log is replaced by ours."""
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("uvicorn.access").disabled = True


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Attaches ``X-Request-ID`` and logs one PII-free line per request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = uuid.uuid4().hex[:16]
        request.state.request_id = rid
        t0 = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            route = request.scope.get("route")
            template = getattr(route, "path", "<unmatched>")
            log.info("req id=%s method=%s route=%s status=%s ms=%.1f", rid, request.method,
                     template, status_code, (time.perf_counter() - t0) * 1000)
        response.headers["X-Request-ID"] = rid
        return response


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers that never leak input or internals."""

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "error"
        return JSONResponse({"error": detail, "request_id": _rid(request)},
                            status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(p) for p in e.get("loc", ())) for e in exc.errors()]
        return JSONResponse({"error": "invalid_request", "fields": fields[:20],
                             "request_id": _rid(request)}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled id=%s exc=%s", _rid(request), type(exc).__name__)
        return JSONResponse({"error": "internal_error", "request_id": _rid(request)},
                            status_code=500)
