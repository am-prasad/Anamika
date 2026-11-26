"""Sanitisation jobs: create (upload or dataset), inspect, download, delete."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from itertools import islice
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from ...core.config import Settings
from ...core.ratelimit import rate_limit
from ...core.security import Principal, require_principal
from ...schemas import (DatasetJobRequest, FileList, JobList, JobOptions, JobStatus, JobView,
                        RecordPage)
from ...services import storage
from ...services.jobstore import JobStore, utcnow
from ...services.queue import JobQueue
from ..deps import owned_job, queue_dep, settings_dep, store_dep

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"],
                   dependencies=[Depends(require_principal)])
CREATE = [Depends(require_principal), Depends(rate_limit("jobs-create", "rate_jobs_create"))]
READ = [Depends(require_principal), Depends(rate_limit("default", "rate_default"))]
DOWNLOAD = [Depends(require_principal), Depends(rate_limit("downloads", "rate_downloads"))]
ACTIVE = {JobStatus.queued.value, JobStatus.running.value}


def _view(job: dict[str, Any]) -> JobView:
    return JobView(**{k: v for k, v in job.items() if k != "owner"})


async def _check_capacity(store: JobStore, settings: Settings, principal: Principal) -> None:
    active = [j for j in await store.list_for(principal.id) if j["status"] in ACTIVE]
    if len(active) >= settings.max_active_jobs_per_principal:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_active_jobs")


def _check_policy(settings: Settings, opts: JobOptions) -> None:
    if opts.policy and not (settings.presets_dir / f"{opts.policy}.yaml").is_file():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown_policy")


def _new_job(principal: Principal, source: str, opts: JobOptions, n_files: int) -> dict[str, Any]:
    return {"id": uuid.uuid4().hex, "owner": principal.id, "status": JobStatus.queued.value,
            "source": source, "release": opts.release,
            "options": {"policy": opts.policy, "verify_determinism": opts.verify_determinism,
                        "leak_scan": opts.leak_scan, "utility": opts.utility, "attack": opts.attack,
                        "explain": opts.explain},
            "created_at": utcnow(), "started_at": None, "finished_at": None,
            "input_files": n_files, "error": None, "summary": None, "verification": None}


def _bool(v: Any) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


@router.post("", status_code=202, response_model=JobView, dependencies=CREATE,
             summary="Upload an export (multipart, one part per file) and sanitise it")
async def create_upload_job(request: Request, principal: Principal = Depends(require_principal),
                            settings: Settings = Depends(settings_dep),
                            store: JobStore = Depends(store_dep),
                            queue: JobQueue = Depends(queue_dep)) -> JobView:
    """Multipart fields: ``files`` (repeat; the part filename is the relative path),
    optional ``release``, ``verify_determinism``, ``leak_scan``."""
    await _check_capacity(store, settings, principal)
    form = await request.form(max_files=settings.max_upload_files, max_fields=16)
    try:
        opts = JobOptions(release=form.get("release") or "default", policy=form.get("policy") or None,
                          verify_determinism=_bool(form.get("verify_determinism")),
                          leak_scan=_bool(form.get("leak_scan")), utility=_bool(form.get("utility")),
                          attack=_bool(form.get("attack")), explain=_bool(form.get("explain")))
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_options") from exc
    _check_policy(settings, opts)
    uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
    if not uploads:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no_files")
    job = _new_job(principal, "upload", opts, len(uploads))
    paths = storage.job_paths(settings.data_dir, job["id"])
    storage.create_workspace(paths)
    budget = [settings.max_request_mb * 1024 * 1024]
    try:
        for up in uploads:
            rel = storage.safe_relpath(up.filename or "", settings.max_path_depth)
            storage.store_upload(paths.input, rel, up.file, budget)
    except HTTPException:
        storage.wipe(paths.root)
        raise
    finally:
        await form.close()
    await store.create(job)
    await queue.enqueue(job["id"])
    return _view(job)


@router.post("/from-dataset", status_code=202, response_model=JobView, dependencies=CREATE,
             summary="Sanitise an allow-listed server-side dataset")
async def create_dataset_job(body: DatasetJobRequest,
                             principal: Principal = Depends(require_principal),
                             settings: Settings = Depends(settings_dep),
                             store: JobStore = Depends(store_dep),
                             queue: JobQueue = Depends(queue_dep)) -> JobView:
    """Runs on ``<datasets_dir>/<dataset>/input`` (read-only, never copied)."""
    root = settings.datasets_dir
    if root is None or not (root / body.dataset / "input").is_dir() \
            or root.resolve() not in (root / body.dataset).resolve().parents:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset_not_found")
    await _check_capacity(store, settings, principal)
    _check_policy(settings, body)
    n = sum(1 for p in (root / body.dataset / "input").rglob("*") if p.is_file())
    job = _new_job(principal, f"dataset:{body.dataset}", body, n)
    storage.create_workspace(storage.job_paths(settings.data_dir, job["id"]))
    await store.create(job)
    await queue.enqueue(job["id"])
    return _view(job)


@router.get("", response_model=JobList, dependencies=READ)
async def list_jobs(principal: Principal = Depends(require_principal),
                    store: JobStore = Depends(store_dep)) -> JobList:
    """The caller's jobs, newest first."""
    return JobList(items=[_view(j) for j in await store.list_for(principal.id)])


@router.get("/{job_id}", response_model=JobView, dependencies=READ)
async def get_job(job: dict[str, Any] = Depends(owned_job)) -> JobView:
    """Status, counts, timing and verification results of one job."""
    return _view(job)


def _done(job: dict[str, Any]) -> None:
    if job["status"] != JobStatus.succeeded.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "job_not_succeeded")


@router.get("/{job_id}/report", dependencies=READ)
async def get_report(job: dict[str, Any] = Depends(owned_job),
                     settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    """The release's ``report.json``."""
    _done(job)
    p = storage.job_paths(settings.data_dir, job["id"]).output / "report.json"
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/{job_id}/records", response_model=RecordPage, dependencies=READ)
async def get_records(job: dict[str, Any] = Depends(owned_job),
                      settings: Settings = Depends(settings_dep),
                      offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)
                      ) -> RecordPage:
    """A page of ``records.jsonl``."""
    _done(job)
    p = storage.job_paths(settings.data_dir, job["id"]).output / "records.jsonl"
    with open(p, encoding="utf-8") as fh:
        total = sum(1 for _ in fh)
    with open(p, encoding="utf-8") as fh:
        items = [json.loads(line) for line in islice(fh, offset, offset + limit)]
    return RecordPage(total=total, offset=offset, limit=limit, items=items)


@router.get("/{job_id}/files", response_model=FileList, dependencies=READ)
async def list_files(job: dict[str, Any] = Depends(owned_job),
                     settings: Settings = Depends(settings_dep)) -> FileList:
    """Every sanitised file with size and SHA-256."""
    _done(job)
    return FileList(items=storage.list_release(storage.job_paths(settings.data_dir, job["id"])))


@router.get("/{job_id}/files/{file_path:path}", dependencies=DOWNLOAD,
            response_class=FileResponse)
async def download_file(file_path: str, job: dict[str, Any] = Depends(owned_job),
                        settings: Settings = Depends(settings_dep)) -> FileResponse:
    """One sanitised file, always as an attachment (never rendered by the browser)."""
    _done(job)
    target = storage.resolve_release_file(storage.job_paths(settings.data_dir, job["id"]),
                                          file_path, settings.max_path_depth)
    return FileResponse(target, media_type="application/octet-stream", filename=target.name)


@router.get("/{job_id}/archive", dependencies=DOWNLOAD, response_class=FileResponse)
async def download_archive(job: dict[str, Any] = Depends(owned_job),
                           settings: Settings = Depends(settings_dep)) -> FileResponse:
    """The whole release (``sanitized/``, ``report.json``, ``records.jsonl``) as a zip."""
    _done(job)
    paths = storage.job_paths(settings.data_dir, job["id"])
    if not paths.archive.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "archive_not_found")
    return FileResponse(paths.archive, media_type="application/zip",
                        filename=f"anamika-release-{job['id'][:8]}.zip")


def _explain_dir(settings: Settings, job: dict[str, Any]) -> Any:
    _done(job)
    d = storage.job_paths(settings.data_dir, job["id"]).explain
    if not job["options"].get("explain") or not d.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "explain_not_requested")
    return d


@router.get("/{job_id}/explain", dependencies=READ)
async def explain_index(job: dict[str, Any] = Depends(owned_job),
                        settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    """Per-file summaries of what was detected (types and rule counts; never values)."""
    d = _explain_dir(settings, job)
    items = []
    for p in sorted(d.glob("*.json")):
        if p.name == "linkage.json":
            continue
        info = json.loads(p.read_text(encoding="utf-8"))
        types: dict[str, int] = {}
        for sp in info.get("spans", []):
            types[sp["type"]] = types.get(sp["type"], 0) + 1
        items.append({"key": p.stem, "output": info.get("output"), "format": info.get("format"),
                      "records": info.get("records"), "span_types": types,
                      "columns": len(info.get("columns", [])), "fields": len(info.get("fields", []))})
    return {"items": items}


@router.get("/{job_id}/explain/{key}", dependencies=READ)
async def explain_file(key: str, job: dict[str, Any] = Depends(owned_job),
                       settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    """Full value-free explanation of one file: spans with offsets, types and rules."""
    if not re.fullmatch(r"[0-9a-f]{16}", key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "explain_not_found")
    p = _explain_dir(settings, job) / f"{key}.json"
    if not p.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "explain_not_found")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/{job_id}/graph", dependencies=READ)
async def identity_graph(job: dict[str, Any] = Depends(owned_job),
                         settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    """Identity graph: records → pseudonyms with the evidence *types* that linked them, and
    pairs deliberately kept apart (conflicting identifiers). Never contains values."""
    p = _explain_dir(settings, job) / "linkage.json"
    if not p.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "graph_not_available")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/{job_id}/compare/{file_path:path}", dependencies=DOWNLOAD)
async def compare_file(file_path: str, job: dict[str, Any] = Depends(owned_job),
                       settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    """Original and sanitised text side by side — demo only, synthetic server-side datasets."""
    _done(job)
    if not settings.allow_originals or not job["source"].startswith("dataset:"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "originals_disabled")
    paths = storage.job_paths(settings.data_dir, job["id"])
    target = storage.resolve_release_file(paths, file_path, settings.max_path_depth)
    report = json.loads((paths.output / "report.json").read_text(encoding="utf-8"))
    out_rel = "sanitized/" + target.relative_to((paths.output / "sanitized").resolve()).as_posix()
    sha = next((e["input_sha256"] for e in report["files"] if e.get("output") == out_rel), None)
    root = settings.datasets_dir / job["source"].split(":", 1)[1] / "input"  # type: ignore[operator]
    original = None
    for p in sorted(root.rglob("*")):
        if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == sha:
            original = p
            break
    if original is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "original_not_found")
    from anamika.ingest.sniff import QuarantineError, decode_bytes

    try:
        orig_text = decode_bytes(original.read_bytes()).text
    except QuarantineError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "original_not_text") from exc
    explain = paths.explain / f"{sha[:16]}.json"
    return {"path": out_rel, "original": orig_text, "sanitized": target.read_text(encoding="utf-8"),
            "explain": json.loads(explain.read_text(encoding="utf-8")) if explain.is_file() else None}


@router.delete("/{job_id}", status_code=204, dependencies=READ)
async def delete_job(job: dict[str, Any] = Depends(owned_job),
                     settings: Settings = Depends(settings_dep),
                     store: JobStore = Depends(store_dep)) -> None:
    """Delete a finished job and every byte of its workspace."""
    if job["status"] in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "job_active")
    storage.wipe(storage.job_paths(settings.data_dir, job["id"]).root)
    await store.delete(job["id"])
