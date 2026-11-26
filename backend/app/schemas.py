"""Request / response models of the public API."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

RELEASE_PATTERN = r"^[a-z0-9][a-z0-9-]{0,31}$"


class JobStatus(str, Enum):
    """Lifecycle of a sanitisation job."""

    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class JobOptions(BaseModel):
    """What to run besides the pipeline itself."""

    release: str = Field("default", pattern=RELEASE_PATTERN,
                         description="release label; the per-release secret is derived from it")
    policy: str | None = Field(None, pattern=r"^[a-z][a-z0-9_-]{0,31}$",
                               description="privacy preset name (see /api/v1/policy/presets)")
    verify_determinism: bool = Field(False, description="re-run with the same and a rotated secret")
    leak_scan: bool = Field(False, description="scorer-style leak scan (datasets with an answer key)")
    utility: bool = Field(False, description="preserve-probes and token retention (datasets with an answer key)")
    attack: bool = Field(False, description="attack arena A1-A7 (datasets with an answer key and attacker files)")
    explain: bool = Field(False, description="value-free span / role / linkage explanations for the console")


class DatasetJobRequest(JobOptions):
    """Create a job from a server-side, allow-listed dataset."""

    dataset: str = Field(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class JobView(BaseModel):
    """Public view of a job. Never contains file names, secrets or record content."""

    id: str
    status: JobStatus
    source: str
    release: str
    options: dict[str, Any]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    input_files: int = 0
    error: str | None = None
    summary: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None


class JobList(BaseModel):
    """A caller's jobs, newest first."""

    items: list[JobView]


class FileItem(BaseModel):
    """One exported file of a release."""

    path: str
    bytes: int
    sha256: str


class FileList(BaseModel):
    """Files of a release under ``sanitized/``."""

    items: list[FileItem]


class RecordPage(BaseModel):
    """A page of ``records.jsonl``."""

    total: int
    offset: int
    limit: int
    items: list[dict[str, Any]]


class DatasetList(BaseModel):
    """Allow-listed server-side datasets."""

    items: list[dict[str, Any]]
