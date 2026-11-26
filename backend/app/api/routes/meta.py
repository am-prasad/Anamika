"""Health probes, the active privacy policy and the dataset allow-list."""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from anamika.policy import load_policy

from ...core.config import Settings
from ...core.ratelimit import rate_limit
from ...core.security import require_principal
from ...schemas import DatasetList
from ...services import storage
from ..deps import settings_dep

router = APIRouter(tags=["meta"])
READ = [Depends(require_principal), Depends(rate_limit("default", "rate_default"))]


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Liveness: the process answers."""
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz(request: Request) -> JSONResponse:
    """Readiness: store reachable, workspace writable, secret configured."""
    settings: Settings = request.app.state.settings
    checks = {"store": await request.app.state.store.ping(),
              "storage": os.access(storage.jobs_root(settings.data_dir), os.W_OK),
              "secret": settings.master_secret is not None}
    ok = all(checks.values())
    return JSONResponse({"status": "ready" if ok else "not_ready", "checks": checks},
                        status_code=200 if ok else 503)


def _plain(obj: Any) -> Any:
    if hasattr(obj, "items"):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


@router.get("/api/v1/policy", dependencies=READ)
async def get_policy() -> dict[str, Any]:
    """The privacy policy the pipeline runs with (``config/policy.yaml``)."""
    return _plain(load_policy())


@router.get("/api/v1/datasets", response_model=DatasetList, dependencies=READ)
async def list_datasets(settings: Settings = Depends(settings_dep)) -> DatasetList:
    """Server-side datasets that jobs may reference by name."""
    items = []
    root = settings.datasets_dir
    if root is not None and root.is_dir():
        for d in sorted(root.iterdir()):
            if (d / "input").is_dir():
                items.append({"name": d.name,
                              "files": sum(1 for p in (d / "input").rglob("*") if p.is_file()),
                              "has_answer_key": (d / "truth" / "truth.json").is_file()})
    return DatasetList(items=items)
