"""API (S4): presets, explain / graph, compare (demo-only), utility verification."""
from __future__ import annotations

import io
import json
import shutil
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT, Settings
from app.core.security import hash_key
from app.main import create_app

K1 = "s4-test-key-0123456789"
NOTE = "Name: Zorawar Pundir\nMob: 9876501234\nDate of Admission: 03-10-2026\nParacetamol 650 mg 1-0-1\n"


def make(tmp_path: Path, **kw) -> Settings:
    presets = tmp_path / "presets"
    presets.mkdir(exist_ok=True)
    base = yaml.safe_load((REPO_ROOT / "config" / "policy.yaml").read_text())
    for name, level in (("strict", "district"), ("research", "tehsil")):
        d = dict(base, description=f"{name} preset")
        d["location"] = dict(base["location"], level=level)
        (presets / f"{name}.yaml").write_text(yaml.safe_dump(d))
    ds = tmp_path / "datasets" / "demo" / "input"
    ds.mkdir(parents=True, exist_ok=True)
    (ds / "note.txt").write_text(NOTE, encoding="utf-8")
    args = dict(_env_file=None, env="test", api_keys_sha256=hash_key(K1), master_secret="m",
                data_dir=tmp_path / "data", presets_dir=presets, datasets_dir=tmp_path / "datasets",
                rate_default="1000/minute", rate_jobs_create="1000/minute", rate_downloads="1000/minute",
                job_timeout_s=120, job_memory_mb=2048)
    args.update(kw)
    return Settings(**args)


H = {"X-API-Key": K1}


def wait(c: TestClient, job_id: str) -> dict:
    for _ in range(400):
        j = c.get(f"/api/v1/jobs/{job_id}", headers=H).json()
        if j["status"] in ("succeeded", "failed"):
            return j
        time.sleep(0.2)
    raise AssertionError("timeout")


def test_presets_listed_and_selectable(tmp_path: Path) -> None:
    with TestClient(create_app(make(tmp_path))) as c:
        items = c.get("/api/v1/policy/presets", headers=H).json()["items"]
        assert {i["name"] for i in items} == {"strict", "research"}
        assert c.get("/api/v1/policy?preset=strict", headers=H).json()["location"]["level"] == "district"
        assert c.get("/api/v1/policy?preset=../x", headers=H).status_code == 404
        r = c.post("/api/v1/jobs/from-dataset", headers=H, json={"dataset": "demo", "policy": "nope"})
        assert r.status_code == 400 and r.json()["error"] == "unknown_policy"
        r = c.post("/api/v1/jobs/from-dataset", headers=H, json={"dataset": "demo", "policy": "strict"})
        done = wait(c, r.json()["id"])
        assert done["status"] == "succeeded" and done["summary"]["policy"] == "strict"


def test_explain_and_graph_are_value_free(tmp_path: Path) -> None:
    with TestClient(create_app(make(tmp_path))) as c:
        r = c.post("/api/v1/jobs/from-dataset", headers=H, json={"dataset": "demo", "explain": True})
        job = wait(c, r.json()["id"])
        assert job["status"] == "succeeded"
        idx = c.get(f"/api/v1/jobs/{job['id']}/explain", headers=H).json()["items"]
        assert len(idx) == 1 and idx[0]["span_types"].get("PHONE") == 1
        one = c.get(f"/api/v1/jobs/{job['id']}/explain/{idx[0]['key']}", headers=H)
        graph = c.get(f"/api/v1/jobs/{job['id']}/graph", headers=H)
        for resp in (one, graph):
            assert resp.status_code == 200
            assert "Zorawar" not in resp.text and "9876501234" not in resp.text
        assert {"nodes", "edges", "kept_apart"} <= set(graph.json())
        assert c.get(f"/api/v1/jobs/{job['id']}/explain/zzz", headers=H).status_code == 404


def test_explain_not_available_unless_requested(tmp_path: Path) -> None:
    with TestClient(create_app(make(tmp_path))) as c:
        r = c.post("/api/v1/jobs/from-dataset", headers=H, json={"dataset": "demo"})
        job = wait(c, r.json()["id"])
        assert c.get(f"/api/v1/jobs/{job['id']}/explain", headers=H).status_code == 404


def test_compare_is_disabled_by_default_and_works_in_demo_mode(tmp_path: Path) -> None:
    with TestClient(create_app(make(tmp_path))) as c:
        job = wait(c, c.post("/api/v1/jobs/from-dataset", headers=H, json={"dataset": "demo"}).json()["id"])
        assert c.get(f"/api/v1/jobs/{job['id']}/compare/note.txt", headers=H).status_code == 403
    with TestClient(create_app(make(tmp_path, allow_originals=True))) as c:
        job = wait(c, c.post("/api/v1/jobs/from-dataset", headers=H,
                             json={"dataset": "demo", "explain": True}).json()["id"])
        body = c.get(f"/api/v1/jobs/{job['id']}/compare/note.txt", headers=H).json()
        assert "9876501234" in body["original"] and "9876501234" not in body["sanitized"]
        assert body["explain"]["spans"]
        up = c.post("/api/v1/jobs", headers=H, files=[("files", ("u.txt", io.BytesIO(NOTE.encode()), "text/plain"))])
        uj = wait(c, up.json()["id"])
        assert c.get(f"/api/v1/jobs/{uj['id']}/compare/u.txt", headers=H).status_code == 403


def test_originals_never_allowed_in_production(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        make(tmp_path, env="production", allow_originals=True)


def test_utility_and_attack_need_answer_key(tmp_path: Path) -> None:
    with TestClient(create_app(make(tmp_path))) as c:
        r = c.post("/api/v1/jobs/from-dataset", headers=H,
                   json={"dataset": "demo", "utility": True, "attack": True})
        job = wait(c, r.json()["id"])
        assert job["verification"] == {"utility": {"available": False}, "attack": {"available": False}}
