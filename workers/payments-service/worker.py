"""
Trancendos Payments Service — Self-Hosted Worker
========================================================
Payment processing API. Replaces CF trancendos-payments-service.

Port: 8013
Zero-cost: FastAPI + SQLite, no external dependencies.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from src.database.encrypted_sqlite import connect as sqlite3_connect
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.entities.health_metadata import health_entity_block

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8013
WORKER_NAME = "payments-service"
DB_PATH = Path(__file__).parent / "data" / "payments.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class PaymentsDatabase:
    """SQLite-backed storage for payments."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3_connect(str(self.db_path), timeout=10)
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
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT DEFAULT 'USD',
                    status TEXT NOT NULL DEFAULT 'pending',
                    provider TEXT DEFAULT 'internal',
                    provider_ref TEXT,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        data.setdefault("created_at", now)
        cols = list(data.keys())
        vals = list(data.values())
        placeholders = ", ".join("?" for _ in cols)
        with self._cursor() as cur:
            cur.execute(f"INSERT INTO payments ({', '.join(cols)}) VALUES ({placeholders})", vals)
        return data

    def get(self, id_field: str, id_value: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(f"SELECT * FROM payments WHERE {id_field}=?", (id_value,)).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 50, offset: int = 0, **filters) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = "SELECT * FROM payments WHERE 1=1"
        params: list = []
        for key, val in filters.items():
            query += f" AND {key}=?"
            params.append(val)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def update(self, id_field: str, id_value: str, data: Dict[str, Any]) -> bool:
        # payments table doesn't have updated_at column
        sets = ", ".join(f"{k}=?" for k in data.keys())
        vals = list(data.values()) + [id_value]
        with self._cursor() as cur:
            cur.execute(f"UPDATE payments SET {sets} WHERE {id_field}=?", vals)
            return cur.rowcount > 0

    def delete(self, id_field: str, id_value: str, soft: bool = True) -> bool:
        # payments table doesn't have is_active column; use status-based soft delete
        if soft:
            with self._cursor() as cur:
                cur.execute(
                    f"UPDATE payments SET status='cancelled' WHERE {id_field}=?",
                    (id_value,),
                )
                return cur.rowcount > 0
        else:
            with self._cursor() as cur:
                cur.execute(f"DELETE FROM payments WHERE {id_field}=?", (id_value,))
                return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
db = PaymentsDatabase(DB_PATH)

app = FastAPI(
    title="Payments Service",
    description="Payment processing API. Replaces CF trancendos-payments-service.",
    version="1.0.0",
)

from src.observability.prometheus_mount import mount_prometheus_endpoint

mount_prometheus_endpoint(app, "payments-service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])
STARTED_AT = datetime.now(timezone.utc)


@app.get("/health")
async def health():
    return {
        "entity": health_entity_block(8013, "payments-service"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


@_router.get("/")
async def list_all(limit: int = 50, offset: int = 0):
    """List all payments."""
    return {"data": db.list(limit=limit, offset=offset)}


@_router.post("/")
async def create(data: Dict[str, Any]):
    """Create a new payments entry."""
    item_id = data.get("payment_id", str(uuid.uuid4()))
    data["payment_id"] = item_id
    created = db.create(data)
    return {"ok": True, **created}


@_router.get("/{payment_id}")
async def get_by_id(payment_id: str):
    """Get a payments entry by ID."""
    item = db.get("payment_id", payment_id)
    if not item:
        raise HTTPException(404, f"Not found: {payment_id}")
    return item


@_router.patch("/{payment_id}")
async def update_by_id(payment_id: str, data: Dict[str, Any]):
    """Update a payments entry."""
    if not db.update("payment_id", payment_id, data):
        raise HTTPException(404, f"Not found: {payment_id}")
    return {"ok": True}


@_router.delete("/{payment_id}")
async def delete_by_id(payment_id: str):
    """Delete a payments entry (soft delete)."""
    if not db.delete("payment_id", payment_id):
        raise HTTPException(404, f"Not found: {payment_id}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Domain-specific endpoints
# ---------------------------------------------------------------------------


@_router.get("/by-order/{order_id}")
async def get_by_order(order_id: str):
    """List all payments for a given order."""
    return {"data": db.list(limit=100, offset=0, order_id=order_id)}


@_router.get("/by-user/{user_id}")
async def get_by_user(user_id: str, limit: int = 50, offset: int = 0):
    """List all payments made by a user."""
    return {"data": db.list(limit=limit, offset=offset, user_id=user_id)}


@_router.get("/by-status/{status}")
async def get_by_status(status: str, limit: int = 50, offset: int = 0):
    """List payments by status (pending, completed, failed, cancelled, refunded)."""
    valid = {"pending", "completed", "failed", "cancelled", "refunded"}
    if status not in valid:
        raise HTTPException(400, f"Invalid status. Must be one of: {sorted(valid)}")
    return {"data": db.list(limit=limit, offset=offset, status=status)}


@_router.post("/{payment_id}/capture")
async def capture_payment(payment_id: str):
    """Capture a pending payment (mark as completed)."""
    item = db.get("payment_id", payment_id)
    if not item:
        raise HTTPException(404, f"Not found: {payment_id}")
    if item.get("status") != "pending":
        raise HTTPException(409, f"Payment status is '{item.get('status')}', not pending")
    db.update("payment_id", payment_id, {"status": "completed"})
    return {"ok": True, "payment_id": payment_id, "status": "completed"}


@_router.post("/{payment_id}/refund")
async def refund_payment(payment_id: str):
    """Refund a completed payment."""
    item = db.get("payment_id", payment_id)
    if not item:
        raise HTTPException(404, f"Not found: {payment_id}")
    if item.get("status") != "completed":
        raise HTTPException(409, f"Payment status is '{item.get('status')}', not completed")
    db.update("payment_id", payment_id, {"status": "refunded"})
    return {"ok": True, "payment_id": payment_id, "status": "refunded"}


@_router.post("/{payment_id}/cancel")
async def cancel_payment(payment_id: str):
    """Cancel a pending payment."""
    item = db.get("payment_id", payment_id)
    if not item:
        raise HTTPException(404, f"Not found: {payment_id}")
    if item.get("status") not in ("pending",):
        raise HTTPException(409, f"Cannot cancel payment with status '{item.get('status')}'")
    db.update("payment_id", payment_id, {"status": "cancelled"})
    return {"ok": True, "payment_id": payment_id, "status": "cancelled"}


@_router.get("/stats/summary")
async def payment_stats():
    """Aggregate payment statistics by status and total amounts."""
    conn = db._get_conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) as count, SUM(amount) as total FROM payments GROUP BY status",
    ).fetchall()
    return {"stats": [dict(r) for r in rows]}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
