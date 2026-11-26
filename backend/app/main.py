"""FastAPI application factory for the Anamika service.

Run locally:  ``uv run uvicorn app.main:app --reload``  (from ``backend/``).
In Docker the API runs with ``ANAMIKA_QUEUE_MODE=redis`` and separate arq workers.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from anamika import __version__

from .api.routes import jobs, meta
from .core.config import Settings, get_settings
from .core.observability import AccessLogMiddleware, configure_logging, install_error_handlers
from .core.ratelimit import MemoryBackend, RedisBackend
from .core.security import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from .services import storage
from .services.jobstore import MemoryJobStore, RedisJobStore
from .services.queue import ArqQueue, InlineQueue


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; ``settings`` overrides the environment (tests)."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        storage.jobs_root(settings.data_dir)
        redis = None
        if settings.redis_url:
            from redis.asyncio import from_url

            redis = from_url(settings.redis_url, decode_responses=True)
            app.state.store = RedisJobStore(redis, settings.job_ttl_hours * 3600)
            app.state.ratelimit = RedisBackend(redis)
        else:
            app.state.store = MemoryJobStore()
            app.state.ratelimit = MemoryBackend()
        if settings.queue_mode == "redis":
            app.state.queue = await ArqQueue.connect(settings.redis_url)  # type: ignore[arg-type]
        else:
            app.state.queue = InlineQueue(app.state.store, settings)
        try:
            yield
        finally:
            await app.state.queue.close()
            if redis is not None:
                await redis.aclose()

    configure_logging()
    app = FastAPI(
        title="Anamika API", version=__version__, lifespan=lifespan,
        description="Visible to science, invisible to attackers. Privacy firewall for "
                    "multilingual hospital records.",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings

    # Middleware runs bottom-up: access log sees everything, size limit runs early.
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.env == "production")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                       allow_credentials=False, allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["X-API-Key", "Content-Type"],
                       expose_headers=["X-Request-ID", "X-RateLimit-Limit",
                                       "X-RateLimit-Remaining", "X-RateLimit-Reset",
                                       "Retry-After"], max_age=600)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_mb * 1024 * 1024)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
    app.add_middleware(AccessLogMiddleware)
    install_error_handlers(app)
    app.include_router(meta.router)
    app.include_router(jobs.router)
    return app


app = create_app()
