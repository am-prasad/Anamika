"""Job metadata stores: Redis (shared, horizontally scalable) or in-memory (dev / tests).

A job record holds status, timestamps, counts and verification results only — never
file names, record content or secrets. Redis records expire after ``job_ttl_hours``.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Protocol


def utcnow() -> str:
    """Current UTC time as ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


class JobStore(Protocol):
    """Persistence interface shared by the API and the worker."""

    async def create(self, job: dict[str, Any]) -> None: ...
    async def get(self, job_id: str) -> dict[str, Any] | None: ...
    async def update(self, job_id: str, **fields: Any) -> dict[str, Any] | None: ...
    async def list_for(self, owner: str) -> list[dict[str, Any]]: ...
    async def delete(self, job_id: str) -> None: ...
    async def ping(self) -> bool: ...


class MemoryJobStore:
    """Process-local store (single replica only)."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create(self, job: dict[str, Any]) -> None:
        async with self._lock:
            self._jobs[job["id"]] = dict(job)

    async def get(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        return dict(job) if job else None

    async def update(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        async with self._lock:
            if job_id not in self._jobs:
                return None
            self._jobs[job_id].update(fields)
            return dict(self._jobs[job_id])

    async def list_for(self, owner: str) -> list[dict[str, Any]]:
        jobs = [dict(j) for j in self._jobs.values() if j["owner"] == owner]
        return sorted(jobs, key=lambda j: j["created_at"], reverse=True)

    async def delete(self, job_id: str) -> None:
        async with self._lock:
            self._jobs.pop(job_id, None)

    async def ping(self) -> bool:
        return True


class RedisJobStore:
    """Redis-backed store: ``job:<id>`` JSON documents plus a per-owner index."""

    def __init__(self, redis, ttl_s: int) -> None:  # type: ignore[no-untyped-def]
        self.redis, self.ttl_s = redis, ttl_s

    async def create(self, job: dict[str, Any]) -> None:
        pipe = self.redis.pipeline(transaction=True)
        pipe.set(f"job:{job['id']}", json.dumps(job), ex=self.ttl_s)
        pipe.zadd(f"jobs:owner:{job['owner']}", {job["id"]: datetime.fromisoformat(
            job["created_at"]).timestamp()})
        pipe.expire(f"jobs:owner:{job['owner']}", self.ttl_s)
        await pipe.execute()

    async def get(self, job_id: str) -> dict[str, Any] | None:
        raw = await self.redis.get(f"job:{job_id}")
        return json.loads(raw) if raw else None

    async def update(self, job_id: str, **fields: Any) -> dict[str, Any] | None:
        key = f"job:{job_id}"
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    if raw is None:
                        await pipe.unwatch()
                        return None
                    job = json.loads(raw)
                    job.update(fields)
                    pipe.multi()
                    pipe.set(key, json.dumps(job), keepttl=True)
                    await pipe.execute()
                    return job
                except Exception as exc:  # WatchError: retry on concurrent update
                    if type(exc).__name__ != "WatchError":
                        raise

    async def list_for(self, owner: str) -> list[dict[str, Any]]:
        ids = await self.redis.zrevrange(f"jobs:owner:{owner}", 0, 199)
        if not ids:
            return []
        raws = await self.redis.mget([f"job:{i}" for i in ids])
        return [json.loads(r) for r in raws if r]

    async def delete(self, job_id: str) -> None:
        job = await self.get(job_id)
        pipe = self.redis.pipeline(transaction=True)
        pipe.delete(f"job:{job_id}")
        if job:
            pipe.zrem(f"jobs:owner:{job['owner']}", job_id)
        await pipe.execute()

    async def ping(self) -> bool:
        try:
            return bool(await self.redis.ping())
        except Exception:  # noqa: BLE001
            return False
