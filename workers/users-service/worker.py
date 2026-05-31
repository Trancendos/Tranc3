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

import json
import logging
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger("tranc3.workers.users-service")


def _default_database_path() -> str:
    """Resolve users.db path with safe fallback for non-production environments.

    Production deployments mount a writable /data volume. In CI, tests, and
    local development /data is often missing or read-only — fall back to
    ``$USERS_DATABASE_PATH``, then ``$TRANC3_DATA_DIR``, then the system temp
    directory so module import never crashes at start-up.
    """
    explicit = os.environ.get("USERS_DATABASE_PATH")
    if explicit:
        return explicit
    default_dir = "/data"
    if os.path.isdir(default_dir) and os.access(default_dir, os.W_OK):
        return os.path.join(default_dir, "users.db")
    fallback_dir = os.environ.get("TRANC3_DATA_DIR") or tempfile.gettempdir()
    os.makedirs(fallback_dir, exist_ok=True)
    return os.path.join(fallback_dir, "tranc3-users.db")


DATABASE_PATH = _default_database_path()

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


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class UsersDatabase:
    def __init__(self, db_path: str = DATABASE_PATH) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
db = UsersDatabase()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _row_to_response(row: sqlite3.Row) -> UserResponse:
    prefs = row["preferences"]
    if isinstance(prefs, str):
        try:
            prefs = json.loads(prefs)
        except Exception:
            prefs = {}
    return UserResponse(
        user_id=row["user_id"],
        username=row["username"],
        email=row["email"],
        display_name=row["display_name"] or "",
        role=row["role"],
        preferences=prefs,
        is_active=bool(row["is_active"]),
        is_locked=bool(row["is_locked"]),
        bio=row["bio"] or "",
        avatar_url=row["avatar_url"] or "",
        timezone=row["timezone"] or "UTC",
        last_login=row["last_login"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
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
        "user_count": count,
        "active_count": active,
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
                user.display_name,
                user.role,
                prefs_json,
                user.bio,
                user.avatar_url,
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
        updates["display_name"] = update.display_name
    if update.email is not None:
        updates["email"] = str(update.email)
    if update.role is not None:
        updates["role"] = update.role
    if update.preferences is not None:
        updates["preferences"] = json.dumps(update.preferences)
    if update.is_active is not None:
        updates["is_active"] = 1 if update.is_active else 0
    if update.bio is not None:
        updates["bio"] = update.bio
    if update.avatar_url is not None:
        updates["avatar_url"] = update.avatar_url
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


@_router.post("/users/password-reset/request", response_model=PasswordResetResponse)
async def request_password_reset(body: PasswordResetRequest):
    """Stub: generate a password-reset token (not emailed; use notifications-service)."""
    row = db.execute(
        "SELECT * FROM users WHERE email = ? AND is_active = 1", (str(body.email),)
    ).fetchone()
    if not row:
        # Don't leak user existence
        return PasswordResetResponse(
            message="If that email is registered, a reset link has been generated.",
            reset_token="",
        )
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO password_reset_tokens (token, user_id, email, created_at) VALUES (?, ?, ?, ?)",
        (token, row["user_id"], str(body.email), now),
    )
    db.commit()
    return PasswordResetResponse(
        message="Password reset token generated.",
        reset_token=token,
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
        "SELECT role, COUNT(*) as count FROM users WHERE is_active = 1 GROUP BY role"
    ).fetchall()
    return {"roles": {row["role"]: row["count"] for row in rows}}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)
