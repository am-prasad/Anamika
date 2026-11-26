"""arq worker: consumes jobs from Redis and runs the sandboxed pipeline.

Start with ``arq app.worker.WorkerSettings``. Scale by running more worker containers;
each handles ``inline_concurrency`` jobs at a time. An hourly cron removes expired
workspaces.
"""
from __future__ import annotations

from typing import Any

from arq import cron
from arq.connections import RedisSettings
from redis.asyncio import from_url

from .core.config import get_settings
from .core.observability import configure_logging
from .services.jobstore import RedisJobStore
from .services.runner import cleanup_expired, execute_job

_settings = get_settings()


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    ctx["store"] = RedisJobStore(from_url(_settings.redis_url, decode_responses=True),
                                 _settings.job_ttl_hours * 3600)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["store"].redis.aclose()


async def run_job(ctx: dict[str, Any], job_id: str) -> None:
    """arq task: execute one job."""
    await execute_job(job_id, ctx["store"], _settings)


async def cleanup(ctx: dict[str, Any]) -> None:
    """arq cron: drop expired workspaces."""
    await cleanup_expired(ctx["store"], _settings)


class WorkerSettings:
    """arq configuration."""

    functions = [run_job]
    cron_jobs = [cron(cleanup, minute={7}, run_at_startup=True)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.redis_url or "redis://localhost:6379")
    max_jobs = _settings.inline_concurrency
    job_timeout = _settings.job_timeout_s * 3 + 120  # pipeline + two verification runs
    keep_result = 3600
    max_tries = 1
