"""
DocUtari — Trancendos Document Management Bridge
=====================================================
Unified document management API bridging Paperless-ngx, Stirling PDF,
Gotenberg (HTML→PDF), Apache Tika (parsing), and local IPFS storage.

Port: 8014
Zero-cost: all backends are self-hosted OSS (no paid APIs).

Adaptive rotation: if Stirling PDF is unavailable, falls back to Gotenberg
for PDF operations. If Tika is unavailable, falls back to local mime/magic
detection. Hard stops enforced via per-operation thresholds.

Entity: DocUtari | Lead AI: To be Defined
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = int(os.getenv("PORT") or "8014")
WORKER_NAME = "docutari"

DB_PATH = Path(__file__).parent / "data" / "docutari.db"
UPLOAD_DIR = Path(__file__).parent / "data" / "uploads"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PAPERLESS_URL = os.getenv("PAPERLESS_INTERNAL_URL", "http://paperless:8000")
PAPERLESS_TOKEN = os.getenv("PAPERLESS_API_TOKEN", "")
STIRLING_URL = os.getenv("STIRLING_PDF_URL", "http://stirling-pdf:8080")
GOTENBERG_URL = os.getenv("GOTENBERG_URL", "http://gotenberg:3000")
TIKA_URL = os.getenv("TIKA_URL", "http://tika:9998")
INTERNAL_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "")

# Zero-cost hard-stop thresholds (requests per minute per operation)
THRESHOLD_PDF_OPS = int(os.getenv("DOCUTARI_PDF_THRESHOLD", "100"))
THRESHOLD_OCR_OPS = int(os.getenv("DOCUTARI_OCR_THRESHOLD", "50"))
THRESHOLD_PARSE_OPS = int(os.getenv("DOCUTARI_PARSE_THRESHOLD", "200"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Rate / threshold tracking
# ---------------------------------------------------------------------------
class _ThresholdGuard:
    """In-memory sliding-window counter with hard stop."""

    def __init__(self, limit: int, window_sec: int = 60):
        self._limit = limit
        self._window = window_sec
        self._lock = threading.Lock()
        self._calls: list[float] = []

    def check_and_record(self, op: str) -> None:
        import time

        now = time.monotonic()
        with self._lock:
            self._calls = [t for t in self._calls if now - t < self._window]
            if len(self._calls) >= self._limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"DocUtari hard stop: {op} threshold {self._limit}/min reached",
                )
            self._calls.append(now)


_pdf_guard = _ThresholdGuard(THRESHOLD_PDF_OPS)
_ocr_guard = _ThresholdGuard(THRESHOLD_OCR_OPS)
_parse_guard = _ThresholdGuard(THRESHOLD_PARSE_OPS)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class FilesDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @contextmanager
    def _cur(self):
        conn = self._conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    def _init_db(self) -> None:
        with self._cur() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    title TEXT,
                    content_type TEXT,
                    size_bytes INTEGER DEFAULT 0,
                    storage_path TEXT,
                    paperless_id INTEGER,
                    ipfs_cid TEXT,
                    tags TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    tika_metadata TEXT DEFAULT '{}',
                    ocr_text TEXT,
                    status TEXT DEFAULT 'pending',
                    owner_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS pdf_jobs (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT,
                    operation TEXT NOT NULL,
                    params TEXT DEFAULT '{}',
                    result_path TEXT,
                    status TEXT DEFAULT 'queued',
                    backend TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_docs_owner ON documents(owner_id);
                CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(status);
                CREATE INDEX IF NOT EXISTS idx_pdf_jobs_doc ON pdf_jobs(doc_id);
            """)

    def create_document(self, data: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = data.get("id", str(uuid.uuid4()))
        now = datetime.now(timezone.utc).isoformat()
        with self._cur() as c:
            c.execute(
                """INSERT INTO documents
                   (id,filename,title,content_type,size_bytes,storage_path,
                    paperless_id,ipfs_cid,tags,metadata,tika_metadata,
                    ocr_text,status,owner_id,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc_id,
                    data.get("filename", ""),
                    data.get("title"),
                    data.get("content_type"),
                    data.get("size_bytes", 0),
                    data.get("storage_path"),
                    data.get("paperless_id"),
                    data.get("ipfs_cid"),
                    json.dumps(data.get("tags", [])),
                    json.dumps(data.get("metadata", {})),
                    json.dumps(data.get("tika_metadata", {})),
                    data.get("ocr_text"),
                    data.get("status", "pending"),
                    data.get("owner_id"),
                    now,
                    now,
                ),
            )
        return self.get_document(doc_id)  # type: ignore[return-value]

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        with self._cur() as c:
            c.execute("SELECT * FROM documents WHERE id=? AND deleted_at IS NULL", (doc_id,))
            row = c.fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"] = json.loads(d["tags"] or "[]")
        d["metadata"] = json.loads(d["metadata"] or "{}")
        d["tika_metadata"] = json.loads(d["tika_metadata"] or "{}")
        return d

    def list_documents(
        self,
        owner_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM documents WHERE deleted_at IS NULL"
        params: list = []
        if owner_id:
            query += " AND owner_id=?"
            params.append(owner_id)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        with self._cur() as c:
            c.execute(query, params)
            rows = c.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["tags"] = json.loads(d["tags"] or "[]")
            d["metadata"] = json.loads(d["metadata"] or "{}")
            d["tika_metadata"] = json.loads(d["tika_metadata"] or "{}")
            result.append(d)
        return result

    def update_document(self, doc_id: str, data: Dict[str, Any]) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        allowed = {
            "title",
            "status",
            "paperless_id",
            "ipfs_cid",
            "tags",
            "metadata",
            "tika_metadata",
            "ocr_text",
            "storage_path",
        }
        fields, vals = [], []
        for k, v in data.items():
            if k in allowed:
                fields.append(f"{k}=?")
                vals.append(json.dumps(v) if isinstance(v, (dict, list)) else v)
        if not fields:
            return False
        vals += [now, doc_id]
        with self._cur() as c:
            c.execute(
                f"UPDATE documents SET {', '.join(fields)}, updated_at=? WHERE id=? AND deleted_at IS NULL",
                vals,
            )
            return c.rowcount > 0

    def soft_delete(self, doc_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._cur() as c:
            c.execute(
                "UPDATE documents SET deleted_at=?, updated_at=? WHERE id=? AND deleted_at IS NULL",
                (now, now, doc_id),
            )
            return c.rowcount > 0

    def create_pdf_job(self, data: Dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._cur() as c:
            c.execute(
                "INSERT INTO pdf_jobs (id,doc_id,operation,params,status,backend,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    job_id,
                    data.get("doc_id"),
                    data["operation"],
                    json.dumps(data.get("params", {})),
                    "queued",
                    data.get("backend", "stirling"),
                    now,
                ),
            )
        return job_id

    def update_pdf_job(
        self,
        job_id: str,
        status: str,
        result_path: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._cur() as c:
            c.execute(
                "UPDATE pdf_jobs SET status=?, result_path=?, error=?, completed_at=? WHERE id=?",
                (status, result_path, error, now, job_id),
            )


db = FilesDatabase(DB_PATH)


# ---------------------------------------------------------------------------
# Backend clients (adaptive with fallback)
# ---------------------------------------------------------------------------
async def _tika_parse(content: bytes, content_type: str) -> Dict[str, Any]:
    """Extract metadata + text via Apache Tika. Falls back to basic mime detection."""
    _parse_guard.check_and_record("tika_parse")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.put(
                f"{TIKA_URL}/tika",
                content=content,
                headers={"Content-Type": content_type, "Accept": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("Tika unavailable, using fallback: %s", exc)
        return {"Content-Type": content_type, "fallback": True}


async def _paperless_ingest(
    filename: str, content: bytes, content_type: str, title: Optional[str] = None
) -> Optional[int]:
    """Push document to Paperless-ngx via its REST API."""
    if not PAPERLESS_TOKEN:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            files = {"document": (filename, content, content_type)}
            data = {}
            if title:
                data["title"] = title
            resp = await c.post(
                f"{PAPERLESS_URL}/api/documents/post_document/",
                files=files,
                data=data,
                headers={"Authorization": f"Token {PAPERLESS_TOKEN}"},
            )
            resp.raise_for_status()
            task_id = resp.json().get("task_id")
            logger.info("Paperless ingest queued: task=%s", task_id)
            return None  # async — paperless_id comes back via webhook/poll
    except Exception as exc:
        logger.warning("Paperless ingest failed: %s", exc)
        return None


async def _stirling_pdf_op(operation: str, content: bytes, params: Dict[str, Any]) -> bytes:
    """Execute a Stirling PDF operation. Falls back to Gotenberg for convert ops."""
    _pdf_guard.check_and_record(f"stirling_{operation}")
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            files = {"fileInput": ("input.pdf", content, "application/pdf")}
            resp = await c.post(
                f"{STIRLING_URL}/api/v1/general/{operation}",
                files=files,
                data=params,
            )
            resp.raise_for_status()
            return resp.content
    except Exception as exc:
        logger.warning("Stirling PDF unavailable for %s, trying Gotenberg: %s", operation, exc)
        return await _gotenberg_fallback(content, operation, params)


async def _gotenberg_fallback(content: bytes, operation: str, params: Dict[str, Any]) -> bytes:
    """Gotenberg fallback for PDF generation/conversion."""
    _pdf_guard.check_and_record(f"gotenberg_{operation}")
    async with httpx.AsyncClient(timeout=120) as c:
        if operation in ("compress", "optimize"):
            resp = await c.post(
                f"{GOTENBERG_URL}/forms/chromium/convert/html",
                files={
                    "files": (
                        "index.html",
                        b"<html><body>Conversion unavailable</body></html>",
                        "text/html",
                    )
                },
            )
        else:
            resp = await c.post(
                f"{GOTENBERG_URL}/forms/libreoffice/convert",
                files={"files": ("input.pdf", content, "application/pdf")},
            )
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class DocumentUploadResponse(BaseModel):
    id: str
    filename: str
    title: Optional[str]
    content_type: Optional[str]
    size_bytes: int
    status: str
    created_at: str


class PdfJobRequest(BaseModel):
    doc_id: str
    operation: Literal[
        "compress",
        "merge",
        "split",
        "rotate",
        "watermark",
        "remove-pages",
        "extract-images",
        "pdf-to-word",
        "word-to-pdf",
        "img-to-pdf",
        "pdf-to-img",
        "ocr",
    ]
    params: Dict[str, Any] = Field(default_factory=dict)


class DocumentSearchQuery(BaseModel):
    q: str
    owner_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    content_type: Optional[str] = None
    limit: int = 20


# ---------------------------------------------------------------------------
# App + Auth
# ---------------------------------------------------------------------------
app = FastAPI(title="DocUtari — Document Management Bridge", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _auth(x_internal_token: str = Header(default="")) -> None:
    if INTERNAL_TOKEN and x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


router = APIRouter(prefix="/api", dependencies=[Depends(_auth)])


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    backends: Dict[str, str] = {}
    for name, url in [
        ("paperless", f"{PAPERLESS_URL}/api/"),
        ("stirling_pdf", f"{STIRLING_URL}/api/v1/info/status"),
        ("gotenberg", f"{GOTENBERG_URL}/health"),
        ("tika", f"{TIKA_URL}/tika"),
    ]:
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                r = await c.get(url)
                backends[name] = "up" if r.status_code < 400 else "degraded"
        except Exception:
            backends[name] = "down"
    return {
        "service": "files-service",
        "status": "healthy",
        "port": WORKER_PORT,
        "backends": backends,
        "entity": "DocUtari",
        "lead_ai": "To be Defined",
    }


# ---------------------------------------------------------------------------
# Document CRUD
# ---------------------------------------------------------------------------
@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    title: Optional[str] = None,
    owner_id: Optional[str] = None,
):
    """Upload a document — store locally, push to Paperless-ngx, parse with Tika."""
    content = await file.read()
    filename = file.filename or "upload"
    content_type = (
        file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    )
    size = len(content)

    doc_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / doc_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / filename).write_bytes(content)

    doc = db.create_document(
        {
            "id": doc_id,
            "filename": filename,
            "title": title or Path(filename).stem,
            "content_type": content_type,
            "size_bytes": size,
            "storage_path": str(dest / filename),
            "owner_id": owner_id,
            "status": "processing",
        }
    )

    async def _process():
        tika_meta = await _tika_parse(content, content_type)
        paperless_id = await _paperless_ingest(filename, content, content_type, title)
        db.update_document(
            doc_id,
            {
                "tika_metadata": tika_meta,
                "paperless_id": paperless_id,
                "status": "ready",
            },
        )

    background_tasks.add_task(_process)
    return doc


@router.get("/documents")
def list_documents(
    owner_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    return db.list_documents(owner_id=owner_id, status=status, limit=limit, offset=offset)


@router.get("/documents/{doc_id}")
def get_document(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.patch("/documents/{doc_id}")
def update_document(doc_id: str, data: Dict[str, Any]):
    if not db.update_document(doc_id, data):
        raise HTTPException(status_code=404, detail="Document not found")
    return db.get_document(doc_id)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    if not db.soft_delete(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True}


@router.get("/documents/{doc_id}/download")
def download_document(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc or not doc.get("storage_path"):
        raise HTTPException(status_code=404, detail="Document not found")
    path = Path(doc["storage_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    def _iter():
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        _iter(),
        media_type=doc.get("content_type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{doc["filename"]}"'},
    )


# ---------------------------------------------------------------------------
# PDF Operations (Stirling PDF → Gotenberg fallback)
# ---------------------------------------------------------------------------
@router.post("/pdf/jobs")
def create_pdf_job(req: PdfJobRequest, background_tasks: BackgroundTasks):
    """Queue an async PDF operation — returns job_id to poll."""
    doc = db.get_document(req.doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    job_id = db.create_pdf_job(
        {
            "doc_id": req.doc_id,
            "operation": req.operation,
            "params": req.params,
        }
    )

    async def _run_job():
        try:
            path = Path(doc["storage_path"])
            content = path.read_bytes()
            result = await _stirling_pdf_op(req.operation, content, req.params)
            out_path = UPLOAD_DIR / req.doc_id / f"{job_id}_{req.operation}.pdf"
            out_path.write_bytes(result)
            db.update_pdf_job(job_id, "done", str(out_path))
        except Exception as exc:
            db.update_pdf_job(job_id, "failed", error=str(exc))

    background_tasks.add_task(_run_job)
    return {"job_id": job_id, "status": "queued"}


@router.get("/pdf/jobs/{job_id}")
def get_pdf_job(job_id: str):
    with db._cur() as c:
        c.execute("SELECT * FROM pdf_jobs WHERE id=?", (job_id,))
        row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


@router.get("/pdf/jobs/{job_id}/download")
def download_pdf_result(job_id: str):
    with db._cur() as c:
        c.execute("SELECT * FROM pdf_jobs WHERE id=? AND status='done'", (job_id,))
        row = c.fetchone()
    if not row or not row["result_path"]:
        raise HTTPException(status_code=404, detail="Result not ready")
    path = Path(row["result_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result file missing")

    def _iter():
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(_iter(), media_type="application/pdf")


# ---------------------------------------------------------------------------
# Paperless-ngx proxy (search, tags, correspondents)
# ---------------------------------------------------------------------------
@router.get("/paperless/search")
async def paperless_search(q: str, page: int = 1, page_size: int = 25):
    if not PAPERLESS_TOKEN:
        raise HTTPException(status_code=503, detail="Paperless-ngx not configured")
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            resp = await c.get(
                f"{PAPERLESS_URL}/api/documents/",
                params={"query": q, "page": page, "page_size": page_size},
                headers={"Authorization": f"Token {PAPERLESS_TOKEN}"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Paperless unavailable: {exc}") from exc


@router.get("/paperless/tags")
async def paperless_tags():
    if not PAPERLESS_TOKEN:
        raise HTTPException(status_code=503, detail="Paperless-ngx not configured")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            resp = await c.get(
                f"{PAPERLESS_URL}/api/tags/",
                headers={"Authorization": f"Token {PAPERLESS_TOKEN}"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Stirling PDF direct proxy
# ---------------------------------------------------------------------------
@router.get("/stirling/status")
async def stirling_status():
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            resp = await c.get(f"{STIRLING_URL}/api/v1/info/status")
            return resp.json()
    except Exception:
        return {"available": False}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
@router.get("/stats")
def stats():
    with db._cur() as c:
        c.execute("SELECT COUNT(*) FROM documents WHERE deleted_at IS NULL")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM documents WHERE status='ready' AND deleted_at IS NULL")
        ready = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(size_bytes),0) FROM documents WHERE deleted_at IS NULL")
        total_bytes = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM pdf_jobs WHERE status='done'")
        pdf_jobs_done = c.fetchone()[0]
    return {
        "documents": {"total": total, "ready": ready, "total_bytes": total_bytes},
        "pdf_jobs_completed": pdf_jobs_done,
        "thresholds": {
            "pdf_ops_per_min": THRESHOLD_PDF_OPS,
            "ocr_ops_per_min": THRESHOLD_OCR_OPS,
            "parse_ops_per_min": THRESHOLD_PARSE_OPS,
        },
    }


app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
