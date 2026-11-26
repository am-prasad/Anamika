"""Job queues: ``inline`` (in-process, bounded concurrency) or ``redis`` (arq workers).

With ``redis`` the API only enqueues; any number of worker containers consume jobs,
so throughput scales horizontally and API replicas stay stateless.
"""
from __future__ import annotations

import asyncio
from typing import Protocol

from ..core.config import Settings
from .jobstore import JobStore
from .runner import execute_job


class JobQueue(Protocol):
    """Enqueue interface."""

    async def enqueue(self, job_id: str) -> None: ...
    async def close(self) -> None: ...


class InlineQueue:
    """Runs jobs as background tasks in the API process (development, single node)."""

    def __init__(self, store: JobStore, settings: Settings) -> None:
        self.store, self.settings = store, settings
        self._sem = asyncio.Semaphore(settings.inline_concurrency)
        self._tasks: set[asyncio.Task[None]] = set()

    async def enqueue(self, job_id: str) -> None:
        async def run() -> None:
            async with self._sem:
                await execute_job(job_id, self.store, self.settings)

        task = asyncio.create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """Wait for every running job (tests and graceful shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def close(self) -> None:
        await self.drain()


class ArqQueue:
    """Enqueues onto Redis for arq workers (``app.worker.WorkerSettings``)."""

    def __init__(self, pool) -> None:  # type: ignore[no-untyped-def]
        self.pool = pool

    @classmethod
    async def connect(cls, redis_url: str) -> "ArqQueue":
        from arq import create_pool
        from arq.connections import RedisSettings

        return cls(await create_pool(RedisSettings.from_dsn(redis_url)))

    async def enqueue(self, job_id: str) -> None:
        await self.pool.enqueue_job("run_job", job_id, _job_id=job_id)

    async def close(self) -> None:
        await self.pool.aclose()
