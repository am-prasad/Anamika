"""Sanitisation jobs: create (upload or dataset), inspect, download, delete."""
from __future__ import annotations

import json
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


def _new_job(principal: Principal, source: str, opts: JobOptions, n_files: int) -> dict[str, Any]:
    return {"id": uuid.uuid4().hex, "owner": principal.id, "status": JobStatus.queued.value,
            "source": source, "release": opts.release,
            "options": {"verify_determinism": opts.verify_determinism,
                        "leak_scan": opts.leak_scan},
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
        opts = JobOptions(release=form.get("release") or "default",
                          verify_determinism=_bool(form.get("verify_determinism")),
                          leak_scan=_bool(form.get("leak_scan")))
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid_options") from exc
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


@router.delete("/{job_id}", status_code=204, dependencies=READ)
async def delete_job(job: dict[str, Any] = Depends(owned_job),
                     settings: Settings = Depends(settings_dep),
                     store: JobStore = Depends(store_dep)) -> None:
    """Delete a finished job and every byte of its workspace."""
    if job["status"] in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "job_active")
    storage.wipe(storage.job_paths(settings.data_dir, job["id"]).root)
    await store.delete(job["id"])
