"""Safety layer tests: logger whitelist, keyring, encrypted temp, crash hygiene."""
from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from anamika.safety import (Keyring, PrivateTemp, SafeLogger, SecretMissing,
                            UnsafeLogMessage)

REPO = Path(__file__).resolve().parents[1]


def test_logger_accepts_whitelisted_template() -> None:
    buf = io.StringIO()
    SafeLogger(stream=buf).emit("file.quarantined", sha="9f2c01ab77aa", reason="empty_file")
    assert buf.getvalue() == "anamika: file 9f2c01ab77aa quarantined reason=empty_file\n"


@pytest.mark.parametrize("fields", [
    {"sha": "Ramesh Kumar", "reason": "empty_file"},       # free text in sha slot
    {"sha": "9f2c01ab", "reason": "Ramesh Kumar"},          # spaces / capitals in id slot
    {"sha": "9f2c01ab", "reason": "+91 98765 43210"},       # phone in id slot
    {"sha": "9f2c01ab"},                                     # missing field
])
def test_logger_rejects_unsafe_values(fields: dict) -> None:
    with pytest.raises(UnsafeLogMessage):
        SafeLogger(stream=io.StringIO()).emit("file.quarantined", **fields)


def test_logger_rejects_unknown_template() -> None:
    with pytest.raises(UnsafeLogMessage):
        SafeLogger(stream=io.StringIO()).emit("debug.anything", text="x")


def test_logger_numeric_fields_reject_strings_and_bools() -> None:
    log = SafeLogger(stream=io.StringIO())
    with pytest.raises(UnsafeLogMessage):
        log.emit("run.start", files="12")
    with pytest.raises(UnsafeLogMessage):
        log.emit("run.start", files=True)


def test_keyring_subkeys_are_distinct_and_deterministic() -> None:
    a, b = Keyring.from_secret(b"practice"), Keyring.from_secret(b"practice")
    assert a == b
    keys = [a.pseudo, a.shift, a.file, a.enc, a.record]
    assert len(set(keys)) == len(keys)
    assert b"practice" not in b"".join(keys)
    assert Keyring.from_secret(b"other").pseudo != a.pseudo


def test_keyring_repr_hides_material() -> None:
    k = Keyring.from_secret(b"practice")
    assert "redacted" in repr(k) and k.pseudo.hex() not in repr(k)


def test_keyring_from_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAKSHA_SECRET", raising=False)
    with pytest.raises(SecretMissing):
        Keyring.from_env()


def test_private_temp_roundtrip_is_encrypted_and_wiped(tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", None)
    t = PrivateTemp(Keyring.from_secret(b"practice").enc)
    payload = "नाम: मोहम्मद शाहिद, +91 98765 43210".encode()
    t.put("blob1", payload)
    stored = (t.path / "blob1.bin").read_bytes()
    assert payload not in stored and t.get("blob1") == payload
    assert oct(t.path.stat().st_mode & 0o777) == "0o700"
    d = t.path
    t.wipe()
    assert not d.exists()


def test_private_temp_rejects_unsafe_names() -> None:
    t = PrivateTemp(Keyring.from_secret(b"x").enc)
    with pytest.raises(ValueError):
        t.put("../escape", b"x")
    t.wipe()


def test_crash_prints_only_exception_class(tmp_path: Path) -> None:
    code = ("from anamika.safety import install_guards, set_stage\n"
            "install_guards(); set_stage('detect')\n"
            "raise ValueError('Patient Ramesh Kumar 9876543210')\n")
    env = dict(os.environ, PYTHONPATH=str(REPO))
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env, text=True)
    assert p.returncode == 1
    assert "Ramesh" not in p.stderr + p.stdout and "9876543210" not in p.stderr
    assert "fatal valueerror during stage detect" in p.stderr
