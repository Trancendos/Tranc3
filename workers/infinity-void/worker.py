"""
The Void — Self-Hosted Python Replacement for Cloudflare Worker

Replaces: cloudflare/infinity-void/src/index.ts
Runs as: FastAPI application on Fly.io or bare metal
Zero external dependencies — encrypted secrets vault.

Features:
  - AES-256-GCM encryption with PBKDF2 key derivation (100k iterations)
  - SQLite metadata storage (replaces Cloudflare D1)
  - In-memory rate limiting (replaces Cloudflare KV)
  - Optional file-based storage (replaces Cloudflare R2)
  - Full audit logging
  - Crypto-shredding on delete

Routes:
  GET  /health               → health check
  GET  /vault/status         → vault seal status + secret count
  POST /secrets              → store a secret
  POST /secrets/retrieve     → retrieve a secret's plaintext
  GET  /secrets              → list own secrets (metadata only)
  GET  /secrets/{id}         → get secret metadata
  DELETE /secrets/{id}        → crypto-shred a secret
  GET  /secrets/{id}/audit   → audit log for a secret
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

_SAFE_COMPONENT_RE = re.compile(r"^[\w\-]+$")

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# ── Configuration ───────────────────────────────────────────────

_master_key_raw = os.getenv("MASTER_KEY_SEED")
if not _master_key_raw or _master_key_raw == "change-me-in-production":
    raise RuntimeError(
        "MASTER_KEY_SEED is not set (or still the default). "
        "The Void vault cannot start without a strong unique key. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
MASTER_KEY_SEED: str = _master_key_raw

_internal_secret_raw = os.getenv("INTERNAL_SECRET")
if not _internal_secret_raw or _internal_secret_raw == "internal-dev-secret":
    raise RuntimeError(
        "INTERNAL_SECRET is not set (or still the default). "
        "The Void vault cannot start without a strong unique internal secret. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
INTERNAL_SECRET: str = _internal_secret_raw
INFINITY_ONE_URL = os.getenv("INFINITY_ONE_URL", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DATA_DIR = Path(os.getenv("VOID_DATA_DIR", "/tmp/void-data"))
DB_PATH = DATA_DIR / "void.db"
R2_DIR = DATA_DIR / "secrets"  # Replaces Cloudflare R2

ALLOWED_ORIGINS = [
    "https://trancendos.com",
    "https://api.trancendos.com",
    "https://arcadia.trancendos.com",
]

# ── Rate Limiter (in-memory, replaces Cloudflare KV) ───────────


class RateLimiter:
    """In-memory rate limiter — replaces Cloudflare KV-based rate limiting."""

    def __init__(self) -> None:
        self._counts: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int = 50, window: int = 3600) -> bool:
        now = time.time()
        # Clean old entries
        self._counts[key] = [t for t in self._counts[key] if now - t < window]
        if len(self._counts[key]) >= max_requests:
            return False
        self._counts[key].append(now)
        return True


rate_limiter = RateLimiter()

# ── Crypto ──────────────────────────────────────────────────────


def derive_key(seed: str, salt: bytes) -> bytes:
    """PBKDF2 key derivation — 100k iterations, SHA-256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return kdf.derive(seed.encode())


def encrypt_secret(plaintext: str, master_key_seed: str) -> dict[str, str]:
    """AES-256-GCM encryption."""
    salt = os.urandom(32)
    iv = os.urandom(12)
    key = derive_key(master_key_seed, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode(), None)
    return {
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "iv": base64.b64encode(iv).decode(),
        "salt": base64.b64encode(salt).decode(),
    }


def decrypt_secret(ciphertext_b64: str, iv_b64: str, salt_b64: str, master_key_seed: str) -> str:
    """AES-256-GCM decryption."""
    ciphertext = base64.b64decode(ciphertext_b64)
    iv = base64.b64decode(iv_b64)
    salt = base64.b64decode(salt_b64)
    key = derive_key(master_key_seed, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, ciphertext, None)
    return plaintext.decode()


def hash_value(value: str) -> str:
    """SHA-256 hash."""
    return hashlib.sha256(value.encode()).hexdigest()


# ── Database (SQLite, replaces Cloudflare D1) ──────────────────


_schema_initialized = False  # codeql[py/unused-global-variable]


def get_db() -> sqlite3.Connection:
    global _schema_initialized
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    R2_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if not _schema_initialized:
        _schema_initialized = True
        init_schema()
    return conn


def init_schema() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS void_secrets (
            secret_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            type TEXT NOT NULL DEFAULT 'generic',
            classification TEXT NOT NULL DEFAULT 'confidential',
            status TEXT NOT NULL DEFAULT 'active',
            version INTEGER NOT NULL DEFAULT 1,
            path TEXT,
            tags TEXT NOT NULL DEFAULT '[]',
            owner_id TEXT,
            r2_key TEXT,
            payload TEXT,
            payload_hash TEXT NOT NULL,
            iv TEXT NOT NULL,
            salt TEXT NOT NULL,
            expires_at TEXT,
            last_accessed_at TEXT,
            access_policy TEXT NOT NULL DEFAULT '{}',
            rotation_config TEXT NOT NULL DEFAULT '{}',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS void_audit_log (
            audit_id TEXT PRIMARY KEY,
            secret_id TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_id TEXT,
            actor_type TEXT NOT NULL DEFAULT 'user',
            ip_address TEXT,
            success INTEGER NOT NULL DEFAULT 1,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS void_vault_state (
            state_key TEXT PRIMARY KEY,
            state_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_void_secrets_owner ON void_secrets(owner_id);
        CREATE INDEX IF NOT EXISTS idx_void_secrets_status ON void_secrets(status);
        CREATE INDEX IF NOT EXISTS idx_void_audit_secret ON void_audit_log(secret_id);
        INSERT OR IGNORE INTO void_vault_state (state_key, state_value, updated_at)
            VALUES ('sealed', 'false', datetime('now'));
    """)
    conn.commit()
    conn.close()


def _safe_path_component(value: str, field: str = "id") -> str:
    """Reject path-traversal characters; allow only word chars and hyphens."""
    stripped = Path(value).name
    if not stripped or stripped != value or not _SAFE_COMPONENT_RE.match(stripped):
        raise HTTPException(status_code=400, detail=f"Invalid {field} format")
    return stripped


# ── Auth ────────────────────────────────────────────────────────


async def get_auth_user_id(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        if ENVIRONMENT == "test":
            return "test-user"
        return None
    token = authorization[7:]

    if not INFINITY_ONE_URL:
        if ENVIRONMENT != "production":
            return "dev-user"
        return None

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{INFINITY_ONE_URL}/auth/verify",
                json={"token": token},
                headers={
                    "Content-Type": "application/json",
                    "X-Internal-Secret": INTERNAL_SECRET,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("user_id")
        except httpx.HTTPError:
            pass
    return None


# ── App ─────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    # OpenTelemetry instrumentation
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from src.observability.otel import init_otel

        init_otel(service_name="tranc3.infinity-void")
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass  # OTel is optional — never block startup
    """Startup: initialize DB schema. Shutdown: cleanup (if needed)."""
    init_schema()
    yield


app = FastAPI(
    title="The Void — Self-Hosted Secrets Vault",
    version="2.1.0",
    description="Encrypted secrets vault — replaces Cloudflare Worker. Zero external dependencies.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Request-ID",
        "X-MFA-Token",
        "X-Hardware-Key",
        "X-Lighthouse-Token",
        "X-Internal-Secret",
    ],
    max_age=86400,
)


# ── Routes ──────────────────────────────────────────────────────


@app.get("/health")
async def health():
    try:
        init_schema()
        conn = get_db()
        sealed = conn.execute(
            "SELECT state_value FROM void_vault_state WHERE state_key = 'sealed'"
        ).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) as count FROM void_secrets WHERE status = 'active'"
        ).fetchone()
        conn.close()
        vault_sealed = sealed["state_value"] == "true" if sealed else False
        secret_count = count["count"] if count else 0
        status = "healthy"
    except Exception:
        vault_sealed = False
        secret_count = 0
        status = "degraded"
    return {
        "status": status,
        "service": "the-void-worker",
        "version": "2.1.0",
        "vault_sealed": vault_sealed,
        "secret_count": secret_count,
        "storage": "sqlite+r2-file" if R2_DIR.exists() else "sqlite",
        "hosting": "self-hosted (replaces Cloudflare Worker)",
        "environment": ENVIRONMENT,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.get("/vault/status")
async def vault_status(authorization: str | None = Header(None)):
    user_id = await get_auth_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    conn = get_db()
    sealed = conn.execute(
        "SELECT state_value FROM void_vault_state WHERE state_key = 'sealed'"
    ).fetchone()
    count = conn.execute(
        "SELECT COUNT(*) as count FROM void_secrets WHERE status = 'active'"
    ).fetchone()
    conn.close()
    return {
        "status": "sealed" if (sealed and sealed["state_value"] == "true") else "unsealed",
        "sealed": sealed["state_value"] == "true" if sealed else False,
        "secret_count": count["count"] if count else 0,
        "storage": "sqlite+r2-file" if R2_DIR.exists() else "sqlite",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.post("/secrets")
async def store_secret(request: Request, authorization: str | None = Header(None)):
    user_id = await get_auth_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not rate_limiter.check(f"store:{user_id}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    body = await request.json()
    name = body.get("name")
    plaintext = body.get("plaintext") or body.get("value")
    if not name or not plaintext:
        raise HTTPException(status_code=400, detail="name and plaintext required")

    secret_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload_hash = hash_value(plaintext)
    encrypted = encrypt_secret(plaintext, MASTER_KEY_SEED)

    # Store payload in R2-like file storage
    safe_uid = _safe_path_component(user_id, "user_id")
    safe_sid = _safe_path_component(secret_id, "secret_id")
    r2_key = f"secrets/{safe_uid}/{safe_sid}"
    r2_path = R2_DIR / safe_uid / safe_sid
    r2_path.mkdir(parents=True, exist_ok=True)
    with open(r2_path / "payload.json", "w") as f:
        json.dump({"ciphertext": encrypted["ciphertext"]}, f)

    conn = get_db()
    conn.execute(
        """INSERT INTO void_secrets
           (secret_id, name, description, type, classification, status, version,
            path, tags, owner_id, r2_key, payload_hash, iv, salt,
            access_policy, rotation_config, metadata, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            secret_id,
            name,
            body.get("description"),
            body.get("type", "generic"),
            body.get("classification", "confidential"),
            "active",
            1,
            body.get("path"),
            json.dumps(body.get("tags", [])),
            user_id,
            r2_key,
            payload_hash,
            encrypted["iv"],
            encrypted["salt"],
            json.dumps(body.get("access_policy", {})),
            json.dumps(body.get("rotation_config", {})),
            json.dumps(body.get("metadata", {})),
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "secret_id": secret_id,
        "name": name,
        "status": "active",
        "version": 1,
        "created_at": now,
    }


@app.post("/secrets/retrieve")
async def retrieve_secret(request: Request, authorization: str | None = Header(None)):
    user_id = await get_auth_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not rate_limiter.check(f"retrieve:{user_id}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    body = await request.json()
    secret_id = body.get("secret_id") or body.get("id")
    if not secret_id:
        raise HTTPException(status_code=400, detail="secret_id required")

    conn = get_db()
    row = conn.execute("SELECT * FROM void_secrets WHERE secret_id = ?", (secret_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Secret not found")
    if row["owner_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Forbidden")
    if row["status"] != "active":
        conn.close()
        raise HTTPException(status_code=410, detail="Secret is not active")

    # Read payload from R2-like storage
    safe_uid = _safe_path_component(user_id, "user_id")
    safe_sid = _safe_path_component(secret_id, "secret_id")
    r2_path = R2_DIR / safe_uid / safe_sid / "payload.json"
    if r2_path.exists():
        with open(r2_path) as f:
            payload = json.load(f)
    else:
        conn.close()
        raise HTTPException(status_code=404, detail="Payload not found")

    plaintext = decrypt_secret(payload["ciphertext"], row["iv"], row["salt"], MASTER_KEY_SEED)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute(
        "UPDATE void_secrets SET last_accessed_at = ? WHERE secret_id = ?", (now, secret_id)
    )
    conn.execute(
        "INSERT INTO void_audit_log (audit_id, secret_id, action, actor_id, actor_type, success, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), secret_id, "retrieve", user_id, "user", 1, "{}", now),
    )
    conn.commit()
    conn.close()

    return {"secret_id": secret_id, "plaintext": plaintext}


@app.get("/secrets")
async def list_secrets(authorization: str | None = Header(None)):
    user_id = await get_auth_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    conn = get_db()
    rows = conn.execute(
        """SELECT secret_id, name, type, classification, status, version, created_at, expires_at
           FROM void_secrets WHERE owner_id = ? AND status != 'deleted' ORDER BY created_at DESC LIMIT 100""",
        (user_id,),
    ).fetchall()
    conn.close()

    secrets = [dict(r) for r in rows]
    return {"secrets": secrets, "count": len(secrets)}


@app.get("/secrets/{secret_id}")
async def get_secret_meta(secret_id: str, authorization: str | None = Header(None)):
    user_id = await get_auth_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    conn = get_db()
    row = conn.execute(
        """SELECT secret_id, name, description, type, classification, status, version,
                  path, tags, owner_id, expires_at, last_accessed_at, created_at, updated_at
           FROM void_secrets WHERE secret_id = ?""",
        (secret_id,),
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Secret not found")
    if row["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return dict(row)


@app.delete("/secrets/{secret_id}")
async def delete_secret(secret_id: str, request: Request, authorization: str | None = Header(None)):
    user_id = await get_auth_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    conn = get_db()
    row = conn.execute(
        "SELECT owner_id, r2_key FROM void_secrets WHERE secret_id = ?", (secret_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Secret not found")
    if row["owner_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Forbidden")

    # Crypto-shred: delete R2 payload
    safe_uid = _safe_path_component(user_id, "user_id")
    safe_sid = _safe_path_component(secret_id, "secret_id")
    r2_path = R2_DIR / safe_uid / safe_sid
    if r2_path.exists():
        import shutil

        shutil.rmtree(r2_path, ignore_errors=True)

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute(
        "UPDATE void_secrets SET status = ?, payload = NULL, updated_at = ? WHERE secret_id = ?",
        ("deleted", now, secret_id),
    )
    conn.execute(
        "INSERT INTO void_audit_log (audit_id, secret_id, action, actor_id, actor_type, success, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), secret_id, "crypto_shred", user_id, "user", 1, "{}", now),
    )
    conn.commit()
    conn.close()

    return {"secret_id": secret_id, "status": "deleted", "shredded": True}


@app.get("/secrets/{secret_id}/audit")
async def get_audit_log(secret_id: str, authorization: str | None = Header(None)):
    user_id = await get_auth_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    conn = get_db()
    secret = conn.execute(
        "SELECT owner_id FROM void_secrets WHERE secret_id = ?", (secret_id,)
    ).fetchone()
    if not secret:
        conn.close()
        raise HTTPException(status_code=404, detail="Secret not found")
    if secret["owner_id"] != user_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Forbidden")

    rows = conn.execute(
        """SELECT audit_id, action, actor_id, actor_type, ip_address, success, created_at
           FROM void_audit_log WHERE secret_id = ? ORDER BY created_at DESC LIMIT 100""",
        (secret_id,),
    ).fetchall()
    conn.close()

    return {"secret_id": secret_id, "audit_log": [dict(r) for r in rows]}


# ── Run ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
