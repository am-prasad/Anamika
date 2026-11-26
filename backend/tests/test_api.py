"""API tests: auth, ownership, limits, hardening headers and the full job lifecycle.

Jobs run through the real pipeline subprocess (inline queue) on small synthetic files.
"""
from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import hash_key
from app.main import create_app
from app.services.runner import derive_release_secret

K1, K2 = "test-key-one-0123456789", "test-key-two-9876543210"
PHONE = "9876543210"
CSV = f"UHID,Patient Name,Mobile,Diagnosis\nSNJ/26/000001,Test Person,{PHONE},Dengue fever\n"
NOTE = f"Name: Test Person\nMob: {PHONE}\nParacetamol 650 mg 1-0-1 x 5 days\n"


def make_settings(tmp_path: Path, **kw) -> Settings:
    base = dict(_env_file=None, env="test", api_keys_sha256=f"{hash_key(K1)},{hash_key(K2)}",
                master_secret="unit-test-master", data_dir=tmp_path / "data",
                rate_default="1000/minute", rate_jobs_create="1000/minute",
                rate_downloads="1000/minute", job_timeout_s=120, job_memory_mb=2048)
    base.update(kw)
    return Settings(**base)


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


def H(key: str = K1) -> dict[str, str]:
    return {"X-API-Key": key}


def upload(c: TestClient, files: dict[str, str], key: str = K1, **form) -> dict:
    parts = [("files", (name, io.BytesIO(body.encode()), "application/octet-stream"))
             for name, body in files.items()]
    r = c.post("/api/v1/jobs", files=parts, data={k: str(v) for k, v in form.items()},
               headers=H(key))
    assert r.status_code == 202, r.text
    return r.json()


def wait(c: TestClient, job_id: str, key: str = K1, timeout: float = 90) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = c.get(f"/api/v1/jobs/{job_id}", headers=H(key)).json()
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish")


# ------------------------------------------------------------------ health & hardening

def test_health_and_security_headers(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    for h in ("X-Content-Type-Options", "X-Frame-Options", "Content-Security-Policy",
              "Referrer-Policy", "X-Request-ID"):
        assert h in r.headers
    assert client.get("/readyz").json()["status"] == "ready"


def test_untrusted_host_rejected(client: TestClient) -> None:
    assert client.get("/healthz", headers={"Host": "evil.example"}).status_code == 400


def test_production_guards(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        make_settings(tmp_path, env="production", auth_disabled=True)
    with pytest.raises(ValueError):
        make_settings(tmp_path, env="production", api_keys_sha256="")
    assert make_settings(tmp_path, env="production").docs_enabled is False


# ------------------------------------------------------------------ auth & ownership

@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}, {"X-API-Key": "x" * 1000}])
def test_auth_required(client: TestClient, headers: dict) -> None:
    r = client.get("/api/v1/jobs", headers=headers)
    assert r.status_code == 401 and r.json()["error"] == "missing_or_invalid_api_key"


def test_jobs_are_private_to_their_owner(client: TestClient) -> None:
    job = upload(client, {"a.txt": NOTE})
    wait(client, job["id"])
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=H(K2)).status_code == 404
    assert client.get(f"/api/v1/jobs/{job['id']}/archive", headers=H(K2)).status_code == 404
    assert client.get("/api/v1/jobs", headers=H(K2)).json()["items"] == []


# ------------------------------------------------------------------ limits

def test_rate_limit_returns_429_with_retry_after(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path, rate_default="3/minute"))) as c:
        codes = [c.get("/api/v1/jobs", headers=H()).status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        r = c.get("/api/v1/jobs", headers=H())
        assert "Retry-After" in r.headers and r.headers["X-RateLimit-Remaining"] == "0"
        assert c.get("/api/v1/jobs", headers=H(K2)).status_code == 200  # per-principal


def test_request_size_limit(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path, max_request_mb=1))) as c:
        r = c.post("/api/v1/jobs", headers=H(),
                   files=[("files", ("big.txt", io.BytesIO(b"x" * (2 * 1024 * 1024)), "text/plain"))])
        assert r.status_code == 413


@pytest.mark.parametrize("name", ["../escape.txt", "/etc/passwd", "a/../../b.txt", "a|b.txt",
                                  "/".join(["d"] * 20) + "/f.txt"])
def test_path_traversal_rejected(client: TestClient, tmp_path: Path, name: str) -> None:
    r = client.post("/api/v1/jobs", headers=H(),
                    files=[("files", (name, io.BytesIO(b"x"), "text/plain"))])
    assert r.status_code == 400
    assert not list((tmp_path / "data" / "jobs").glob("*"))  # workspace wiped


@pytest.mark.parametrize("name", ["a\x00b.txt", "a\x1fb", "..", "", "x/" * 13 + "f"])
def test_safe_relpath_unit(name: str) -> None:
    from fastapi import HTTPException

    from app.services.storage import safe_relpath
    with pytest.raises(HTTPException):
        safe_relpath(name, 12)
    assert str(safe_relpath("reg\\a b.csv", 12)) == "reg/a b.csv"


def test_active_job_cap(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path, max_active_jobs_per_principal=0))) as c:
        r = c.post("/api/v1/jobs", headers=H(),
                   files=[("files", ("a.txt", io.BytesIO(b"x"), "text/plain"))])
        assert r.status_code == 429 and r.json()["error"] == "too_many_active_jobs"


def test_validation_errors_do_not_echo_input(client: TestClient) -> None:
    r = client.post("/api/v1/jobs/from-dataset", headers=H(),
                    json={"dataset": f"Test Person {PHONE}"})
    assert r.status_code == 422 and PHONE not in r.text and "Test Person" not in r.text


# ------------------------------------------------------------------ job lifecycle

def test_upload_job_end_to_end(client: TestClient, tmp_path: Path) -> None:
    job = upload(client, {"reg/patients.csv": CSV, "notes/n1.txt": NOTE,
                          "misc/scan.pdf": "%PDF-1.4 fake"}, verify_determinism="true")
    done = wait(client, job["id"])
    assert done["status"] == "succeeded", done
    counts = done["summary"]["counts"]
    assert counts["files_total"] == 3 and counts["files_quarantined"] == 1
    assert done["summary"]["quarantine_reasons"] == {"unsupported_format": 1}
    det = done["verification"]["determinism"]
    assert det["files_identical"] == det["files_total"] > 0

    files = client.get(f"/api/v1/jobs/{job['id']}/files", headers=H()).json()["items"]
    assert sorted(f["path"] for f in files) == ["notes/n1.txt", "reg/patients.csv"]
    r = client.get(f"/api/v1/jobs/{job['id']}/files/notes/n1.txt", headers=H())
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "X-RateLimit-Remaining" in r.headers
    assert PHONE not in r.text and "650 mg 1-0-1" in r.text
    assert client.get(f"/api/v1/jobs/{job['id']}/files/../report.json",
                      headers=H()).status_code in (400, 404)

    recs = client.get(f"/api/v1/jobs/{job['id']}/records?limit=1", headers=H()).json()
    assert recs["total"] == 2 and len(recs["items"]) == 1
    report = client.get(f"/api/v1/jobs/{job['id']}/report", headers=H()).json()
    assert report["schema"] == "raksha-report/1"

    z = client.get(f"/api/v1/jobs/{job['id']}/archive", headers=H())
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert {"report.json", "records.jsonl", "sanitized/notes/n1.txt"} <= set(names)

    ws = tmp_path / "data" / "jobs" / job["id"]
    assert not any((ws / "input").glob("**/*")), "raw input must be wiped after the run"
    secret = derive_release_secret("unit-test-master", "key_" + hash_key(K1)[:12], "default")
    for p in ws.rglob("*"):
        if p.is_file():
            assert secret.encode() not in p.read_bytes()
    assert secret not in client.get(f"/api/v1/jobs/{job['id']}", headers=H()).text

    assert client.delete(f"/api/v1/jobs/{job['id']}", headers=H()).status_code == 204
    assert not ws.exists()
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=H()).status_code == 404


def test_dataset_job_and_allow_list(tmp_path: Path) -> None:
    ds = tmp_path / "datasets" / "demo" / "input"
    ds.mkdir(parents=True)
    (ds / "n.txt").write_text(NOTE, encoding="utf-8")
    with TestClient(create_app(make_settings(tmp_path, datasets_dir=tmp_path / "datasets"))) as c:
        items = c.get("/api/v1/datasets", headers=H()).json()["items"]
        assert items == [{"name": "demo", "files": 1, "has_answer_key": False, "has_attacker": False}]
        assert c.post("/api/v1/jobs/from-dataset", headers=H(),
                      json={"dataset": "nope"}).status_code == 404
        r = c.post("/api/v1/jobs/from-dataset", headers=H(),
                   json={"dataset": "demo", "leak_scan": True})
        done = wait(c, r.json()["id"])
        assert done["status"] == "succeeded"
        assert done["verification"] == {"leak_scan": {"available": False}}
        assert (ds / "n.txt").read_text(encoding="utf-8") == NOTE  # input untouched


def test_job_fails_cleanly_without_master_secret(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path, master_secret=None))) as c:
        assert c.get("/readyz").status_code == 503
        done = wait(c, upload(c, {"a.txt": NOTE})["id"])
        assert done["status"] == "failed" and done["error"] == "service_not_configured"


def test_release_secret_is_tenant_and_release_scoped() -> None:
    a = derive_release_secret("m", "key_a", "r1")
    assert a != derive_release_secret("m", "key_b", "r1")
    assert a != derive_release_secret("m", "key_a", "r2")
    assert a != derive_release_secret("m2", "key_a", "r1")


def test_policy_endpoint(client: TestClient) -> None:
    pol = client.get("/api/v1/policy", headers=H()).json()
    assert pol["location"]["level"] in ("tehsil", "district", "state") and "dates" in pol
