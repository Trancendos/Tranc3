"""
Trancendos Users Service — Self-Hosted Worker
================================================
Replaces CF trancendos-users-service.
Full user management API with SQLite storage.

Maps to: Infinity / user management
Port: 8006
Zero-cost: FastAPI + SQLite, no external dependencies.

Features:
- User CRUD (create, read, update, soft-delete)
- Avatar URL, bio, timezone management
- Role-based access (user/admin/moderator)
- User search (username, email, display_name)
- Account lock/unlock
- Password-reset token stub
- Bulk deactivate (admin)
- Last-login timestamp tracking
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import sqlite3
from src.database.encrypted_sqlite import connect as sqlite3_connect, encrypt_field, decrypt_field
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from shared_core.sanitize import sanitize_for_log
from src.entities.health_metadata import health_entity_block

logger = logging.getLogger("tranc3.workers.users-service")

DATABASE_PATH = os.environ.get("USERS_DATABASE_PATH", "/data/users.db")
NOTIFICATIONS_URL = os.environ.get("NOTIFICATIONS_SERVICE_URL", "http://localhost:8008")

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    display_name: str = Field(default="", max_length=100)
    role: str = Field(default="user", pattern=r"^(user|admin|moderator)$")
    preferences: dict = Field(default_factory=dict)
    bio: str = Field(default="", max_length=500)
    avatar_url: str = Field(default="", max_length=512)
    timezone: str = Field(default="UTC", max_length=64)


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    preferences: Optional[dict] = None
    is_active: Optional[bool] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None


class UserResponse(BaseModel):
    user_id: str
    username: str
    email: str
    display_name: str
    role: str
    preferences: dict
    is_active: bool
    is_locked: bool = False
    bio: str = ""
    avatar_url: str = ""
    timezone: str = "UTC"
    last_login: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    per_page: int


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetResponse(BaseModel):
    message: str
    reset_token: str  # stub — never sent externally in this service


class BulkDeactivateRequest(BaseModel):
    user_ids: List[str]


class RoleUpdateRequest(BaseModel):
    role: str = Field(pattern=r"^(user|admin|moderator)$")


class ConsentUpdate(BaseModel):
    """GDPR Art. 6/7 — explicit, granular consent flags."""
    analytics: Optional[bool] = None
    marketing_email: Optional[bool] = None
    marketing_sms: Optional[bool] = None
    data_sharing: Optional[bool] = None
    personalisation: Optional[bool] = None
    extra: Optional[dict] = Field(default=None)


class ConsentRecord(BaseModel):
    user_id: str
    analytics: bool = False
    marketing_email: bool = False
    marketing_sms: bool = False
    data_sharing: bool = False
    personalisation: bool = False
    extra: dict = Field(default_factory=dict)
    consented_at: Optional[str] = None
    updated_at: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class UsersDatabase:
    # Columns encrypted with AES-GCM at rest (not used in WHERE/INDEX)
    _ENCRYPTED_COLUMNS = {"bio", "avatar_url", "preferences", "display_name"}

    def __init__(self, db_path: str = DATABASE_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3_connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS consent (
                user_id          TEXT PRIMARY KEY,
                analytics        INTEGER DEFAULT 0,
                marketing_email  INTEGER DEFAULT 0,
                marketing_sms    INTEGER DEFAULT 0,
                data_sharing     INTEGER DEFAULT 0,
                personalisation  INTEGER DEFAULT 0,
                extra            TEXT DEFAULT '{}',
                consented_at     TEXT,
                updated_at       TEXT,
                ip_address       TEXT,
                user_agent       TEXT
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id       TEXT PRIMARY KEY,
                username      TEXT UNIQUE NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                display_name  TEXT DEFAULT '',
                role          TEXT DEFAULT 'user',
                preferences   TEXT DEFAULT '{}',
                bio           TEXT DEFAULT '',
                avatar_url    TEXT DEFAULT '',
                timezone      TEXT DEFAULT 'UTC',
                is_active     INTEGER DEFAULT 1,
                is_locked     INTEGER DEFAULT 0,
                last_login    TEXT,
                created_at    TEXT NOT NULL,
                updated_at    TEXT
            );
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token      TEXT PRIMARY KEY,
                user_id    TEXT NOT NULL,
                email      TEXT NOT NULL,
                created_at TEXT NOT NULL,
                used       INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_users_email    ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_role     ON users(role);
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        """)
        self._conn.commit()

    def _enc(self, column: str, value: Any) -> Any:
        if column in self._ENCRYPTED_COLUMNS:
            return encrypt_field(self.db_path, value)
        return value

    def _dec_row(self, row: sqlite3.Row) -> sqlite3.Row:
        """Return a plain dict with encrypted columns decrypted."""
        d = dict(row)
        for col in self._ENCRYPTED_COLUMNS:
            if col in d and d[col] is not None:
                d[col] = decrypt_field(self.db_path, d[col])
        return d

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()


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


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Trancendos Users Service", version="2.0.0")

from src.observability.prometheus_mount import mount_prometheus_endpoint

mount_prometheus_endpoint(app, "users-service")

_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
db = UsersDatabase()

# Shared async HTTP client — created once at startup, closed at shutdown.
_http_client: httpx.AsyncClient | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _http_client
    _http_client = httpx.AsyncClient(timeout=5.0)


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _http_client:
        await _http_client.aclose()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _row_to_response(row) -> UserResponse:
    d = db._dec_row(row) if isinstance(row, sqlite3.Row) else row
    prefs = d.get("preferences") or "{}"
    if isinstance(prefs, str):
        try:
            prefs = json.loads(prefs)
        except Exception:
            prefs = {}
    return UserResponse(
        user_id=d["user_id"],
        username=d["username"],
        email=d["email"],
        display_name=d.get("display_name") or "",
        role=d["role"],
        preferences=prefs,
        is_active=bool(d["is_active"]),
        is_locked=bool(d["is_locked"]),
        bio=d.get("bio") or "",
        avatar_url=d.get("avatar_url") or "",
        timezone=d.get("timezone") or "UTC",
        last_login=d.get("last_login"),
        created_at=d["created_at"],
        updated_at=d.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# All non-health routes require internal authentication
_router = APIRouter(dependencies=[Depends(require_internal_auth)])


@app.get("/health")
async def health():
    count = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    active = db.execute("SELECT COUNT(*) as c FROM users WHERE is_active = 1").fetchone()["c"]
    return {
        "status": "healthy",
        "service": "users-service",
        "port": 8006,
        "user_count": count,
        "active_count": active,
        "entity": health_entity_block(8006, "users-service"),
    }


@_router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate):
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    prefs_json = json.dumps(user.preferences)
    try:
        db.execute(
            """INSERT INTO users
               (user_id, username, email, display_name, role, preferences,
                bio, avatar_url, timezone, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                user.username,
                user.email,
                db._enc("display_name", user.display_name),
                user.role,
                db._enc("preferences", prefs_json),
                db._enc("bio", user.bio),
                db._enc("avatar_url", user.avatar_url),
                user.timezone,
                now,
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username or email already exists") from None
    return UserResponse(
        user_id=user_id,
        username=user.username,
        email=str(user.email),
        display_name=user.display_name,
        role=user.role,
        preferences=user.preferences,
        is_active=True,
        is_locked=False,
        bio=user.bio,
        avatar_url=user.avatar_url,
        timezone=user.timezone,
        last_login=None,
        created_at=now,
    )


@_router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return _row_to_response(row)


@_router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    role: Optional[str] = Query(default=None),
    active_only: bool = Query(default=False),
):
    offset = (page - 1) * per_page
    conditions = []
    params: list = []
    if role:
        conditions.append("role = ?")
        params.append(role)
    if active_only:
        conditions.append("is_active = 1")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    total = db.execute(f"SELECT COUNT(*) as c FROM users {where}", tuple(params)).fetchone()["c"]
    rows = db.execute(
        f"SELECT * FROM users {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        tuple(params) + (per_page, offset),
    ).fetchall()
    return UserListResponse(
        users=[_row_to_response(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@_router.get("/users/search/query", response_model=UserListResponse)
async def search_users(
    q: str = Query(min_length=1),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
):
    """Full-text search across username, email, display_name."""
    offset = (page - 1) * per_page
    pattern = f"%{q}%"
    total = db.execute(
        "SELECT COUNT(*) as c FROM users WHERE username LIKE ? OR email LIKE ? OR display_name LIKE ?",
        (pattern, pattern, pattern),
    ).fetchone()["c"]
    rows = db.execute(
        "SELECT * FROM users WHERE username LIKE ? OR email LIKE ? OR display_name LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (pattern, pattern, pattern, per_page, offset),
    ).fetchall()
    return UserListResponse(
        users=[_row_to_response(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@_router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, update: UserUpdate):
    existing = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    updates: dict = {}
    if update.display_name is not None:
        updates["display_name"] = db._enc("display_name", update.display_name)
    if update.email is not None:
        updates["email"] = str(update.email)
    if update.role is not None:
        updates["role"] = update.role
    if update.preferences is not None:
        updates["preferences"] = db._enc("preferences", json.dumps(update.preferences))
    if update.is_active is not None:
        updates["is_active"] = 1 if update.is_active else 0
    if update.bio is not None:
        updates["bio"] = db._enc("bio", update.bio)
    if update.avatar_url is not None:
        updates["avatar_url"] = db._enc("avatar_url", update.avatar_url)
    if update.timezone is not None:
        updates["timezone"] = update.timezone
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    db.execute(
        f"UPDATE users SET {set_clause} WHERE user_id = ?",
        (*updates.values(), user_id),
    )
    db.commit()

    row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_response(row)


@_router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    result = db.execute(
        "UPDATE users SET is_active = 0, updated_at = ? WHERE user_id = ?",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deactivated"}


@_router.post("/users/{user_id}/lock")
async def lock_user(user_id: str):
    """Lock a user account (prevents login)."""
    result = db.execute(
        "UPDATE users SET is_locked = 1, updated_at = ? WHERE user_id = ?",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User account locked", "user_id": user_id}


@_router.post("/users/{user_id}/unlock")
async def unlock_user(user_id: str):
    """Unlock a user account."""
    result = db.execute(
        "UPDATE users SET is_locked = 0, updated_at = ? WHERE user_id = ?",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User account unlocked", "user_id": user_id}


@_router.post("/users/{user_id}/login")
async def record_login(user_id: str):
    """Record a successful login timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    result = db.execute(
        "UPDATE users SET last_login = ?, updated_at = ? WHERE user_id = ? AND is_active = 1 AND is_locked = 0",
        (now, now, user_id),
    )
    db.commit()
    if result.rowcount == 0:
        row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        if not row["is_active"]:
            raise HTTPException(status_code=403, detail="Account deactivated")
        raise HTTPException(status_code=403, detail="Account locked")
    return {"message": "Login recorded", "last_login": now}


@_router.patch("/users/{user_id}/role", response_model=UserResponse)
async def update_role(user_id: str, body: RoleUpdateRequest):
    """Update user role (admin operation)."""
    existing = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE users SET role = ?, updated_at = ? WHERE user_id = ?",
        (body.role, now, user_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_response(row)


async def _dispatch_reset_email(user_id: str, email: str, token: str) -> None:
    """Fire-and-forget: ask notifications-service to send the password-reset email."""
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    reset_link = f"{frontend_url}/reset-password?token={token}"
    payload = {
        "user_id": user_id,
        "channel": "email",
        "priority": "high",
        "subject": "Reset your Trancendos password",
        "body": (
            f"You requested a password reset.\n\n"
            f"Click the link below to choose a new password (expires in 1 hour):\n\n"
            f"{reset_link}\n\n"
            f"If you did not request this, you can safely ignore this email."
        ),
        "metadata": {"user_id": user_id},
    }
    try:
        if _http_client is not None:
            resp = await _http_client.post(f"{NOTIFICATIONS_URL}/notifications/send", json=payload)
        else:
            async with httpx.AsyncClient(timeout=5.0) as _fallback:
                resp = await _fallback.post(f"{NOTIFICATIONS_URL}/notifications/send", json=payload)
        if resp.status_code not in (200, 201):
            logger.warning(
                "notifications-service returned %s for reset email user=%s",
                resp.status_code, sanitize_for_log(user_id),
            )
    except Exception:
        logger.exception("Failed to dispatch reset email for user=%s", sanitize_for_log(user_id))


@_router.post("/users/password-reset/request", response_model=PasswordResetResponse)
async def request_password_reset(body: PasswordResetRequest, background_tasks: BackgroundTasks):
    """Generate a password-reset token and dispatch a reset email via notifications-service."""
    row = db.execute(
        "SELECT * FROM users WHERE email = ? AND is_active = 1",
        (str(body.email),),
    ).fetchone()
    if not row:
        # Don't leak user existence — respond identically for unknown emails
        return PasswordResetResponse(
            message="If that email is registered, a reset link has been sent.",
            reset_token="",
        )
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO password_reset_tokens (token, user_id, email, created_at) VALUES (?, ?, ?, ?)",
        (token, row["user_id"], str(body.email), now),
    )
    db.commit()
    background_tasks.add_task(_dispatch_reset_email, row["user_id"], str(body.email), token)
    return PasswordResetResponse(
        message="If that email is registered, a reset link has been sent.",
        reset_token="",
    )


@_router.post("/admin/users/bulk-deactivate")
async def bulk_deactivate(body: BulkDeactivateRequest):
    """Deactivate multiple users at once (admin operation)."""
    now = datetime.now(timezone.utc).isoformat()
    deactivated = []
    not_found = []
    for user_id in body.user_ids:
        result = db.execute(
            "UPDATE users SET is_active = 0, updated_at = ? WHERE user_id = ?",
            (now, user_id),
        )
        if result.rowcount:
            deactivated.append(user_id)
        else:
            not_found.append(user_id)
    db.commit()
    return {
        "deactivated": deactivated,
        "not_found": not_found,
        "count": len(deactivated),
    }


@_router.get("/admin/users/roles/summary")
async def roles_summary():
    """Summary count by role."""
    rows = db.execute(
        "SELECT role, COUNT(*) as count FROM users WHERE is_active = 1 GROUP BY role",
    ).fetchall()
    return {"roles": {row["role"]: row["count"] for row in rows}}


# ── GDPR Endpoints (Art. 15/17/20) ───────────────────────────────────────────

_SAR_PII_FIELDS = [
    "user_id", "username", "email", "display_name", "bio", "avatar_url",
    "timezone", "role", "preferences", "created_at", "updated_at", "last_login",
]


@_router.get("/users/{user_id}/data-export")
async def gdpr_data_export(
    user_id: str,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    x_caller_user_id: Optional[str] = Header(default=None),
    x_caller_role: Optional[str] = Header(default=None),
):
    """GDPR Art. 15 & 20 — Subject Access Request data export."""
    if x_caller_user_id != user_id and x_caller_role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    row = db.execute(
        f"SELECT {', '.join(_SAR_PII_FIELDS)} FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    subject = {k: db._dec_row(row).get(k) for k in _SAR_PII_FIELDS}
    subject["preferences"] = json.loads(subject.get("preferences") or "{}")

    consent_row = db.execute("SELECT * FROM consent WHERE user_id = ?", (user_id,)).fetchone()
    subject["consent"] = dict(consent_row) if consent_row else {}

    logger.info(
        "GDPR SAR export: user_id=%s requested_by=%s format=%s",
        sanitize_for_log(user_id),
        sanitize_for_log(x_caller_user_id or "unknown"),
        format,
    )

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=_SAR_PII_FIELDS)
        writer.writeheader()
        # Prefix cells starting with formula characters to prevent CSV injection
        csv_row = {}
        for k, v in subject.items():
            if k == "consent":
                continue
            sv = json.dumps(v) if isinstance(v, (dict, list)) else str(v or "")
            csv_row[k] = ("'" + sv) if sv and sv[0] in ("=", "+", "-", "@", "\t", "\r") else sv
        writer.writerow(csv_row)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="data-export-{user_id}.csv"'},
        )

    return {
        "subject": subject,
        "export_metadata": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "format": "json",
            "gdpr_article": "Art. 15 & 20 GDPR",
            "data_controller": "Trancendos",
        },
    }


@_router.delete("/users/{user_id}/data")
async def gdpr_erase_user(
    user_id: str,
    x_caller_role: Optional[str] = Header(default=None),
):
    """GDPR Art. 17 — Right to erasure (soft-delete PII)."""
    if x_caller_role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")

    row = db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """UPDATE users SET
            username = ?, email = ?, display_name = ?, bio = ?,
            avatar_url = ?, preferences = '{}', is_active = 0,
            updated_at = ?
           WHERE user_id = ?""",
        (
            f"deleted_user_{user_id[:8]}",
            f"deleted_{user_id}@deleted.invalid",  # unique per user — prevents UNIQUE violation
            "",
            "",
            "",
            now,
            user_id,
        ),
    )
    db.commit()
    # Reset consent on erasure
    db.execute(
        """INSERT INTO consent (user_id, analytics, marketing_email, marketing_sms,
                data_sharing, personalisation, extra, updated_at)
           VALUES (?,0,0,0,0,0,'{}',?)
           ON CONFLICT(user_id) DO UPDATE SET
               analytics=0, marketing_email=0, marketing_sms=0,
               data_sharing=0, personalisation=0, updated_at=excluded.updated_at""",
        (user_id, now),
    )
    db.commit()
    logger.info("GDPR Art. 17 erasure: user_id=%s erased_by_admin", sanitize_for_log(user_id))
    return {"deleted": True, "user_id": user_id, "gdpr_article": "Art. 17 GDPR"}


# ── Consent Endpoints (GDPR Art. 6/7) ────────────────────────────────────────


@_router.get("/users/{user_id}/consent", response_model=ConsentRecord)
async def get_consent(user_id: str):
    """Return current GDPR consent flags for a user."""
    user_row = db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")
    row = db.execute("SELECT * FROM consent WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return ConsentRecord(user_id=user_id)
    extra_val = row["extra"]
    try:
        extra_val = json.loads(extra_val) if isinstance(extra_val, str) else (extra_val or {})
    except Exception:
        extra_val = {}
    return ConsentRecord(
        user_id=user_id,
        analytics=bool(row["analytics"]),
        marketing_email=bool(row["marketing_email"]),
        marketing_sms=bool(row["marketing_sms"]),
        data_sharing=bool(row["data_sharing"]),
        personalisation=bool(row["personalisation"]),
        extra=extra_val,
        consented_at=row["consented_at"],
        updated_at=row["updated_at"],
        ip_address=row["ip_address"],
        user_agent=row["user_agent"],
    )


@_router.post("/users/{user_id}/consent", response_model=ConsentRecord)
async def upsert_consent(
    user_id: str,
    body: ConsentUpdate,
    x_forwarded_for: Optional[str] = Header(default=None, alias="X-Forwarded-For"),
    user_agent: Optional[str] = Header(default=None, alias="User-Agent"),
):
    """Set or update GDPR consent flags (merge — existing flags unchanged unless specified)."""
    user_row = db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc).isoformat()
    existing = db.execute("SELECT * FROM consent WHERE user_id = ?", (user_id,)).fetchone()

    if existing:
        updates: dict = {"updated_at": now}
        if body.analytics is not None:
            updates["analytics"] = 1 if body.analytics else 0
        if body.marketing_email is not None:
            updates["marketing_email"] = 1 if body.marketing_email else 0
        if body.marketing_sms is not None:
            updates["marketing_sms"] = 1 if body.marketing_sms else 0
        if body.data_sharing is not None:
            updates["data_sharing"] = 1 if body.data_sharing else 0
        if body.personalisation is not None:
            updates["personalisation"] = 1 if body.personalisation else 0
        if body.extra is not None:
            try:
                old_extra = json.loads(existing["extra"]) if existing["extra"] else {}
            except Exception:
                old_extra = {}
            updates["extra"] = json.dumps({**old_extra, **body.extra})
        if x_forwarded_for:
            updates["ip_address"] = x_forwarded_for.split(",")[0].strip()
        if user_agent:
            updates["user_agent"] = user_agent
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        db.execute(
            f"UPDATE consent SET {set_clause} WHERE user_id = ?",
            (*updates.values(), user_id),
        )
    else:
        db.execute(
            """INSERT INTO consent
               (user_id, analytics, marketing_email, marketing_sms, data_sharing,
                personalisation, extra, consented_at, updated_at, ip_address, user_agent)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id,
                1 if body.analytics else 0,
                1 if body.marketing_email else 0,
                1 if body.marketing_sms else 0,
                1 if body.data_sharing else 0,
                1 if body.personalisation else 0,
                json.dumps(body.extra or {}),
                now,
                now,
                x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None,
                user_agent,
            ),
        )
    db.commit()
    return await get_consent(user_id)


@_router.delete("/users/{user_id}/consent")
async def withdraw_consent(user_id: str):
    """Withdraw all GDPR consent (sets all flags to False, GDPR Art. 7(3))."""
    user_row = db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT INTO consent (user_id, analytics, marketing_email, marketing_sms,
                data_sharing, personalisation, extra, updated_at)
           VALUES (?,0,0,0,0,0,'{}',?)
           ON CONFLICT(user_id) DO UPDATE SET
               analytics=0, marketing_email=0, marketing_sms=0,
               data_sharing=0, personalisation=0, updated_at=excluded.updated_at""",
        (user_id, now),
    )
    db.commit()
    return {"message": "All consent withdrawn", "user_id": user_id, "withdrawn_at": now}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)
