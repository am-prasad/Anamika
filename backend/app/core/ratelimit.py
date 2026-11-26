"""Fixed-window rate limiting with a Redis backend (shared across replicas) or memory.

Limits are expressed as ``"<count>/<second|minute|hour|day>"`` and applied per bucket and
per principal (API key) — or per client IP for unauthenticated routes. Responses carry
``X-RateLimit-*`` headers; exceeding a limit returns 429 with ``Retry-After``.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from fastapi import HTTPException, Request, Response, status

_PERIODS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


@dataclass(frozen=True)
class Limit:
    """A parsed rate limit."""

    count: int
    period_s: int

    @classmethod
    def parse(cls, spec: str) -> "Limit":
        """Parse ``"10/minute"``."""
        n, _, unit = spec.partition("/")
        unit = unit.strip().rstrip("s")
        if unit not in _PERIODS or not n.strip().isdigit() or int(n) < 1:
            raise ValueError("invalid rate limit spec")
        return cls(int(n), _PERIODS[unit])


class RateLimitBackend(Protocol):
    """Counts hits in a window; returns the count after this hit."""

    async def hit(self, key: str, window_s: int) -> int: ...


class MemoryBackend:
    """Single-process backend (development / tests)."""

    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, window_s: int) -> int:
        now = time.monotonic()
        async with self._lock:
            if len(self._counts) > 50_000:  # bound memory: drop expired entries
                self._counts = {k: v for k, v in self._counts.items() if v[1] > now}
            count, expires = self._counts.get(key, (0, now + window_s))
            if expires <= now:
                count, expires = 0, now + window_s
            count += 1
            self._counts[key] = (count, expires)
            return count


class RedisBackend:
    """Shared backend: atomic INCR + EXPIRE in one round trip."""

    def __init__(self, redis) -> None:  # type: ignore[no-untyped-def]
        self.redis = redis

    async def hit(self, key: str, window_s: int) -> int:
        pipe = self.redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, window_s, nx=True)
        count, _ = await pipe.execute()
        return int(count)


def client_identity(request: Request) -> str:
    """Principal id if authenticated, else the client IP."""
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        return principal.id
    return "ip:" + (request.client.host if request.client else "unknown")


def rate_limit(bucket: str, setting: str) -> Callable[[Request, Response], Awaitable[None]]:
    """FastAPI dependency enforcing the limit named by settings attribute ``setting``."""

    async def dependency(request: Request, response: Response) -> None:
        settings = request.app.state.settings
        limit = Limit.parse(getattr(settings, setting))
        window = int(time.time() // limit.period_s)
        key = f"rl:{bucket}:{client_identity(request)}:{window}"
        count = await request.app.state.ratelimit.hit(key, limit.period_s)
        reset = (window + 1) * limit.period_s - int(time.time())
        remaining = max(limit.count - count, 0)
        headers = {"X-RateLimit-Limit": str(limit.count),
                   "X-RateLimit-Remaining": str(remaining),
                   "X-RateLimit-Reset": str(reset)}
        if count > limit.count:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited",
                                headers={**headers, "Retry-After": str(max(reset, 1))})
        response.headers.update(headers)
        request.state.ratelimit_headers = headers  # also applied to FileResponses by middleware

    return dependency
