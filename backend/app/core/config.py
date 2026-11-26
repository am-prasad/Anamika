"""Service configuration, loaded from ``ANAMIKA_*`` environment variables (or ``.env``).

Every security-relevant default is conservative: authentication is on, docs are off in
production, uploads are bounded, and the master secret is mandatory before any job runs.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    """All tunables of the API and worker. See ``.env.example`` for documentation."""

    model_config = SettingsConfigDict(env_prefix="ANAMIKA_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"

    # --- authentication
    api_keys_sha256: str = Field("", description="comma-separated SHA-256 hex of accepted API keys")
    auth_disabled: bool = False

    # --- secrets: the per-release RAKSHA_SECRET is derived from this, never stored
    master_secret: SecretStr | None = None

    # --- infrastructure
    redis_url: str | None = None
    queue_mode: Literal["inline", "redis"] = "inline"
    data_dir: Path = BACKEND_ROOT / ".data"
    datasets_dir: Path | None = None
    presets_dir: Path = REPO_ROOT / "config" / "presets"
    allow_originals: bool = False  # demo only: serve original files of server-side synthetic datasets

    # --- HTTP hardening
    cors_origins: str = "http://localhost:3000"
    trusted_hosts: str = "localhost,127.0.0.1,testserver,api"
    max_request_mb: int = 256
    max_upload_files: int = 5000
    max_path_depth: int = 12

    # --- rate limits ("<count>/<second|minute|hour|day>")
    rate_default: str = "120/minute"
    rate_jobs_create: str = "10/minute"
    rate_downloads: str = "300/minute"

    # --- jobs
    max_active_jobs_per_principal: int = 3
    inline_concurrency: int = 2
    job_timeout_s: int = 900
    job_ttl_hours: int = 24
    job_memory_mb: int = 4096
    job_cpus: int = 2
    retain_inputs: bool = False
    pipeline_python: str = sys.executable
    pipeline_main: Path = BACKEND_ROOT / "main.py"

    @field_validator("data_dir", mode="after")
    @classmethod
    def _abs(cls, v: Path) -> Path:
        return v.resolve()

    @model_validator(mode="after")
    def _guard(self) -> "Settings":
        if self.auth_disabled and self.env == "production":
            raise ValueError("auth cannot be disabled in production")
        if self.queue_mode == "redis" and not self.redis_url:
            raise ValueError("queue_mode=redis requires ANAMIKA_REDIS_URL")
        if self.allow_originals and self.env == "production":
            raise ValueError("original files may not be served in production")
        if self.env == "production" and not self.api_keys:
            raise ValueError("production requires at least one API key hash")
        return self

    @property
    def api_keys(self) -> list[str]:
        """Accepted API-key hashes (lower-case SHA-256 hex)."""
        return [k.lower() for k in _csv(self.api_keys_sha256)]

    @property
    def cors_origin_list(self) -> list[str]:
        """Origins allowed by CORS (the Next.js frontend)."""
        return _csv(self.cors_origins)

    @property
    def trusted_host_list(self) -> list[str]:
        """Host headers the API answers to."""
        return _csv(self.trusted_hosts)

    @property
    def docs_enabled(self) -> bool:
        """OpenAPI docs are served outside production only."""
        return self.env != "production"


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()
