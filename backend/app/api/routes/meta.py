"""Health probes, the active privacy policy and the dataset allow-list."""
from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
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
async def get_policy(preset: str | None = None, settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    """The default privacy policy (``config/policy.yaml``) or a named preset."""
    if preset is None:
        return _plain(load_policy())
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", preset) or not (settings.presets_dir / f"{preset}.yaml").is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown_policy")
    return _plain(load_policy(settings.presets_dir / f"{preset}.yaml"))


@router.get("/api/v1/policy/presets", dependencies=READ)
async def list_presets(settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    """Privacy presets with their key knobs and description (for the console's slider)."""
    items = []
    if settings.presets_dir.is_dir():
        for p in sorted(settings.presets_dir.glob("*.yaml")):
            pol = load_policy(p)
            items.append({"name": p.stem, "description": pol.get("description", ""),
                          "location_level": pol["location"]["level"],
                          "age_band_years": pol["ages"]["band_years"],
                          "pin_digits": pol["location"]["pin_digits"],
                          "rare_k": pol.get("kanon", {}).get("rare_k", 0),
                          "measured": _plain(pol.get("measured", {}))})
    return {"items": items}


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
                              "has_answer_key": (d / "truth" / "truth.json").is_file(),
                              "has_attacker": (d / "attacker" / "registry.csv").is_file()})
    return DatasetList(items=items)
