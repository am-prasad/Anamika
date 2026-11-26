"""Job workspace on disk: path safety, bounded uploads, listings and archives.

Layout per job (all ``0700``)::

    <data_dir>/jobs/<job_id>/input/     uploaded raw files (deleted after the run unless retained)
    <data_dir>/jobs/<job_id>/output/    sanitized/, report.json, records.jsonl
    <data_dir>/jobs/<job_id>/work/      private TMPDIR/HOME for the pipeline, verification runs
    <data_dir>/jobs/<job_id>/release.zip
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from fastapi import HTTPException, status

JOB_ID = re.compile(r"^[0-9a-f]{32}$")
_BAD_SEGMENT = re.compile(r"[\x00-\x1f\x7f<>:\"|?*]")
CHUNK = 1024 * 1024


@dataclass(frozen=True)
class JobPaths:
    """Directories of one job."""

    root: Path

    @property
    def input(self) -> Path:
        return self.root / "input"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def archive(self) -> Path:
        return self.root / "release.zip"


def jobs_root(data_dir: Path) -> Path:
    """``<data_dir>/jobs``, created with private permissions."""
    root = data_dir / "jobs"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def job_paths(data_dir: Path, job_id: str) -> JobPaths:
    """Paths of ``job_id`` (validated: 32 lowercase hex chars)."""
    if not JOB_ID.fullmatch(job_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job_not_found")
    return JobPaths(jobs_root(data_dir) / job_id)


def create_workspace(paths: JobPaths) -> None:
    """Create a fresh job workspace with ``0700`` directories."""
    old = os.umask(0o077)
    try:
        for d in (paths.root, paths.input, paths.output, paths.work):
            d.mkdir(parents=True, exist_ok=True, mode=0o700)
    finally:
        os.umask(old)


def safe_relpath(name: str, max_depth: int) -> PurePosixPath:
    """Validate a client-supplied relative path; 400 on traversal or odd characters."""
    norm = unicodedata.normalize("NFC", (name or "").replace("\\", "/")).strip()
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if (not parts or len(parts) > max_depth or norm.startswith("/") or any(
            p == ".." or len(p) > 255 or _BAD_SEGMENT.search(p) for p in parts)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_file_path")
    return PurePosixPath(*parts)


def store_upload(root: Path, rel: PurePosixPath, stream: BinaryIO, budget: list[int]) -> int:
    """Copy ``stream`` to ``root/rel`` in chunks, enforcing the shared byte ``budget``."""
    dest = root.joinpath(*rel.parts)
    if root.resolve() not in dest.resolve().parents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_file_path")
    if dest.exists():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "duplicate_file_path")
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    written = 0
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        while chunk := stream.read(CHUNK):
            written += len(chunk)
            budget[0] -= len(chunk)
            if budget[0] < 0:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "upload_too_large")
            fh.write(chunk)
    return written


def list_release(paths: JobPaths) -> list[dict]:
    """Every file under ``output/sanitized`` with size and SHA-256, sorted."""
    san = paths.output / "sanitized"
    items = []
    if san.is_dir():
        for p in sorted(san.rglob("*")):
            if p.is_file():
                items.append({"path": p.relative_to(san).as_posix(), "bytes": p.stat().st_size,
                              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    return items


def resolve_release_file(paths: JobPaths, rel: str, max_depth: int) -> Path:
    """Absolute path of an exported file; 404 if it is not inside ``sanitized/``."""
    clean = safe_relpath(rel, max_depth)
    san = (paths.output / "sanitized").resolve()
    target = san.joinpath(*clean.parts).resolve()
    if san not in target.parents or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file_not_found")
    return target


def build_archive(paths: JobPaths) -> Path:
    """Zip ``sanitized/``, ``report.json`` and ``records.jsonl`` deterministically."""
    tmp = paths.archive.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(paths.output.rglob("*")):
            if p.is_file():
                info = zipfile.ZipInfo(p.relative_to(paths.output).as_posix(),
                                       date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, p.read_bytes())
    os.replace(tmp, paths.archive)
    return paths.archive


def wipe(path: Path) -> None:
    """Remove a directory tree (best effort, never raises)."""
    shutil.rmtree(path, ignore_errors=True)
