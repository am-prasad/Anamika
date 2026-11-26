"""Executes sanitisation jobs: the offline pipeline in a sandboxed subprocess.

The API never imports pipeline internals to process data. It runs exactly the command
the evaluator runs (``python main.py --input … --output …``) in a child process with:

* a clean environment (only PATH, locale, the derived ``RAKSHA_SECRET`` and a private
  ``TMPDIR``/``HOME`` inside the job workspace);
* resource limits — address space (``job_memory_mb``), CPU time, no core dumps,
  bounded file descriptors — and optional CPU affinity (``job_cpus``);
* a wall-clock timeout.

The per-release secret is ``HMAC(master_secret, owner/release)``: never stored, never
returned, different for every tenant and release label.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
try:  # POSIX only; on native Windows (development) jobs run without rlimits
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore[assignment]
import subprocess
import time
from pathlib import Path
from typing import Any

from ..core.config import BACKEND_ROOT, Settings
from . import storage
from .jobstore import JobStore, utcnow


class JobError(Exception):
    """A job failure with a closed-vocabulary code (safe to store and return)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def derive_release_secret(master: str, owner: str, release: str) -> str:
    """Per-tenant, per-release ``RAKSHA_SECRET``; never persisted."""
    msg = f"anamika/release/v1/{owner}/{release}".encode()
    return hmac.new(master.encode(), msg, hashlib.sha256).hexdigest()


def _limits(settings: Settings):  # type: ignore[no-untyped-def]
    if resource is None:
        return None
    mem = settings.job_memory_mb * 1024 * 1024
    cpu_s = settings.job_timeout_s * max(settings.job_cpus, 1) + 30
    cpus = settings.job_cpus

    def apply() -> None:  # runs in the child between fork and exec
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
        if cpus and hasattr(os, "sched_setaffinity"):
            avail = sorted(os.sched_getaffinity(0))
            os.sched_setaffinity(0, avail[:cpus])

    return apply


def resolve_policy(settings: Settings, preset: str | None) -> Path | None:
    """Path of a named preset in ``presets_dir`` (``None`` = repository default policy)."""
    if not preset:
        return None
    path = (settings.presets_dir / f"{preset}.yaml").resolve()
    if settings.presets_dir.resolve() not in path.parents or not path.is_file():
        raise JobError("unknown_policy")
    return path


def run_pipeline(settings: Settings, input_dir: Path, output_dir: Path, work_dir: Path,
                 secret: str, policy: Path | None = None, explain_dir: Path | None = None) -> dict[str, Any]:
    """Run the pipeline once; return ``{"exit_code", "seconds"}`` (output is discarded)."""
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = work_dir / f"tmp-{output_dir.name}"
    tmp.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "RAKSHA_SECRET": secret,
        "RAKSHA_INPUT": str(input_dir), "RAKSHA_OUTPUT": str(output_dir),
        "RAKSHA_CPUS": str(settings.job_cpus), "OMP_NUM_THREADS": str(settings.job_cpus),
        "TMPDIR": str(tmp), "HOME": str(tmp),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
    }
    if policy is not None:
        env["ANAMIKA_POLICY"] = str(policy)
    extra = ["--debug-spans", str(explain_dir)] if explain_dir is not None else []
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [settings.pipeline_python, str(settings.pipeline_main), "--input", str(input_dir),
             "--output", str(output_dir), *extra],
            cwd=BACKEND_ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=settings.job_timeout_s,
            preexec_fn=_limits(settings), close_fds=True)
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        raise JobError("pipeline_timeout") from exc
    finally:
        storage.wipe(tmp)
    return {"exit_code": code, "seconds": round(time.monotonic() - t0, 2)}


def _summary(output_dir: Path) -> dict[str, Any]:
    try:
        report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise JobError("report_missing") from exc
    reasons: dict[str, int] = {}
    for f in report.get("files", []):
        if f.get("status") == "quarantined":
            reasons[f.get("reason", "unknown")] = reasons.get(f.get("reason", "unknown"), 0) + 1
    return {"counts": report.get("counts", {}), "entities": report.get("entities", {}),
            "timing": report.get("timing", {}), "resources": report.get("resources", {}),
            "quarantine_reasons": dict(sorted(reasons.items()))}


def _verify(settings: Settings, paths: storage.JobPaths, input_dir: Path, secret: str,
            rotated: str, policy: Path | None) -> tuple[dict[str, Any], Path]:
    from tools.determinism import file_hashes, pseudonyms

    base = file_hashes(paths.output)
    again = paths.work / "verify-same"
    other = paths.work / "verify-rotated"
    r1 = run_pipeline(settings, input_dir, again, paths.work, secret, policy)
    r2 = run_pipeline(settings, input_dir, other, paths.work, rotated, policy)
    same = file_hashes(again)
    rot = file_hashes(other)
    p_base, p_rot = pseudonyms(paths.output), pseudonyms(other)
    result = {
        "determinism": {"files_total": len(base),
                        "files_identical": sum(same.get(k) == v for k, v in base.items()),
                        "exit_code": r1["exit_code"]},
        "rotation": {"files_changed": sum(rot.get(k) != v for k, v in base.items()),
                     "pseudonyms_total": len(p_base),
                     "pseudonyms_reused": len(p_base & p_rot), "exit_code": r2["exit_code"]},
    }
    storage.wipe(again)
    return result, other


def _utility(paths: storage.JobPaths, input_dir: Path, truth: Path) -> dict[str, Any]:
    from tools.utility_check import check

    res = check(paths.output, input_dir, truth, 0)
    res.pop("worst_files", None)
    return res


def _attack(paths: storage.JobPaths, rotated: Path | None, input_dir: Path, truth: Path,
            attacker: Path) -> dict[str, Any]:
    from tools.attacker import run

    return run(paths.output, rotated, input_dir, truth, attacker)


def _leak_scan(paths: storage.JobPaths, input_dir: Path, truth: Path) -> dict[str, Any]:
    from tools.leak_scan import scan

    # Side channels are logs, temp files and stray artefacts. The determinism reruns under
    # work/ are full releases with their own legitimate kept values (e.g. "Ward 3"); they are
    # checked byte for byte against this release, so only their logs count as side channels.
    extras: list[Path] = []
    if paths.work.is_dir():
        for p in sorted(paths.work.iterdir()):
            if p.is_dir() and (p / "report.json").is_file():
                if (p / "logs").is_dir():
                    extras.append(p / "logs")
            else:
                extras.append(p)
    res = scan(paths.output, input_dir, truth, extras)
    res.pop("worst_files", None)  # hashed file ids are of no use to API clients
    return res


def resolve_input(settings: Settings, job: dict[str, Any],
                  paths: storage.JobPaths) -> tuple[Path, Path | None, Path | None]:
    """Input directory, optional answer key and optional attacker folder for a job."""
    source = job["source"]
    if source == "upload":
        return paths.input, None, None
    name = source.split(":", 1)[1]
    if settings.datasets_dir is None:
        raise JobError("dataset_unavailable")
    root = (settings.datasets_dir / name).resolve()
    if settings.datasets_dir.resolve() not in root.parents or not (root / "input").is_dir():
        raise JobError("dataset_unavailable")
    truth = root / "truth" / "truth.json"
    attacker = root / "attacker"
    return (root / "input", truth if truth.is_file() else None,
            attacker if (attacker / "registry.csv").is_file() else None)


async def execute_job(job_id: str, store: JobStore, settings: Settings) -> None:
    """Run one job end to end and record its outcome (never raises)."""
    job = await store.get(job_id)
    if job is None or job["status"] != "queued":
        return
    paths = storage.job_paths(settings.data_dir, job_id)
    await store.update(job_id, status="running", started_at=utcnow())
    try:
        if settings.master_secret is None:
            raise JobError("service_not_configured")
        master = settings.master_secret.get_secret_value()
        secret = derive_release_secret(master, job["owner"], job["release"])
        input_dir, truth, attacker = resolve_input(settings, job, paths)
        opts = job["options"]
        policy = resolve_policy(settings, opts.get("policy"))
        explain_dir = paths.explain if opts.get("explain") else None
        run = await asyncio.to_thread(run_pipeline, settings, input_dir, paths.output,
                                      paths.work, secret, policy, explain_dir)
        if run["exit_code"] != 0:
            raise JobError("pipeline_failed")
        summary = _summary(paths.output)
        summary["wall_seconds"] = run["seconds"]
        summary["policy"] = opts.get("policy") or "default"
        verification: dict[str, Any] = {}
        rotated_release: Path | None = None
        if opts.get("verify_determinism"):
            rotated = derive_release_secret(master, job["owner"], job["release"] + "~rotation")
            result, rotated_release = await asyncio.to_thread(
                _verify, settings, paths, input_dir, secret, rotated, policy)
            verification.update(result)
        if opts.get("leak_scan"):
            verification["leak_scan"] = (await asyncio.to_thread(_leak_scan, paths, input_dir, truth)
                                         if truth else {"available": False})
        if opts.get("utility"):
            verification["utility"] = (await asyncio.to_thread(_utility, paths, input_dir, truth)
                                       if truth else {"available": False})
        if opts.get("attack"):
            verification["attack"] = (await asyncio.to_thread(_attack, paths, rotated_release, input_dir,
                                                              truth, attacker)
                                      if truth and attacker else {"available": False})
        await asyncio.to_thread(storage.build_archive, paths)
        await store.update(job_id, status="succeeded", finished_at=utcnow(), summary=summary,
                           verification=verification or None)
    except JobError as exc:
        await store.update(job_id, status="failed", finished_at=utcnow(), error=exc.code)
    except Exception as exc:  # noqa: BLE001 - record a class name only, never a message
        await store.update(job_id, status="failed", finished_at=utcnow(),
                           error="internal." + type(exc).__name__.lower())
    finally:
        if not settings.retain_inputs:
            storage.wipe(paths.input)
        storage.wipe(paths.work)
        paths.work.mkdir(exist_ok=True, mode=0o700)


async def cleanup_expired(store: JobStore, settings: Settings) -> int:
    """Delete workspaces whose job is gone (TTL) or older than ``job_ttl_hours``."""
    removed = 0
    root = storage.jobs_root(settings.data_dir)
    cutoff = time.time() - settings.job_ttl_hours * 3600
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not storage.JOB_ID.fullmatch(d.name):
            continue
        job = await store.get(d.name)
        if job is None or d.stat().st_mtime < cutoff:
            storage.wipe(d)
            if job is not None:
                await store.delete(d.name)
            removed += 1
    return removed
