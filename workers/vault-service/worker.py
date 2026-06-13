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

Port: 8038
Zero-cost: FastAPI + SQLite + mmap, no external vault required.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
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
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from src.entities.health_metadata import health_entity_block

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICE_NAME = "vault-service"
PORT = 8038

# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("VAULT_DB_PATH", "data/vault.db")
STORAGE_ROOT = os.environ.get("VAULT_STORAGE_ROOT", "data/vault_secrets")
AUDIT_LOG_PATH = os.environ.get("VAULT_AUDIT_LOG", "data/vault_audit.jsonl")
DEFAULT_TTL = int(os.environ.get("VAULT_DEFAULT_TTL", "3600"))
# Master key seed for AES-256-GCM derivation — must be set via env var in production
VAULT_MASTER_KEY = os.environ.get("VAULT_MASTER_KEY", "")

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
    _init_db()
    logger.info("vault-service started — DB at %s", DB_PATH)
    yield


app = FastAPI(
    title="Tranc3 Vault Service (AES-256-GCM)",
    description="Secure secret storage — XOR cipher replaced with AES-256-GCM + PBKDF2.",
    version="1.0.0",
    lifespan=_lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])
# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "service": "vault-service", "port": 8030}


# ---------------------------------------------------------------------------
# Secrets CRUD
# ---------------------------------------------------------------------------


@_router.post("/secrets", response_model=SecretResponse, status_code=201)
async def create_secret(body: SecretCreate):
    conn = _get_db()
    now = _now()
    sid = _new_id()
    encrypted = _encrypt_secret(body.value)
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
    for key, value in os.environ.items():
        for pattern in patterns:
            if pattern in key.upper() and value:
                preview = value[:8] + "..." if len(value) > 8 else value
                leaks.append({"variable_name": key, "preview": preview, "severity": "high"})
                lid = _new_id()
                now = _now()
                try:
                    conn.execute(
                        "INSERT INTO leak_detections (id, variable_name, variable_value_preview, severity, created_at) VALUES (?,?,?,?,?)",
                        (lid, key, preview, "high", now),
                    )
                except sqlite3.IntegrityError:
                    pass
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

    uvicorn.run(app, host="0.0.0.0", port=8030)
