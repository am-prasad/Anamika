"""Shared FastAPI dependencies."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from ..core.config import Settings
from ..core.security import Principal, require_principal
from ..services.jobstore import JobStore
from ..services.queue import JobQueue


def settings_dep(request: Request) -> Settings:
    """The app's settings (allows per-app overrides in tests)."""
    return request.app.state.settings


def store_dep(request: Request) -> JobStore:
    return request.app.state.store


def queue_dep(request: Request) -> JobQueue:
    return request.app.state.queue


async def owned_job(job_id: str, principal: Principal = Depends(require_principal),
                    store: JobStore = Depends(store_dep)) -> dict[str, Any]:
    """The job if it belongs to the caller; 404 otherwise (existence is not revealed)."""
    job = await store.get(job_id) if len(job_id) == 32 else None
    if job is None or job["owner"] != principal.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")
    return job
