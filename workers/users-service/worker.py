"""
Trancendos Users Service — Self-Hosted Worker
================================================
Replaces CF trancendos-users-service.
User management CRUD API with SQLite storage.

Maps to: Infinity / user management
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger("tranc3.workers.users-service")

DATABASE_PATH = "/data/users.db"


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    display_name: str = Field(default="", max_length=100)
    role: str = Field(default="user", pattern=r"^(user|admin|moderator)$")
    preferences: dict = Field(default_factory=dict)


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None
    role: str | None = None
    preferences: dict | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    user_id: str
    username: str
    email: str
    display_name: str
    role: str
    preferences: dict
    is_active: bool
    created_at: str
    updated_at: str | None = None


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
    page: int
    per_page: int


class UsersDatabase:
    def __init__(self, db_path: str = DATABASE_PATH) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                display_name TEXT DEFAULT '',
                role TEXT DEFAULT 'user',
                preferences TEXT DEFAULT '{}',
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
        """)
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()


app = FastAPI(title="Trancendos Users Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
db = UsersDatabase()


@app.get("/health")
async def health():
    count = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    return {"status": "healthy", "service": "users-service", "user_count": count}


@app.post("/users", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate):
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    try:
        db.execute(
            "INSERT INTO users (user_id, username, email, display_name, role, preferences, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                user.username,
                user.email,
                user.display_name,
                user.role,
                str(user.preferences),
                now,
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username or email already exists") from None
    return UserResponse(
        user_id=user_id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        preferences=user.preferences,
        is_active=True,
        created_at=now,
    )


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return _row_to_response(row)


@app.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(default=1, ge=1), per_page: int = Query(default=20, ge=1, le=100)
):
    offset = (page - 1) * per_page
    total = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    rows = db.execute(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (per_page, offset)
    ).fetchall()
    return UserListResponse(
        users=[_row_to_response(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@app.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, update: UserUpdate):
    existing = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    updates = {}
    if update.display_name is not None:
        updates["display_name"] = update.display_name
    if update.email is not None:
        updates["email"] = update.email
    if update.role is not None:
        updates["role"] = update.role
    if update.preferences is not None:
        updates["preferences"] = str(update.preferences)
    if update.is_active is not None:
        updates["is_active"] = 1 if update.is_active else 0
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    db.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", (*updates.values(), user_id))
    db.commit()

    row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_response(row)


@app.delete("/users/{user_id}")
async def delete_user(user_id: str):
    result = db.execute(
        "UPDATE users SET is_active = 0, updated_at = ? WHERE user_id = ?",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deactivated"}


def _row_to_response(row: sqlite3.Row) -> UserResponse:
    prefs = row["preferences"]
    if isinstance(prefs, str):
        try:
            import json

            prefs = json.loads(prefs)
        except Exception:
            prefs = {}
    return UserResponse(
        user_id=row["user_id"],
        username=row["username"],
        email=row["email"],
        display_name=row["display_name"],
        role=row["role"],
        preferences=prefs,
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)
