"""
Trancendos warp-tunnel — Cryptographic Scanner & Quarantine Transport
=====================================================================
File quarantine, threat scanning, safe transfer hub.
Scans uploaded content for known threat patterns
quarantines suspicious files.

Port: 8040  Entity: The Warp Tunnel  Lead AI: Rocking Ricki
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

WORKER_PORT = int(os.getenv("PORT", "8040"))
WORKER_NAME = "warp-tunnel"
DB_PATH = Path(__file__).parent / "data" / "warp_tunnel.db"
QUARANTINE_DIR = Path(__file__).parent / "data" / "quarantine"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50 MB default

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0

# Basic threat signatures (YARA-lite style, zero-cost)
THREAT_PATTERNS = [
    (re.compile(rb"eval\s*\(\s*base64_decode", re.IGNORECASE), "php_webshell"),
    (re.compile(rb"<\?php.*system\s*\(", re.IGNORECASE | re.DOTALL), "php_system_call"),
    (re.compile(rb"powershell.*-enc\s+[A-Za-z0-9+/]{20}", re.IGNORECASE), "ps_encoded_cmd"),
    (re.compile(rb"cmd\.exe\s*/c\s+\S+", re.IGNORECASE), "cmd_injection"),
    (re.compile(rb"\x4d\x5a\x90\x00"), "pe_executable"),
    (re.compile(rb"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"), "eicar_test"),
    (
        re.compile(rb"(?:union\s+select|select\s+.*from\s+information_schema)", re.IGNORECASE),
        "sql_injection",
    ),
    (re.compile(rb"<script[^>]*>.*?alert\s*\(", re.IGNORECASE | re.DOTALL), "xss_payload"),
]


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
            CREATE TABLE IF NOT EXISTS scan_jobs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                filename     TEXT NOT NULL,
                sha256       TEXT NOT NULL,
                file_size    INTEGER NOT NULL,
                status       TEXT NOT NULL DEFAULT 'pending',
                threat_level TEXT,
                threats      TEXT DEFAULT '[]',
                scanned_at   REAL,
                created_at   REAL NOT NULL,
                quarantined  INTEGER DEFAULT 0,
                quarantine_path TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_sha ON scan_jobs(sha256)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_status ON scan_jobs(status)")
        conn.commit()


# ---------------------------------------------------------------------------
# Scan logic
# ---------------------------------------------------------------------------


def _scan_content(content: bytes) -> tuple[str, list[str]]:
    """Return (threat_level, [matched_threats])."""
    found = []
    for pattern, name in THREAT_PATTERNS:
        if pattern.search(content):
            found.append(name)
    if not found:
        return "clean", []
    critical = {"pe_executable", "php_webshell", "eicar_test"}
    if any(t in critical for t in found):
        return "critical", found
    return "suspicious", found


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield
    logger.info("%s shutdown", WORKER_NAME)


app = FastAPI(title="The Warp Tunnel — Threat Scanner", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_router = APIRouter()


def _safe_filename(name: str | None) -> str:
    """Sanitise filename to prevent path traversal (CWE-22)."""
    if not name:
        return "unknown"
    name = unicodedata.normalize("NFKC", name)
    name = Path(name).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name[:255] or "unknown"


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@_router.get("/health")
async def health():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM scan_jobs").fetchone()[0]
        quarantined = conn.execute("SELECT COUNT(*) FROM scan_jobs WHERE quarantined=1").fetchone()[
            0
        ]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "The Warp Tunnel", "lead_ai": "Rocking Ricki"},
        "total_scanned": total,
        "quarantined": quarantined,
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


@_router.post("/scan", status_code=201)
async def scan_file(
    file: UploadFile = File(...),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    sha256 = hashlib.sha256(content).hexdigest()
    now = time.time()
    threat_level, threats = _scan_content(content)

    quarantined = 0
    quarantine_path = None
    if threat_level in ("critical", "suspicious"):
        q_path = QUARANTINE_DIR / f"{sha256[:16]}_{_safe_filename(file.filename)}"
        q_path.write_bytes(content)
        quarantined = 1
        quarantine_path = str(q_path)
        logger.warning("Quarantined %s: %s (%s)", file.filename, threats, threat_level)

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO scan_jobs (filename, sha256, file_size, status, threat_level, threats, scanned_at, created_at, quarantined, quarantine_path) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                file.filename or "unknown",
                sha256,
                len(content),
                "scanned",
                threat_level,
                json.dumps(threats),
                now,
                now,
                quarantined,
                quarantine_path,
            ),
        )
        conn.commit()
        job_id = cur.lastrowid

    return {
        "id": job_id,
        "filename": file.filename,
        "sha256": sha256,
        "file_size": len(content),
        "threat_level": threat_level,
        "threats": threats,
        "quarantined": bool(quarantined),
        "scanned_at": now,
    }


@_router.post("/scan/hash")
async def scan_by_hash(payload: dict, x_internal_secret: str = Header(default="")):
    """Check if a SHA256 hash has been seen before."""
    _auth(x_internal_secret)
    sha256 = payload.get("sha256", "")
    if not sha256:
        raise HTTPException(status_code=400, detail="sha256 required")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, threat_level, threats, scanned_at FROM scan_jobs WHERE sha256=?",
            (sha256,),
        ).fetchall()
    if not rows:
        return {"known": False, "sha256": sha256}
    return {"known": True, "sha256": sha256, "history": [dict(r) for r in rows]}


@_router.get("/scans")
async def list_scans(
    threat_level: Optional[str] = None,
    quarantined: Optional[bool] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if threat_level:
        clauses.append("threat_level = ?")
        params.append(threat_level)
    if quarantined is not None:
        clauses.append("quarantined = ?")
        params.append(int(quarantined))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM scan_jobs {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM scan_jobs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "scans": [dict(r) for r in rows]}


@_router.get("/scans/{scan_id}")
async def get_scan(scan_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM scan_jobs WHERE id=?", (scan_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Scan not found")
    return dict(row)


@_router.delete("/quarantine/{scan_id}", status_code=204)
async def release_quarantine(scan_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM scan_jobs WHERE id=?", (scan_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Scan not found")
        if row["quarantine_path"] and Path(row["quarantine_path"]).exists():
            Path(row["quarantine_path"]).unlink(missing_ok=True)
        conn.execute(
            "UPDATE scan_jobs SET quarantined=0, quarantine_path=NULL WHERE id=?", (scan_id,)
        )
        conn.commit()


@_router.get("/stats")
async def stats(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM scan_jobs").fetchone()[0]
        by_level = conn.execute(
            "SELECT threat_level, COUNT(*) c FROM scan_jobs GROUP BY threat_level"
        ).fetchall()
        q_count = conn.execute("SELECT COUNT(*) FROM scan_jobs WHERE quarantined=1").fetchone()[0]
    return {
        "total_scanned": total,
        "quarantined": q_count,
        "by_threat_level": [dict(r) for r in by_level],
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
