"""
Trancendos email-service — Self-Hosted Worker
=============================================
SMTP outbox queue with SQLite persistence. Emails are queued, then a
background loop drains them via configurable SMTP relay. Falls back to
logging provider (zero-cost, no SMTP needed in dev/test).

Port: 8018
Zero-cost: FastAPI + SQLite + smtplib (stdlib), no external deps.
"""

from __future__ import annotations

import asyncio
import email.mime.multipart
import email.mime.text
import json
import logging
import os
import smtplib
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import formataddr
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = 8018
WORKER_NAME = "email-service"
DB_PATH = Path(__file__).parent / "data" / "email.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@trancendos.com")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Trancendos")
DRAIN_INTERVAL = int(os.getenv("EMAIL_DRAIN_INTERVAL", "10"))
MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS outbox (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                to_addr     TEXT NOT NULL,
                cc_addr     TEXT,
                subject     TEXT NOT NULL,
                body_text   TEXT,
                body_html   TEXT,
                headers     TEXT DEFAULT '{}',
                status      TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER NOT NULL DEFAULT 0,
                error       TEXT,
                queued_at   REAL NOT NULL,
                sent_at     REAL
            );
            CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status, queued_at);

            CREATE TABLE IF NOT EXISTS templates (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                subject     TEXT NOT NULL,
                body_text   TEXT,
                body_html   TEXT,
                created_at  REAL NOT NULL
            );
        """)
        conn.commit()


def _send_smtp(
    to: str,
    cc: Optional[str],
    subject: str,
    body_text: Optional[str],
    body_html: Optional[str],
    extra_headers: dict,
) -> None:
    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    for k, v in extra_headers.items():
        msg[k] = v
    if body_text:
        msg.attach(email.mime.text.MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(email.mime.text.MIMEText(body_html, "html"))
    recipients = [to] + ([cc] if cc else [])
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, recipients, msg.as_string())


async def _drain_outbox() -> None:
    while True:
        await asyncio.sleep(DRAIN_INTERVAL)
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM outbox WHERE status='pending' AND retry_count < ? ORDER BY queued_at LIMIT 20",
                (MAX_RETRIES,),
            ).fetchall()
        for row in rows:
            row = dict(row)
            if not SMTP_HOST:
                # logging provider — mark sent without actually sending
                logger.info(
                    "EMAIL [log] to=%s subject=%s body_preview=%s",
                    row["to_addr"],
                    row["subject"],
                    (row["body_text"] or "")[:80],
                )
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE outbox SET status='sent', sent_at=? WHERE id=?",
                        (time.time(), row["id"]),
                    )
                    conn.commit()
                continue
            try:
                extra = json.loads(row["headers"] or "{}")
                _send_smtp(
                    row["to_addr"],
                    row["cc_addr"],
                    row["subject"],
                    row["body_text"],
                    row["body_html"],
                    extra,
                )
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE outbox SET status='sent', sent_at=? WHERE id=?",
                        (time.time(), row["id"]),
                    )
                    conn.commit()
            except Exception as exc:
                retry = row["retry_count"] + 1
                status = "failed" if retry >= MAX_RETRIES else "pending"
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE outbox SET status=?, retry_count=?, error=? WHERE id=?",
                        (status, retry, str(exc), row["id"]),
                    )
                    conn.commit()
                logger.warning("Email %d send error: %s", row["id"], exc)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SendIn(BaseModel):
    to: str
    cc: Optional[str] = None
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    headers: Dict[str, str] = {}


class BatchSendIn(BaseModel):
    emails: List[SendIn]


class TemplateCreate(BaseModel):
    id: str
    name: str
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None


class TemplateRender(BaseModel):
    to: str
    cc: Optional[str] = None
    variables: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("email-service DB ready (SMTP: %s)", SMTP_HOST or "log-only mode")
    task = asyncio.create_task(_drain_outbox())
    yield
    task.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="email-service",
    description="SMTP outbox queue (self-hosted)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    with get_conn() as conn:
        pending = conn.execute("SELECT COUNT(*) FROM outbox WHERE status='pending'").fetchone()[0]
        sent = conn.execute("SELECT COUNT(*) FROM outbox WHERE status='sent'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM outbox WHERE status='failed'").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "smtp_configured": bool(SMTP_HOST),
        "pending": pending,
        "sent": sent,
        "failed": failed,
        "entity": {
            "location": "Arcadia",
            "pillar": "Commercial / Financial",
            "lead_ai": "Lilli SC",
            "primes": ["Dorris Fontaine"],
            "primary_function": "Post-Login User Frontend, Forum & Email Hub",
            "layer": "supporting",
        },
    }


@app.post("/send", status_code=202)
async def send_email(req: SendIn):
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO outbox (to_addr, cc_addr, subject, body_text, body_html, headers, queued_at) VALUES (?,?,?,?,?,?,?)",
            (
                req.to,
                req.cc,
                req.subject,
                req.body_text,
                req.body_html,
                json.dumps(req.headers),
                now,
            ),
        )
        conn.commit()
    return {"id": cur.lastrowid, "status": "queued", "to": req.to}


@app.post("/send/batch", status_code=202)
async def send_batch(req: BatchSendIn):
    now = time.time()
    rows = [
        (e.to, e.cc, e.subject, e.body_text, e.body_html, json.dumps(e.headers), now)
        for e in req.emails
    ]
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO outbox (to_addr, cc_addr, subject, body_text, body_html, headers, queued_at) VALUES (?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
    return {"queued": len(rows)}


@app.get("/outbox")
async def list_outbox(
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
):
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM outbox {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT id, to_addr, subject, status, retry_count, queued_at, sent_at, error FROM outbox {where} ORDER BY queued_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "emails": [dict(r) for r in rows]}


@app.post("/outbox/{email_id}/retry")
async def retry_email(email_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT id, status FROM outbox WHERE id = ?", (email_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Email not found")
        conn.execute(
            "UPDATE outbox SET status='pending', retry_count=0, error=NULL WHERE id=?", (email_id,)
        )
        conn.commit()
    return {"retrying": email_id}


# --- Templates ---


@app.post("/templates", status_code=201)
async def create_template(req: TemplateCreate):
    with get_conn() as conn:
        if conn.execute("SELECT id FROM templates WHERE id = ?", (req.id,)).fetchone():
            raise HTTPException(status_code=409, detail="Template already exists")
        conn.execute(
            "INSERT INTO templates (id, name, subject, body_text, body_html, created_at) VALUES (?,?,?,?,?,?)",
            (req.id, req.name, req.subject, req.body_text, req.body_html, time.time()),
        )
        conn.commit()
    return {"id": req.id, "name": req.name}


@app.get("/templates")
async def list_templates():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, subject, created_at FROM templates ORDER BY name"
        ).fetchall()
    return {"templates": [dict(r) for r in rows]}


@app.post("/templates/{template_id}/send", status_code=202)
async def send_template(template_id: str, req: TemplateRender):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")

    def _render(text: Optional[str]) -> Optional[str]:
        if not text:
            return text
        for k, v in req.variables.items():
            text = text.replace(f"{{{{{k}}}}}", str(v))
        return text

    subject = _render(row["subject"]) or ""
    body_text = _render(row["body_text"])
    body_html = _render(row["body_html"])
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO outbox (to_addr, cc_addr, subject, body_text, body_html, headers, queued_at) VALUES (?,?,?,?,?,?,?)",
            (req.to, req.cc, subject, body_text, body_html, "{}", now),
        )
        conn.commit()
    return {"id": cur.lastrowid, "status": "queued", "to": req.to, "template": template_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
