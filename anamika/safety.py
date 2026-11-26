"""Safety layer: the only place where secrets, logging, crashes and temp storage are handled.

Everything else in Anamika is untrusted with respect to side channels. This module
guarantees that:

* **Logging is PII-free by construction.** :class:`SafeLogger` only emits messages from a
  fixed whitelist of templates. Template fields accept only integers, floats, booleans and
  short identifiers from a closed vocabulary (stage names, reasons, format names) or
  SHA-256 prefixes. Free text from records can never reach stderr.
* **Crashes are silent about content.** :func:`install_guards` replaces ``sys.excepthook``
  and ``threading.excepthook`` so an uncaught exception prints only its class name and
  the current stage, never a traceback with values. Python warnings are suppressed for
  the same reason.
* **The secret never leaves memory.** :class:`Keyring` reads ``RAKSHA_SECRET`` once and
  derives independent sub-keys with HKDF-SHA256 (``pseudo``, ``shift``, ``file``,
  ``enc``). The raw secret is not kept as an attribute, is never printed, hashed into an
  output, or written to disk.
* **Intermediate data is encrypted at rest.** :class:`PrivateTemp` lazily creates one
  ``0700`` directory, encrypts every spilled blob with AES-256-GCM under the ``enc``
  sub-key, and wipes the directory at exit (normal exit, error, or signal).
"""
from __future__ import annotations

import atexit
import hashlib
import hmac
import os
import re
import shutil
import signal
import sys
import tempfile
import threading
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SECRET_ENV: Final = "RAKSHA_SECRET"
_HKDF_SALT: Final = b"anamika/hkdf-salt/v1"
SUBKEYS: Final = ("pseudo", "shift", "file", "enc", "record")

# --------------------------------------------------------------------------- stage tracking

_STAGE = threading.local()


def set_stage(name: str) -> None:
    """Record the pipeline stage currently running (used by crash reports only)."""
    _STAGE.name = name if _IDENT.fullmatch(name or "") else "unknown"


def current_stage() -> str:
    """Return the current pipeline stage name (``startup`` before any stage is set)."""
    return getattr(_STAGE, "name", "startup")


# --------------------------------------------------------------------------- PII-free logger

_IDENT = re.compile(r"[a-z][a-z0-9_.\-]{0,47}")
_SHA_PREFIX = re.compile(r"[0-9a-f]{8,16}")

# Every message Anamika may ever print. Placeholders are typed:
#   {n:...}  int / float      {id:...}  identifier from _IDENT      {sha:...} hex prefix
TEMPLATES: Final[dict[str, str]] = {
    "run.start": "anamika: run started (files={n:files})",
    "run.done": (
        "anamika: done files={n:files} sanitized={n:sanitized} quarantined={n:quarantined} "
        "records={n:records} linked={n:linked} identifiers={n:identifiers} seconds={n:seconds}"
    ),
    "file.quarantined": "anamika: file {sha:sha} quarantined reason={id:reason}",
    "stage.enter": "anamika: stage {id:stage}",
    "secret.missing": "anamika: RAKSHA_SECRET is not set; refusing to run",
    "args.invalid": "anamika: invalid arguments ({id:problem})",
    "fatal": "anamika: fatal {id:exc} during stage {id:stage}",
    "accounting.mismatch": "anamika: accounting mismatch inputs={n:inputs} accounted={n:accounted}",
}
_FIELD = re.compile(r"\{(n|id|sha):([a-z_]+)\}")


class UnsafeLogMessage(ValueError):
    """Raised when code tries to log a template or value that is not whitelisted."""


def _render(template_id: str, fields: dict[str, object]) -> str:
    template = TEMPLATES.get(template_id)
    if template is None:
        raise UnsafeLogMessage("unknown template")

    def sub(m: re.Match[str]) -> str:
        kind, key = m.group(1), m.group(2)
        if key not in fields:
            raise UnsafeLogMessage("missing field")
        value = fields[key]
        if kind == "n":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise UnsafeLogMessage("numeric field expected")
            return f"{value:.2f}" if isinstance(value, float) else str(value)
        if kind == "id":
            if not isinstance(value, str) or not _IDENT.fullmatch(value):
                raise UnsafeLogMessage("identifier field expected")
            return value
        if not isinstance(value, str) or not _SHA_PREFIX.fullmatch(value):
            raise UnsafeLogMessage("sha prefix expected")
        return value

    return _FIELD.sub(sub, template)


class SafeLogger:
    """Writes whitelisted, typed messages to stderr. Nothing else can be logged.

    Example::

        log = SafeLogger()
        log.emit("file.quarantined", sha="9f2c01ab", reason="unsupported_format")
    """

    def __init__(self, stream: object | None = None, quiet: bool = False) -> None:
        self._stream = stream
        self.quiet = quiet

    def emit(self, template_id: str, **fields: object) -> None:
        """Render ``template_id`` with type-checked ``fields`` and write it to stderr."""
        line = _render(template_id, fields)
        if self.quiet:
            return
        stream = self._stream or sys.stderr
        stream.write(line + "\n")  # type: ignore[attr-defined]
        stream.flush()  # type: ignore[attr-defined]


LOG = SafeLogger()


# --------------------------------------------------------------------------- crash guards


def _safe_exit_message(exc_type: type[BaseException]) -> str:
    name = exc_type.__name__.lower()
    return name if _IDENT.fullmatch(name) else "exception"


def _excepthook(exc_type: type[BaseException], exc: BaseException, tb: object) -> None:
    try:
        LOG.emit("fatal", exc=_safe_exit_message(exc_type), stage=current_stage())
    finally:
        PrivateTemp.wipe_all()
        os._exit(1)


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    _excepthook(args.exc_type, args.exc_value or args.exc_type(), args.exc_traceback)


def install_guards() -> None:
    """Install PII-safe crash handlers, silence warnings and register temp wiping."""
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    warnings.simplefilter("ignore")
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 4000))
    atexit.register(PrivateTemp.wipe_all)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, OSError):  # not in main thread / unsupported platform
            pass


def _signal_handler(signum: int, _frame: object) -> None:
    PrivateTemp.wipe_all()
    os._exit(128 + signum)


# --------------------------------------------------------------------------- secret & keys


class SecretMissing(RuntimeError):
    """``RAKSHA_SECRET`` is absent or empty."""


@dataclass(frozen=True)
class Keyring:
    """Independent HKDF-SHA256 sub-keys derived from ``RAKSHA_SECRET``.

    The raw secret is consumed in :meth:`from_env` and not stored. Each purpose gets its
    own 32-byte key, so a leak of one derived value (e.g. a pseudonym) gives no leverage
    on another (e.g. date shifts).
    """

    pseudo: bytes
    shift: bytes
    file: bytes
    enc: bytes
    record: bytes

    def __repr__(self) -> str:  # never show key material, even in debuggers
        return "Keyring(<redacted>)"

    __str__ = __repr__

    @classmethod
    def from_secret(cls, secret: bytes) -> "Keyring":
        """Derive the keyring from raw secret bytes (used by tests and :meth:`from_env`)."""
        if not secret:
            raise SecretMissing("empty secret")
        keys = {}
        for name in SUBKEYS:
            hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=_HKDF_SALT,
                        info=b"anamika/" + name.encode())
            keys[name] = hkdf.derive(secret)
        return cls(**keys)

    @classmethod
    def from_env(cls) -> "Keyring":
        """Read ``RAKSHA_SECRET`` from the environment once and derive sub-keys."""
        raw = os.environ.get(SECRET_ENV, "")
        if not raw:
            raise SecretMissing("RAKSHA_SECRET not set")
        return cls.from_secret(raw.encode("utf-8"))

    def mac(self, purpose: str, message: str | bytes) -> bytes:
        """HMAC-SHA256 of ``message`` under the sub-key named ``purpose``."""
        key = getattr(self, purpose)
        data = message.encode("utf-8") if isinstance(message, str) else message
        return hmac.new(key, data, hashlib.sha256).digest()


# --------------------------------------------------------------------------- encrypted temp


class PrivateTemp:
    """A private, encrypted scratch area that is wiped at exit.

    The directory is created lazily (so runs that never spill leave no trace), with mode
    ``0700``. Blobs are AES-256-GCM encrypted with a random 96-bit nonce and the blob name
    bound as associated data. Prefer keeping intermediates in memory; use this only for
    data that does not fit.
    """

    _instances: list["PrivateTemp"] = []
    _lock = threading.Lock()

    def __init__(self, key: bytes) -> None:
        self._aead = AESGCM(key)
        self._dir: Path | None = None
        with PrivateTemp._lock:
            PrivateTemp._instances.append(self)

    @property
    def path(self) -> Path:
        """The private directory, created on first use."""
        if self._dir is None:
            old = os.umask(0o077)
            try:
                self._dir = Path(tempfile.mkdtemp(prefix="anamika-"))
            finally:
                os.umask(old)
            os.chmod(self._dir, 0o700)
        return self._dir

    def _blob(self, name: str) -> Path:
        if not _IDENT.fullmatch(name):
            raise ValueError("blob names must be plain identifiers")
        return self.path / (name + ".bin")

    def put(self, name: str, data: bytes) -> None:
        """Encrypt ``data`` and store it under ``name``."""
        nonce = os.urandom(12)
        sealed = self._aead.encrypt(nonce, data, name.encode())
        target = self._blob(name)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(nonce + sealed)

    def get(self, name: str) -> bytes:
        """Decrypt and return the blob stored under ``name``."""
        raw = self._blob(name).read_bytes()
        return self._aead.decrypt(raw[:12], raw[12:], name.encode())

    def wipe(self) -> None:
        """Overwrite and delete every blob, then remove the directory."""
        if self._dir is None:
            return
        for p in self._dir.glob("*"):
            try:
                size = p.stat().st_size
                with open(p, "r+b") as fh:
                    fh.write(b"\0" * size)
            except OSError:
                pass
        shutil.rmtree(self._dir, ignore_errors=True)
        self._dir = None

    @classmethod
    def wipe_all(cls) -> None:
        """Wipe every live :class:`PrivateTemp` (registered with ``atexit``)."""
        with cls._lock:
            for inst in cls._instances:
                inst.wipe()


# --------------------------------------------------------------------------- misc helpers


def sha_prefix(digest_hex: str, n: int = 12) -> str:
    """Return the first ``n`` hex characters of a SHA-256 digest (safe to log)."""
    return digest_hex[:n]


def guarded(stage: str) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Decorator: mark ``stage`` as current while the wrapped function runs."""

    def deco(fn: Callable[..., object]) -> Callable[..., object]:
        def wrapper(*a: object, **kw: object) -> object:
            prev = current_stage()
            set_stage(stage)
            try:
                return fn(*a, **kw)
            finally:
                set_stage(prev)

        wrapper.__name__ = getattr(fn, "__name__", "wrapped")
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return deco
