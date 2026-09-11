"""
Trancendos vault-service — Self-Hosted Worker
==============================================
Secure secret management with memory-mapped injection, zeroization,
and audit integration. Wraps Dimensional.architecture.vault and
vault_security into a FastAPI microservice.

Features:
    - Load secrets from env vars, .env files, or inject at runtime
    - Memory-mapped secret injection (mmap) for zero-copy access
    - Automatic zeroization on TTL expiry or explicit revoke
    - Hash-chained audit trail for every secret access
    - Leak detection (scans environment for known secret patterns)
    - Secret rotation with versioning

Port: 8086
Zero-cost: FastAPI + SQLite + mmap, no external vault required.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from Dimensional.service_auth_fastapi import guard_internal_secret

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICE_NAME = "vault-service"
PORT = int(os.environ.get("PORT", "8038"))

# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("VAULT_DB_PATH", "data/vault.db")
STORAGE_ROOT = os.environ.get("VAULT_STORAGE_ROOT", "data/vault_secrets")

# What a vault path segment may contain. Deliberately narrow: a secret key is a
# name, and every character beyond a name is a character that has to be argued
# for. `/` is not here because it separates segments rather than living inside
# one -- namespaced keys still work, they are just checked segment by segment.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# The same alphabet as a segment, plus `%` (segments are percent-encoded before
# they are joined) and `/` as the separator. Anchored with `fullmatch`, so it
# describes the entire constructed path rather than finding a safe piece of one.
_SAFE_BUILT_PATH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._%-]*(?:/[A-Za-z0-9][A-Za-z0-9._%-]*)*")
AUDIT_LOG_PATH = os.environ.get("VAULT_AUDIT_LOG", "data/vault_audit.jsonl")
DEFAULT_TTL = int(os.environ.get("VAULT_DEFAULT_TTL", "3600"))
# Master key seed for AES-256-GCM derivation — must be set via env var in production
VAULT_MASTER_KEY = os.environ.get("VAULT_MASTER_KEY", "")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()

if ENVIRONMENT == "production" and not VAULT_MASTER_KEY:
    raise RuntimeError("vault-service requires VAULT_MASTER_KEY in production")

logger = logging.getLogger("vault-service")

# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS secrets (
            id TEXT PRIMARY KEY,
            key TEXT NOT NULL UNIQUE,
            encrypted_value TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            ttl INTEGER DEFAULT 3600,
            version INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            expires_at TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            secret_id TEXT,
            action TEXT NOT NULL,
            actor TEXT DEFAULT 'system',
            details TEXT DEFAULT '{}',
            hash TEXT NOT NULL,
            prev_hash TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS leak_detections (
            id TEXT PRIMARY KEY,
            variable_name TEXT NOT NULL,
            variable_value_preview TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'high',
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_secrets_key ON secrets(key);
        CREATE INDEX IF NOT EXISTS idx_secrets_active ON secrets(is_active);
        CREATE INDEX IF NOT EXISTS idx_audit_secret ON audit_log(secret_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# OpenBao Client — stdlib only (no extra pip deps), KV v2 API
# OpenBao is the open-source fork of HashiCorp Vault (MPL-2.0).
# When OPENBAO_ADDR is set and reachable, it acts as the primary backend;
# otherwise the AES-GCM SQLite backend below is used as a fallback.
# ---------------------------------------------------------------------------

_OPENBAO_ADDR = os.environ.get("OPENBAO_ADDR", "http://localhost:8200")
_OPENBAO_TOKEN = os.environ.get("OPENBAO_TOKEN", "")


class UnsafeVaultPath(ValueError):
    """A secret key or path that cannot be placed in a URL without changing it."""


def _vault_path(path: str) -> str:
    r"""Return `path` as URL segments that can only mean what they say.

    SEC-010. `_request` built its URL as `f"{self.addr}/v1/{path}"`, and `path`
    reaches it from `body.key` on `POST /secrets` -- a free-form string with a
    length bound and no charset. urllib does not normalise what it is given;
    measured against a local server that records the raw request line:

        key='normal-key'            -> POST /v1/secret/data/tranc3/normal-key
        key='../../../../sys/seal'  -> POST /v1/secret/data/tranc3/../../../../sys/seal
        key='x?list=true'           -> POST /v1/secret/data/tranc3/x?list=true
        key='x#frag'                -> POST /v1/secret/data/tranc3/x

    So a caller of this worker's public create endpoint chooses which OpenBao
    API path this worker calls, and the call carries `X-Vault-Token`. `..`
    walks out of `secret/data/` into `sys/` and `auth/`; `?` appends a query
    the caller wrote; `#` truncates the path. The vault holding every secret on
    the platform is the worst possible place for the caller to pick the
    endpoint, which is why CodeQL scores it 9.1.

    The guard is structural rather than a denylist: every segment is checked,
    and anything that is not a plain name is refused before percent-encoding
    the rest. Encoding alone would not be enough -- `.` is an unreserved
    character, so `%2e%2e` and `..` mean the same thing to a server that
    resolves dot-segments, and quoting would happily preserve the traversal.

    Raises UnsafeVaultPath rather than silently repairing the path. A key the
    caller cannot have meant is a refusal, not something to guess at: sanitising
    `../../sys/seal` into `sys/seal` would still leave the caller choosing the
    endpoint.
    """
    if not path:
        raise UnsafeVaultPath("empty vault path")
    segments = path.strip("/").split("/")
    for segment in segments:
        if not segment:
            raise UnsafeVaultPath(f"empty path segment in {path!r}")
        if segment in (".", ".."):
            raise UnsafeVaultPath(f"traversal segment {segment!r} in {path!r}")
        if not _SAFE_SEGMENT.match(segment):
            raise UnsafeVaultPath(f"unsafe characters in path segment {segment!r}")
    built = "/".join(urllib.parse.quote(seg, safe="") for seg in segments)
    # A final assertion on the WHOLE constructed path, not just its parts.
    #
    # Redundant by construction today — every segment was checked above and
    # then percent-encoded, so `built` cannot contain anything this refuses.
    # Kept for two reasons, one of them about this codebase and one about the
    # scanner reading it.
    #
    # About the code: the per-segment loop and the join are separated by an
    # encoding step, and "each part is safe" plus "the parts are combined" is
    # not the same claim as "the result is safe". Stating the post-condition
    # where it is produced means a future edit to either half has to keep it
    # true rather than merely look like it does.
    #
    # About the scanner: CodeQL still reports `py/partial-ssrf` 9.1 here after
    # SEC-010. Its flow runs `body.key` -> f-string -> `path` -> `_vault_path()`
    # -> `safe_path` -> `url`, tracing straight THROUGH the validation, because
    # a helper that raises is not something it models as a sanitiser. The
    # vulnerability is fixed — nine calibrated assertions say so, and the
    # boundary answers 422 — but the ALERT is not cleared, and those are
    # different facts. Recorded as such in SECURITY_ALERT_REGISTER.md rather
    # than claimed as a clearance.
    if not _SAFE_BUILT_PATH.fullmatch(built):
        raise UnsafeVaultPath(f"constructed vault path is not a plain path: {built!r}")
    return built


class OpenBaoClient:
    """Minimal OpenBao KV v2 client using stdlib urllib — zero external deps."""

    def __init__(self, addr: str = _OPENBAO_ADDR, token: str = _OPENBAO_TOKEN) -> None:
        self.addr = addr.rstrip("/")
        self.token = token
        self._available: Optional[bool] = None  # None = not yet checked

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> Optional[dict]:
        # Every path through this client is checked here, not at each call site.
        # `put_secret` and `get_secret` are the callers today; the next one will
        # not have to remember, which is the only version of this guard that
        # stays true. Refusing returns None like every other failure mode, so a
        # rejected mirror degrades to the SQLite backend rather than 500ing --
        # but `SecretCreate` refuses the same key at the boundary with a 422, so
        # nothing reaches here silently in the case that matters.
        try:
            safe_path = _vault_path(path)
        except UnsafeVaultPath as exc:
            logger.warning("vault-service refused an unsafe OpenBao path: %s", exc)
            return None
        url = f"{self.addr}/v1/{safe_path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "X-Vault-Token": self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=2) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            logger.debug("OpenBao HTTP %s for %s", exc.code, url)
            return None
        except Exception as exc:
            logger.debug("OpenBao unreachable at %s: %s", url, exc)
            return None

    def is_available(self) -> bool:
        """Check once whether OpenBao is reachable; cache the result."""
        if self._available is not None:
            return self._available
        result = self._request("GET", "sys/health")
        self._available = result is not None
        if self._available:
            logger.info("vault-service: OpenBao backend active at %s", self.addr)
        else:
            logger.info("vault-service: OpenBao not reachable — using AES-GCM SQLite backend")
        return self._available

    def put_secret(self, path: str, data: dict) -> bool:
        """Write a secret to KV v2 at secret/data/{path}. Returns True on success."""
        result = self._request("POST", f"secret/data/{path}", {"data": data})
        return result is not None

    def get_secret(self, path: str) -> Optional[dict]:
        """Read a secret from KV v2 at secret/data/{path}. Returns data dict or None."""
        result = self._request("GET", f"secret/data/{path}")
        if result and "data" in result and "data" in result["data"]:
            return result["data"]["data"]
        return None


# Module-level OpenBao client — probed at startup
_openbao: Optional[OpenBaoClient] = None
_openbao_active: bool = False


def _init_openbao() -> None:
    """Initialise the OpenBao client if OPENBAO_ADDR is configured."""
    global _openbao, _openbao_active
    if _OPENBAO_ADDR and _OPENBAO_TOKEN:
        _openbao = OpenBaoClient()
        _openbao_active = _openbao.is_available()
    else:
        _openbao_active = False


# ---------------------------------------------------------------------------
# AES-256-GCM Encryption (cryptographically secure, zero external cost)
# Uses the same pattern as workers/infinity-void/worker.py (The Void).
# ---------------------------------------------------------------------------


def _get_master_key() -> str:
    """Return the master key seed, generating a runtime-only fallback if unset."""
    key = VAULT_MASTER_KEY
    if not key:
        # Warn loudly — this fallback is only acceptable in development.
        # In production, VAULT_MASTER_KEY must be set via environment.
        logger.warning(
            "vault-service: VAULT_MASTER_KEY not set — using ephemeral key. "
            "Secrets will NOT survive restarts. Set VAULT_MASTER_KEY in production."
        )
        # Use a stable-per-process key so secrets survive within a single run
        import threading

        with threading.Lock():
            if not hasattr(_get_master_key, "_ephemeral"):
                _get_master_key._ephemeral = os.urandom(32).hex()
        return _get_master_key._ephemeral
    return key


def _derive_key(seed: str, salt: bytes) -> bytes:
    """PBKDF2-SHA256 key derivation — 100k iterations, 256-bit output."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return kdf.derive(seed.encode())


def _encrypt_secret(plaintext: str) -> str:
    """
    AES-256-GCM encrypt plaintext.
    Returns a hex string: salt(32) + iv(12) + tag(16) + ciphertext.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(32)
    iv = os.urandom(12)
    key = _derive_key(_get_master_key(), salt)
    aesgcm = AESGCM(key)
    # AESGCM.encrypt returns ciphertext + 16-byte tag concatenated
    ct_with_tag = aesgcm.encrypt(iv, plaintext.encode(), None)
    return (salt + iv + ct_with_tag).hex()


def _decrypt_secret(ciphertext_hex: str) -> str:
    """
    AES-256-GCM decrypt.
    Expects hex string: salt(32) + iv(12) + tag(16) + ciphertext.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = bytes.fromhex(ciphertext_hex)
    if len(raw) < 60:  # 32 + 12 + 16 minimum
        raise ValueError("vault-service: ciphertext too short — corrupted or legacy XOR data")
    salt = raw[:32]
    iv = raw[32:44]
    ct_with_tag = raw[44:]
    key = _derive_key(_get_master_key(), salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ct_with_tag, None).decode()


# Backwards-compat shim: attempt XOR-decrypt of legacy secrets stored before this fix.
# Remove this shim once all secrets have been re-encrypted (rotate via PUT /secrets/{id}).
def _legacy_xor_decrypt(
    ciphertext_hex: str,
    xor_key: str = "Tranc3Vault2024!ZeroCostCrypto",
) -> str:
    """Decrypt a secret encrypted by the old (insecure) XOR cipher."""
    key_bytes = xor_key.encode()
    cipher_bytes = bytes.fromhex(ciphertext_hex)
    decrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(cipher_bytes))
    return decrypted.decode(errors="replace")


# ---------------------------------------------------------------------------
# Audit Helpers
# ---------------------------------------------------------------------------

_last_audit_hash = "0" * 64  # Genesis hash


def _get_last_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT hash FROM audit_log ORDER BY created_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    return row["hash"] if row else "0" * 64


def _append_audit(
    conn: sqlite3.Connection,
    secret_id: Optional[str],
    action: str,
    actor: str = "system",
    details: dict = None,
) -> str:
    now = _now()
    prev_hash = _get_last_hash(conn)
    payload = f"{prev_hash}:{secret_id or ''}:{action}:{actor}:{now}"
    entry_hash = hashlib.sha256(payload.encode()).hexdigest()
    aid = _new_id()
    conn.execute(
        "INSERT INTO audit_log (id, secret_id, action, actor, details, hash, prev_hash, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (aid, secret_id, action, actor, json.dumps(details or {}), entry_hash, prev_hash, now),
    )
    return aid


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SecretCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)

    @field_validator("key")
    @classmethod
    def _key_is_a_name(cls, value: str) -> str:
        """Refuse a key that could not be a vault path (SEC-010).

        The same function the OpenBao client uses, so the boundary and the URL
        cannot disagree about what is safe. Here it produces a loud 422 the
        caller can read; there it is the structural guarantee that no future
        call site can reintroduce the hole.
        """
        try:
            canonical = _vault_path(value)
        except UnsafeVaultPath as exc:
            raise ValueError(str(exc)) from None
        # Stricter than the path builder by one rule: the key must ALREADY be
        # what `_vault_path` would make of it. `_vault_path` strips surrounding
        # slashes because a caller writing "/sys/health" means the same path;
        # a secret KEY is different -- "/db-password" and "db-password" would be
        # two SQLite rows mirroring to one OpenBao path. Comparing against the
        # canonical form catches that without restating the rule, so the two
        # cannot drift apart.
        if canonical != value:
            raise ValueError(f"secret key must be canonical: {value!r} normalises to {canonical!r}")
        return value

    value: str = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)
    ttl: int = DEFAULT_TTL


class SecretResponse(BaseModel):
    id: str
    key: str
    tags: List[str]
    ttl: int
    version: int
    is_active: int
    created_at: str
    updated_at: str
    expires_at: Optional[str]


class SecretUpdate(BaseModel):
    value: Optional[str] = None
    tags: Optional[List[str]] = None
    ttl: Optional[int] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    import uuid

    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # OpenTelemetry instrumentation is best-effort. This worker's Docker build
    # context is its own directory, so `src/` is absent from the image and the
    # import raises inside the container. Unguarded, that ImportError escapes
    # lifespan and the worker never starts — telemetry taking the service down.
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.vault-service")
    except Exception:  # noqa: BLE001 — telemetry must never block startup
        pass
    _init_db()
    _init_openbao()
    logger.info("vault-service started — DB at %s", DB_PATH)
    yield


app = FastAPI(
    title="Tranc3 Vault Service (AES-256-GCM)",
    description="Secure secret storage — XOR cipher replaced with AES-256-GCM + PBKDF2.",
    version="1.0.0",
    lifespan=_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
        ).split(",")
        if o.strip() and o.strip() != "*"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


_internal_secret_raw = os.environ.get("INTERNAL_SECRET")
if (
    not _internal_secret_raw
    or not _internal_secret_raw.strip()
    or _internal_secret_raw.strip() == "dev-secret"
):
    raise RuntimeError(
        "INTERNAL_SECRET is not set (or still the default). "
        "This worker cannot start without a strong unique internal secret. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
_INTERNAL_SECRET: str = _internal_secret_raw.strip()


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    guard_internal_secret(
        x_internal_secret,
        _INTERNAL_SECRET,
        mismatch_status=401,
        detail="Invalid or missing X-Internal-Secret header",
    )


_router = APIRouter(dependencies=[Depends(require_internal_auth)])
# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "service": "vault-service", "port": 8030}


@app.get("/vault/backend")
async def vault_backend():
    """Return which storage backend is currently active."""
    if _openbao_active and _openbao is not None:
        return {
            "backend": "openbao",
            "addr": _openbao.addr,
            "description": "OpenBao KV v2 (primary — AES-GCM SQLite is standby fallback)",
        }
    return {
        "backend": "aes-gcm-sqlite",
        "db_path": DB_PATH,
        "description": "AES-256-GCM encrypted SQLite (OpenBao not configured or unreachable)",
    }


# ---------------------------------------------------------------------------
# Secrets CRUD
# ---------------------------------------------------------------------------


@_router.post("/secrets", response_model=SecretResponse, status_code=201)
async def create_secret(body: SecretCreate):
    conn = _get_db()
    now = _now()
    sid = _new_id()
    encrypted = _encrypt_secret(body.value)
    # Mirror to OpenBao when available (primary backend)
    if _openbao_active and _openbao is not None:
        _openbao.put_secret(
            f"tranc3/{body.key}", {"value": body.value, "sid": sid, "ttl": body.ttl}
        )
    try:
        conn.execute(
            "INSERT INTO secrets (id, key, encrypted_value, tags, ttl, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (sid, body.key, encrypted, json.dumps(body.tags), body.ttl, now, now),
        )
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, f"Secret key '{body.key}' already exists") from None

    _append_audit(conn, sid, "secret.create", details={"key": body.key, "ttl": body.ttl})
    conn.commit()
    conn.close()

    return SecretResponse(
        id=sid,
        key=body.key,
        tags=body.tags,
        ttl=body.ttl,
        version=1,
        is_active=1,
        created_at=now,
        updated_at=now,
        expires_at=None,
    )


@_router.get("/secrets", response_model=List[SecretResponse])
async def list_secrets(
    active_only: bool = True, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
):
    conn = _get_db()
    q = "SELECT * FROM secrets WHERE 1=1"
    params: list = []
    if active_only:
        q += " AND is_active=1"
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        SecretResponse(
            id=r["id"],
            key=r["key"],
            tags=json.loads(r["tags"]),
            ttl=r["ttl"],
            version=r["version"],
            is_active=r["is_active"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            expires_at=r["expires_at"],
        )
        for r in rows
    ]


@_router.get("/secrets/{secret_id}", response_model=SecretResponse)
async def get_secret(secret_id: str):
    conn = _get_db()
    row = conn.execute("SELECT * FROM secrets WHERE id=?", (secret_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Secret not found") from None
    _append_audit(conn, secret_id, "secret.read")
    conn.commit()
    conn.close()
    return SecretResponse(
        id=row["id"],
        key=row["key"],
        tags=json.loads(row["tags"]),
        ttl=row["ttl"],
        version=row["version"],
        is_active=row["is_active"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )


@_router.put("/secrets/{secret_id}", response_model=SecretResponse)
async def update_secret(secret_id: str, body: SecretUpdate):
    conn = _get_db()
    row = conn.execute("SELECT * FROM secrets WHERE id=?", (secret_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Secret not found") from None

    now = _now()
    updates = {"updated_at": now, "version": row["version"] + 1}
    if body.value is not None:
        updates["encrypted_value"] = _encrypt_secret(body.value)
    if body.tags is not None:
        updates["tags"] = json.dumps(body.tags)
    if body.ttl is not None:
        updates["ttl"] = body.ttl

    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE secrets SET {set_clause} WHERE id=?", (*updates.values(), secret_id))
    _append_audit(
        conn, secret_id, "secret.update", details={"fields_updated": list(updates.keys())}
    )
    conn.commit()

    row = conn.execute("SELECT * FROM secrets WHERE id=?", (secret_id,)).fetchone()
    conn.close()
    return SecretResponse(
        id=row["id"],
        key=row["key"],
        tags=json.loads(row["tags"]),
        ttl=row["ttl"],
        version=row["version"],
        is_active=row["is_active"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
    )


@_router.put("/secrets/{secret_id}/revoke")
async def revoke_secret(secret_id: str):
    conn = _get_db()
    row = conn.execute("SELECT * FROM secrets WHERE id=?", (secret_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Secret not found") from None
    now = _now()
    conn.execute("UPDATE secrets SET is_active=0, updated_at=? WHERE id=?", (now, secret_id))
    _append_audit(conn, secret_id, "secret.revoke")
    conn.commit()
    conn.close()
    return {"id": secret_id, "is_active": 0, "updated_at": now}


@_router.put("/secrets/{secret_id}/zeroize")
async def zeroize_secret(secret_id: str):
    conn = _get_db()
    row = conn.execute("SELECT * FROM secrets WHERE id=?", (secret_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Secret not found") from None
    now = _now()
    conn.execute(
        "UPDATE secrets SET encrypted_value=?, is_active=0, updated_at=? WHERE id=?",
        (_encrypt_secret("0000"), now, secret_id),
    )
    _append_audit(conn, secret_id, "secret.zeroize")
    conn.commit()
    conn.close()
    return {"id": secret_id, "zeroized": True, "updated_at": now}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@_router.get("/audit")
async def get_audit_log(
    secret_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    conn = _get_db()
    q = "SELECT * FROM audit_log WHERE 1=1"
    params: list = []
    if secret_id:
        q += " AND secret_id=?"
        params.append(secret_id)
    if action:
        q += " AND action=?"
        params.append(action)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@_router.get("/audit/verify")
async def verify_audit_chain():
    conn = _get_db()
    rows = conn.execute(
        "SELECT id, hash, prev_hash FROM audit_log ORDER BY created_at ASC, rowid ASC"
    ).fetchall()
    conn.close()
    if not rows:
        return {"chain_valid": True, "entry_count": 0}
    valid = True
    for i in range(1, len(rows)):
        if rows[i]["prev_hash"] != rows[i - 1]["hash"]:
            valid = False
            break
    return {"chain_valid": valid, "entry_count": len(rows)}


# ---------------------------------------------------------------------------
# Leak Detection
# ---------------------------------------------------------------------------


@_router.get("/scan/leaks")
async def scan_for_leaks():
    conn = _get_db()
    patterns = ["SECRET", "PASSWORD", "API_KEY", "TOKEN", "PRIVATE_KEY"]
    leaks = []
    insert_data = []
    for key, value in os.environ.items():
        for pattern in patterns:
            if pattern in key.upper() and value:
                preview = value[:8] + "..." if len(value) > 8 else value
                leaks.append({"variable_name": key, "preview": preview, "severity": "high"})
                lid = _new_id()
                now = _now()
                insert_data.append((lid, key, preview, "high", now))
    if insert_data:
        conn.executemany(
            "INSERT OR IGNORE INTO leak_detections (id, variable_name, variable_value_preview, severity, created_at) VALUES (?,?,?,?,?)",
            insert_data,
        )
    conn.commit()
    conn.close()
    return {"leaks_found": len(leaks), "leaks": leaks}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@_router.get("/stats")
async def get_stats():
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM secrets").fetchone()["c"]
    active = conn.execute("SELECT COUNT(*) as c FROM secrets WHERE is_active=1").fetchone()["c"]
    revoked = conn.execute("SELECT COUNT(*) as c FROM secrets WHERE is_active=0").fetchone()["c"]
    audit = conn.execute("SELECT COUNT(*) as c FROM audit_log").fetchone()["c"]
    leaks = conn.execute(
        "SELECT COUNT(*) as c FROM leak_detections WHERE status='open'"
    ).fetchone()["c"]
    conn.close()
    return {
        "total_secrets": total,
        "active_secrets": active,
        "revoked_secrets": revoked,
        "audit_entries": audit,
        "open_leaks": leaks,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


_connected_ws: list[WebSocket] = []


@app.websocket("/ws")
async def _ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _connected_ws.append(ws)
    try:
        # Push initial state
        stats = await _get_stats_async()
        await ws.send_text(json.dumps({"type": "initial_state", "data": stats}))
        # Keep alive — listen for client messages
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {"type": "ping"}
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            elif msg.get("type") == "get_stats":
                await ws.send_text(json.dumps({"type": "stats", "data": _get_stats()}))
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _connected_ws:
            _connected_ws.remove(ws)


async def _broadcast_event(event_type: str, data: dict) -> None:
    msg = json.dumps({"type": event_type, "data": data})
    stale = []
    for ws in _connected_ws:
        try:
            await ws.send_text(msg)
        except Exception:
            stale.append(ws)
    for ws in stale:
        _connected_ws.remove(ws)


@_router.get("/events")
async def _sse_events():
    async def _generator():
        while True:
            stats = await _get_stats_async()
            yield {"event": "stats", "data": json.dumps(stats)}
            await asyncio.sleep(5)

    return EventSourceResponse(_generator())


@_router.get("/dashboard/summary")
async def _dashboard_summary():
    """Aggregated summary optimized for dashboard consumption."""
    stats = await _get_stats_async()
    return {
        "service": stats.get("service", SERVICE_NAME),
        "port": stats.get("port", PORT),
        "status": "healthy",
        "summary": stats,
        "real_time": {
            "websocket": f"ws://localhost:{PORT}/ws",
            "sse": f"http://localhost:{PORT}/events",
        },
    }


async def _get_stats_async() -> dict:
    """Async version for use in async contexts."""
    try:
        result = await get_stats()
        if isinstance(result, dict):
            result["service"] = SERVICE_NAME
            result["port"] = PORT
            return result
    except Exception:
        pass
    return {"service": SERVICE_NAME, "port": PORT}


def _get_stats() -> dict:
    """Return basic service stats for real-time endpoints (sync fallback)."""
    return {"service": SERVICE_NAME, "port": PORT}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # nosec B104 — containerised service
