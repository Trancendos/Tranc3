"""
Trancendos Notifications Service — Self-Hosted Worker
=====================================================
Replaces CF trancendos-notifications-service.
Multi-channel notification dispatch with templates, preferences, and rate limiting.

Port: 8008
Maps to: Notifications / messaging
Zero-cost: In-process dispatch, SQLite storage, no external SaaS.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from Dimensional.error_handlers import safe_error_detail
from Dimensional.sanitize import sanitize_for_log
from Dimensional.url_validation import SSRFError, validate_webhook_url

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8008
WORKER_NAME = "notifications-service"
DB_PATH = Path(__file__).parent / "data" / "notifications.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Webhook domain allowlist — comma-separated domains from WEBHOOK_ALLOWED_DOMAINS env var.
# If set, only these domains may receive webhook notifications.
# If empty/unset, all domains passing SSRF validation are permitted.
_WEBHOOK_ALLOWED_DOMAINS: Set[str] = {
    d.strip().lower() for d in os.environ.get("WEBHOOK_ALLOWED_DOMAINS", "").split(",") if d.strip()
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class NotificationChannel(str, Enum):
    email = "email"
    sms = "sms"
    push = "push"
    webhook = "webhook"
    in_app = "in_app"


class NotificationPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class NotificationStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    rate_limited = "rate_limited"


class NotificationRequest(BaseModel):
    notification_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    channel: NotificationChannel
    priority: NotificationPriority = NotificationPriority.normal
    subject: str = ""
    body: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    template_id: Optional[str] = None
    template_vars: Dict[str, str] = Field(default_factory=dict)


class NotificationTemplate(BaseModel):
    template_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    channel: NotificationChannel
    subject_template: str = ""
    body_template: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UserPreferences(BaseModel):
    user_id: str
    channels_enabled: List[NotificationChannel] = Field(
        default_factory=lambda: [NotificationChannel.in_app, NotificationChannel.email]
    )
    quiet_hours_start: Optional[str] = None  # HH:MM format
    quiet_hours_end: Optional[str] = None
    max_per_hour: int = 20
    max_per_day: int = 100


# ---------------------------------------------------------------------------
# Rate Limiter (in-memory, zero-cost)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token-bucket rate limiter per user+channel."""

    def __init__(self):
        self._buckets: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str, max_per_hour: int = 20, max_per_day: int = 100) -> bool:
        now = time.time()
        hour_ago = now - 3600
        day_ago = now - 86400
        with self._lock:
            # Clean old entries
            self._buckets[key] = [t for t in self._buckets[key] if t > day_ago]
            hourly = sum(1 for t in self._buckets[key] if t > hour_ago)
            daily = len(self._buckets[key])
            if hourly >= max_per_hour or daily >= max_per_day:
                return False
            self._buckets[key].append(now)
            return True


import time  # noqa: E402 (needed for RateLimiter)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class NotificationsDatabase:
    """SQLite-backed storage for notifications, templates, and preferences."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        with self._cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    notification_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    priority TEXT NOT NULL DEFAULT 'normal',
                    subject TEXT DEFAULT '',
                    body TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    metadata TEXT DEFAULT '{}',
                    template_id TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT,
                    delivered_at TEXT,
                    error_message TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    template_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    subject_template TEXT DEFAULT '',
                    body_template TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    channels_enabled TEXT DEFAULT '["in_app","email"]',
                    quiet_hours_start TEXT,
                    quiet_hours_end TEXT,
                    max_per_hour INTEGER DEFAULT 20,
                    max_per_day INTEGER DEFAULT 100
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notif_status ON notifications(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notif_created ON notifications(created_at)")

    # -- Notifications --

    def create_notification(
        self, notif: NotificationRequest, status: NotificationStatus = NotificationStatus.pending
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO notifications (notification_id, user_id, channel, priority, subject, body, status, metadata, template_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    notif.notification_id,
                    notif.user_id,
                    notif.channel.value,
                    notif.priority.value,
                    notif.subject,
                    notif.body,
                    status.value,
                    json.dumps(notif.metadata),
                    notif.template_id,
                    now,
                ),
            )
        return {"notification_id": notif.notification_id, "status": status.value}

    def update_status(
        self, notification_id: str, status: NotificationStatus, error: Optional[str] = None
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._cursor() as cur:
            if status == NotificationStatus.sent:
                cur.execute(
                    "UPDATE notifications SET status=?, sent_at=? WHERE notification_id=?",
                    (status.value, now, notification_id),
                )
            elif status == NotificationStatus.delivered:
                cur.execute(
                    "UPDATE notifications SET status=?, delivered_at=? WHERE notification_id=?",
                    (status.value, now, notification_id),
                )
            elif status == NotificationStatus.failed:
                cur.execute(
                    "UPDATE notifications SET status=?, error_message=? WHERE notification_id=?",
                    (status.value, error or "", notification_id),
                )
            else:
                cur.execute(
                    "UPDATE notifications SET status=? WHERE notification_id=?",
                    (status.value, notification_id),
                )

    def get_notification(self, notification_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM notifications WHERE notification_id=?", (notification_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_notifications(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = "SELECT * FROM notifications WHERE 1=1"
        params: list = []
        if user_id:
            query += " AND user_id=?"
            params.append(user_id)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    # -- Templates --

    def create_template(self, template: NotificationTemplate) -> NotificationTemplate:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO templates (template_id, name, channel, subject_template, body_template, metadata) VALUES (?,?,?,?,?,?)",
                (
                    template.template_id,
                    template.name,
                    template.channel.value,
                    template.subject_template,
                    template.body_template,
                    json.dumps(template.metadata),
                ),
            )
        return template

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM templates WHERE template_id=?", (template_id,)).fetchone()
        return dict(row) if row else None

    def list_templates(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if channel:
            rows = conn.execute(
                "SELECT * FROM templates WHERE channel=? ORDER BY name", (channel,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM templates ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def delete_template(self, template_id: str) -> bool:
        with self._cursor() as cur:
            cur.execute("DELETE FROM templates WHERE template_id=?", (template_id,))
            return cur.rowcount > 0

    # -- Preferences --

    def set_preferences(self, prefs: UserPreferences) -> UserPreferences:
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO user_preferences (user_id, channels_enabled, quiet_hours_start, quiet_hours_end, max_per_hour, max_per_day) VALUES (?,?,?,?,?,?)",
                (
                    prefs.user_id,
                    json.dumps([c.value for c in prefs.channels_enabled]),
                    prefs.quiet_hours_start,
                    prefs.quiet_hours_end,
                    prefs.max_per_hour,
                    prefs.max_per_day,
                ),
            )
        return prefs

    def get_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM user_preferences WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Notification Dispatchers (zero-cost — in-process)
# ---------------------------------------------------------------------------


class NotificationDispatcher:
    """Dispatches notifications through various channels. In production, plug in real providers."""

    @staticmethod
    async def dispatch_email(
        user_id: str, subject: str, body: str, metadata: Dict[str, Any]
    ) -> bool:
        """Email dispatch — in zero-cost mode, logs and marks as sent. Plug in SMTP or SES later."""
        logger.info(
            "📧 EMAIL → user=%s subject='%s'", sanitize_for_log(user_id), sanitize_for_log(subject)
        )  # codeql[py/cleartext-logging]
        # In production: integrate with self-hosted mail or free-tier SMTP
        return True

    @staticmethod
    async def dispatch_sms(user_id: str, body: str, metadata: Dict[str, Any]) -> bool:
        """SMS dispatch — zero-cost mode logs only. Plug in Twilio free tier later."""
        logger.info("📱 SMS → user=%s", sanitize_for_log(user_id))  # codeql[py/cleartext-logging]
        return True

    @staticmethod
    async def dispatch_push(
        user_id: str, subject: str, body: str, metadata: Dict[str, Any]
    ) -> bool:
        """Push notification — zero-cost mode logs only. Plug in Web Push later."""
        logger.info(
            "🔔 PUSH → user=%s subject='%s'", sanitize_for_log(user_id), sanitize_for_log(subject)
        )  # codeql[py/cleartext-logging]
        return True

    @staticmethod
    async def dispatch_webhook(url: str, payload: Dict[str, Any]) -> bool:
        """Webhook dispatch — makes HTTP POST to a validated URL.

        WEBHOOK_ALLOWED_DOMAINS (env var) must be configured.  The connection
        host is derived from the allowlist (config-sourced), not from the
        user-supplied URL, so the outbound host is not attacker-controlled.
        """
        import http.client
        from urllib.parse import quote, urlparse

        # SSRF validation — blocks private IPs, metadata endpoints, non-HTTPS
        try:
            validated_url = validate_webhook_url(url)
        except SSRFError as e:
            logger.warning("Webhook URL blocked by SSRF protection: %s", e)
            return False

        # Allowlist is required for webhook dispatch.  The connection host is
        # taken from _WEBHOOK_ALLOWED_DOMAINS (populated from env config at
        # startup), NOT from the user-supplied URL.  Iterating the config set
        # and comparing yields the config-sourced string as the host value,
        # which is not tainted by user input.
        if not _WEBHOOK_ALLOWED_DOMAINS:
            logger.warning("Webhook dispatch blocked: WEBHOOK_ALLOWED_DOMAINS not configured")
            return False

        _p = urlparse(validated_url)
        _req_host = (_p.hostname or "").lower()
        _conn_host: Optional[str] = next(
            (d for d in _WEBHOOK_ALLOWED_DOMAINS if d == _req_host), None
        )
        if _conn_host is None:
            logger.warning(
                "Webhook domain '%s' not in allowlist (%d configured)",
                sanitize_for_log(_req_host),
                len(_WEBHOOK_ALLOWED_DOMAINS),
            )
            return False

        try:
            data = json.dumps(payload).encode()
            import urllib.parse
            _decoded = urllib.parse.unquote(_p.path or "/")
            if ".." in _decoded.split("/"):
                logger.warning("Webhook dispatch blocked: path traversal in URL path")
                return False
            _safe_path = quote(_p.path or "/", safe="/-_.~")
            if _p.query and not all(c.isalnum() or c in "=._-&%[]@" for c in _p.query):
                logger.warning("Webhook dispatch blocked: suspicious query characters")
                return False
            _safe_path += _p.query or ""
            _conn = http.client.HTTPSConnection(_conn_host, 443, timeout=10)
            _conn.request(
                "POST",
                _safe_path,
                body=data,
                headers={"Content-Type": "application/json"},
            )
            _resp = _conn.getresponse()
            _conn.close()
            return _resp.status < 400
        except Exception as e:
            logger.error("Webhook dispatch failed: %s", e)
            return False

    @staticmethod
    async def dispatch_in_app(
        user_id: str, subject: str, body: str, metadata: Dict[str, Any]
    ) -> bool:
        """In-app notification — stored in DB, client polls or uses WebSocket."""
        logger.info(
            "💬 IN-APP → user=%s subject='%s'", sanitize_for_log(user_id), sanitize_for_log(subject)
        )  # codeql[py/cleartext-logging]
        return True


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

db = NotificationsDatabase(DB_PATH)
rate_limiter = RateLimiter()
dispatcher = NotificationDispatcher()

app = FastAPI(
    title="Notifications Service",
    description="Self-hosted multi-channel notification dispatch. Replaces CF trancendos-notifications-service.",
    version="1.0.0",
)

# OpenTelemetry instrumentation
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    from src.observability.otel import init_otel

    init_otel(service_name="tranc3.notifications")
    FastAPIInstrumentor.instrument_app(app)
except Exception:
    pass  # OTel is optional — never block startup

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STARTED_AT = datetime.now(timezone.utc)

# ---------------------------------------------------------------------------
# Internal auth
# ---------------------------------------------------------------------------

_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return  # unconfigured in test/dev — allow through
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "entity": {
            "location": "Arcadia",
            "pillar": "Commercial / Financial",
            "lead_ai": "Lilli SC",
            "primes": ["Dorris Fontaine"],
            "primary_function": "Post-Login User Frontend, Forum & Email Hub",
            "layer": "supporting",
        },
    }


# ---------------------------------------------------------------------------
# Send Notification
# ---------------------------------------------------------------------------


@_router.post("/notifications/send")
async def send_notification(req: NotificationRequest):
    """Send a notification through the specified channel."""
    # Check user preferences
    prefs_data = db.get_preferences(req.user_id)
    max_hour = 20
    max_day = 100
    if prefs_data:
        max_hour = prefs_data.get("max_per_hour", 20)
        max_day = prefs_data.get("max_per_day", 100)
        enabled_channels = json.loads(prefs_data.get("channels_enabled", '["in_app","email"]'))
        if req.channel.value not in enabled_channels:
            return {"ok": False, "reason": f"Channel {req.channel.value} disabled for user"}

    # Rate limit check
    rate_key = f"{req.user_id}:{req.channel.value}"
    if not rate_limiter.check(rate_key, max_per_hour=max_hour, max_per_day=max_day):
        db.create_notification(req, status=NotificationStatus.rate_limited)
        return {
            "ok": False,
            "reason": "Rate limit exceeded",
            "notification_id": req.notification_id,
        }

    # Apply template if specified
    if req.template_id:
        template = db.get_template(req.template_id)
        if template:
            subject = template["subject_template"]
            body = template["body_template"]
            for key, val in req.template_vars.items():
                subject = subject.replace(f"{{{{{key}}}}}", val)
                body = body.replace(f"{{{{{key}}}}}", val)
            req.subject = subject or req.subject
            req.body = body

    # Store notification
    db.create_notification(req, status=NotificationStatus.pending)

    # Dispatch
    success = False
    try:
        if req.channel == NotificationChannel.email:
            success = await dispatcher.dispatch_email(
                req.user_id, req.subject, req.body, req.metadata
            )
        elif req.channel == NotificationChannel.sms:
            success = await dispatcher.dispatch_sms(req.user_id, req.body, req.metadata)
        elif req.channel == NotificationChannel.push:
            success = await dispatcher.dispatch_push(
                req.user_id, req.subject, req.body, req.metadata
            )
        elif req.channel == NotificationChannel.webhook:
            webhook_url = req.metadata.get("webhook_url", "")
            if not webhook_url:
                return {"ok": False, "reason": "webhook_url missing from metadata"}
            # Validate webhook URL at the endpoint level (defense-in-depth)
            try:
                validate_webhook_url(webhook_url)
            except SSRFError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Webhook URL rejected: {e}",
                ) from None
            success = await dispatcher.dispatch_webhook(
                webhook_url,
                {
                    "subject": req.subject,
                    "body": req.body,
                    "metadata": req.metadata,
                },
            )
        elif req.channel == NotificationChannel.in_app:
            success = await dispatcher.dispatch_in_app(
                req.user_id, req.subject, req.body, req.metadata
            )

        if success:
            db.update_status(req.notification_id, NotificationStatus.sent)
            return {"ok": True, "notification_id": req.notification_id, "status": "sent"}
        else:
            db.update_status(
                req.notification_id, NotificationStatus.failed, error="Dispatch failed"
            )
            return {"ok": False, "notification_id": req.notification_id, "status": "failed"}

    except Exception as e:
        db.update_status(
            req.notification_id,
            NotificationStatus.failed,
            error=safe_error_detail(e, 500),
        )
        logger.error("Notification dispatch error: %s", e)
        return {
            "ok": False,
            "notification_id": req.notification_id,
            "status": "failed",
            "error": safe_error_detail(e, 500),
        }


# ---------------------------------------------------------------------------
# List / Get Notifications
# ---------------------------------------------------------------------------


@_router.get("/notifications")
async def list_notifications(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List notifications with optional filtering."""
    return {
        "notifications": db.list_notifications(
            user_id=user_id, status=status, limit=limit, offset=offset
        )
    }


@_router.get("/notifications/{notification_id}")
async def get_notification(notification_id: str):
    """Get a specific notification by ID."""
    notif = db.get_notification(notification_id)
    if not notif:
        raise HTTPException(404, f"Notification not found: {notification_id}")
    return notif


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@_router.post("/templates")
async def create_template(template: NotificationTemplate):
    """Create a notification template."""
    created = db.create_template(template)
    return {"ok": True, "template_id": created.template_id}


@_router.get("/templates")
async def list_templates(channel: Optional[str] = None):
    """List notification templates."""
    return {"templates": db.list_templates(channel=channel)}


@_router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """Get a specific template."""
    template = db.get_template(template_id)
    if not template:
        raise HTTPException(404, f"Template not found: {template_id}")
    return template


@_router.delete("/templates/{template_id}")
async def delete_template(template_id: str):
    """Delete a notification template."""
    if not db.delete_template(template_id):
        raise HTTPException(404, f"Template not found: {template_id}")
    return {"ok": True, "deleted": template_id}


# ---------------------------------------------------------------------------
# User Preferences
# ---------------------------------------------------------------------------


@_router.get("/preferences/{user_id}")
async def get_preferences(user_id: str):
    """Get notification preferences for a user."""
    prefs = db.get_preferences(user_id)
    if not prefs:
        # Return defaults
        return UserPreferences(user_id=user_id).model_dump()
    return prefs


@_router.put("/preferences/{user_id}")
async def set_preferences(user_id: str, prefs: UserPreferences):
    """Set notification preferences for a user."""
    prefs.user_id = user_id
    db.set_preferences(prefs)
    return {"ok": True, "user_id": user_id}


app.include_router(_router)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
