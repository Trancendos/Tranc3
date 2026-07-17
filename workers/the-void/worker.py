"""
Trancendos the-void — AES-GCM Secrets Vault Worker
===================================================
Zero-knowledge encrypted secrets store. Plaintext never persisted;
master key derived via PBKDF2-HMAC-SHA256 (100k iterations).

Port: 8038  Entity: The Void  Lead AI: Prometheus
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = int(os.getenv("PORT") or "8038")
WORKER_NAME = "the-void"
DB_PATH = Path(__file__).parent / "data" / "vault.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

MASTER_KEY_ENV = os.getenv("VAULT_MASTER_KEY", "dev-master-key-change-in-prod")
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

_start_time = time.time()
_req_count = 0
_err_count = 0


# ---------------------------------------------------------------------------
# Crypto helpers
# ---------------------------------------------------------------------------
# `cryptography` is a hard dependency (requirements.txt), not optional here —
# a prior version of this module silently fell back to XOR "encryption" if
# the import failed, which would have made this vault's at-rest protection
# trivially breakable in any environment missing the package, with no error
# raised to reveal it. AESGCM is imported unconditionally at module load so a
# missing dependency fails loudly (ImportError on startup) instead of quietly
# downgrading every secret this worker stores.


def _derive_key(master: str, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256, 100k iterations → 32-byte key."""
    return hashlib.pbkdf2_hmac("sha256", master.encode(), salt, 100_000, dklen=32)


def _encrypt(plaintext: str, master: str) -> tuple[bytes, bytes, bytes]:
    """Return (ciphertext, iv, salt). Uses os.urandom for IV+salt."""
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = _derive_key(master, salt)
    ct = AESGCM(key).encrypt(iv, plaintext.encode(), None)
    return ct, iv, salt


def _decrypt(ct: bytes, iv: bytes, salt: bytes, master: str) -> str:
    """Decrypt and return plaintext."""
    key = _derive_key(master, salt)
    try:
        return AESGCM(key).decrypt(iv, ct, None).decode()
    except InvalidTag:
        # Records written by the old cryptography-unavailable fallback are
        # XOR'd with a b"\xde\xad" sentinel, not AES-GCM — feeding them to
        # AESGCM.decrypt() always raised InvalidTag here, silently making any
        # secret stored before this fix permanently unretrievable. Detect
        # that legacy format by the sentinel and decode it the same way the
        # old fallback did, so pre-existing records stay readable. New writes
        # are always AES-GCM (see _encrypt above) — this is a read-only
        # compatibility path, not a re-introduction of XOR for new secrets.
        if ct[-2:] != b"\xde\xad":
            raise
        raw = ct[:-2]
        return bytes(b ^ key[i % 32] for i, b in enumerate(raw)).decode()


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS secrets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT UNIQUE NOT NULL,
                encrypted_val BLOB NOT NULL,
                iv            BLOB NOT NULL,
                salt          BLOB NOT NULL,
                created_at    REAL NOT NULL,
                accessed_at   REAL,
                access_count  INTEGER DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_secrets_name ON secrets(name)")
        conn.commit()


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield
    logger.info("%s shutdown", WORKER_NAME)


app = FastAPI(title="The Void — Secrets Vault", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_router = APIRouter()


def _check_auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SecretIn(BaseModel):
    name: str
    value: str


class RetrieveIn(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@_router.get("/health")
async def health():
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM secrets").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "The Void", "lead_ai": "Prometheus"},
        "secret_count": count,
    }


@_router.get("/metrics")
async def metrics():
    uptime = time.time() - _start_time
    return (
        f"# HELP requests_total Total requests\n"
        f"# TYPE requests_total counter\n"
        f"requests_total {_req_count}\n"
        f"# HELP errors_total Total errors\n"
        f"# TYPE errors_total counter\n"
        f"errors_total {_err_count}\n"
        f"# HELP uptime_seconds Uptime\n"
        f"# TYPE uptime_seconds gauge\n"
        f"uptime_seconds {uptime:.2f}\n"
    )


@_router.get("/vault/status")
async def vault_status():
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM secrets").fetchone()[0]
        oldest = conn.execute("SELECT MIN(created_at) FROM secrets").fetchone()[0]
    return {
        "sealed": False,
        "secret_count": count,
        "oldest_secret_ts": oldest,
        "service": WORKER_NAME,
        "crypto": "AES-256-GCM via PBKDF2-HMAC-SHA256",
    }


@_router.post("/secrets", status_code=201, dependencies=[])
async def store_secret(body: SecretIn, x_internal_secret: str = Header(default="")):
    _check_auth(x_internal_secret)
    ct, iv, salt = _encrypt(body.value, MASTER_KEY_ENV)
    now = time.time()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO secrets (name, encrypted_val, iv, salt, created_at) VALUES (?,?,?,?,?)",
                (body.name, ct, iv, salt, now),
            )
            conn.commit()
            return {"id": cur.lastrowid, "name": body.name, "created_at": now}
        except sqlite3.IntegrityError:
            # Update existing
            conn.execute(
                "UPDATE secrets SET encrypted_val=?, iv=?, salt=?, created_at=? WHERE name=?",
                (ct, iv, salt, now, body.name),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM secrets WHERE name=?", (body.name,)).fetchone()
            return {"id": row["id"], "name": body.name, "created_at": now, "updated": True}


@_router.post("/secrets/retrieve")
async def retrieve_secret(body: RetrieveIn, x_internal_secret: str = Header(default="")):
    _check_auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM secrets WHERE name=?", (body.name,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Secret not found")
        try:
            plaintext = _decrypt(
                bytes(row["encrypted_val"]), bytes(row["iv"]), bytes(row["salt"]), MASTER_KEY_ENV
            )
        except Exception:
            raise HTTPException(
                status_code=500, detail="Decryption failed — wrong master key?"
            ) from None
        conn.execute(
            "UPDATE secrets SET accessed_at=?, access_count=access_count+1 WHERE name=?",
            (now, body.name),
        )
        conn.commit()
    return {"name": body.name, "value": plaintext, "accessed_at": now}


@_router.get("/secrets")
async def list_secrets(x_internal_secret: str = Header(default="")):
    _check_auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at, accessed_at, access_count FROM secrets ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


@_router.get("/secrets/{secret_id}")
async def get_secret_meta(secret_id: int, x_internal_secret: str = Header(default="")):
    _check_auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, created_at, accessed_at, access_count FROM secrets WHERE id=?",
            (secret_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Secret not found")
    return dict(row)


@_router.delete("/secrets/{secret_id}", status_code=204)
async def delete_secret(secret_id: int, x_internal_secret: str = Header(default="")):
    _check_auth(x_internal_secret)
    with get_conn() as conn:
        deleted = conn.execute("DELETE FROM secrets WHERE id=?", (secret_id,)).rowcount
        conn.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Secret not found")


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
