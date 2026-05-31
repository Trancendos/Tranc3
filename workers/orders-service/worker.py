"""
Trancendos Orders Service — Self-Hosted Worker
======================================================
Order management CRUD API. Replaces CF trancendos-orders-service.

Port: 8012
Zero-cost: FastAPI + SQLite, no external dependencies.
"""

from __future__ import annotations
from src.entities.health_metadata import health_entity_block

import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8012
WORKER_NAME = "orders-service"
DB_PATH = Path(__file__).parent / "data" / "orders.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class OrdersDatabase:
    """SQLite-backed storage for orders."""

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
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    items TEXT NOT NULL DEFAULT '[]',
                    total REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    shipping_address TEXT DEFAULT '{}',
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        data.setdefault("created_at", now)
        cols = list(data.keys())
        vals = list(data.values())
        placeholders = ", ".join("?" for _ in cols)
        with self._cursor() as cur:
            cur.execute(f"INSERT INTO orders ({', '.join(cols)}) VALUES ({placeholders})", vals)
        return data

    def get(self, id_field: str, id_value: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(f"SELECT * FROM orders WHERE {id_field}=?", (id_value,)).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 50, offset: int = 0, **filters) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = "SELECT * FROM orders WHERE 1=1"
        params: list = []
        for key, val in filters.items():
            query += f" AND {key}=?"
            params.append(val)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def update(self, id_field: str, id_value: str, data: Dict[str, Any]) -> bool:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ", ".join(f"{k}=?" for k in data.keys())
        vals = list(data.values()) + [id_value]
        with self._cursor() as cur:
            cur.execute(f"UPDATE orders SET {sets} WHERE {id_field}=?", vals)
            return cur.rowcount > 0

    def delete(self, id_field: str, id_value: str, soft: bool = True) -> bool:
        # orders table doesn't have is_active column; use status-based soft delete
        if soft:
            with self._cursor() as cur:
                cur.execute(
                    f"UPDATE orders SET status='cancelled', updated_at=? WHERE {id_field}=?",
                    (datetime.now(timezone.utc).isoformat(), id_value),
                )
                return cur.rowcount > 0
        else:
            with self._cursor() as cur:
                cur.execute(f"DELETE FROM orders WHERE {id_field}=?", (id_value,))
                return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
db = OrdersDatabase(DB_PATH)

app = FastAPI(
    title="Orders Service",
    description="Order management CRUD API. Replaces CF trancendos-orders-service.",
    version="1.0.0",
)

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
        "entity": health_entity_block(8012, "orders-service"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


@_router.get("/")
async def list_all(limit: int = 50, offset: int = 0):
    """List all orders."""
    return {"data": db.list(limit=limit, offset=offset)}


@_router.post("/")
async def create(data: Dict[str, Any]):
    """Create a new orders entry."""
    item_id = data.get("order_id", str(uuid.uuid4()))
    data["order_id"] = item_id
    created = db.create(data)
    return {"ok": True, **created}


@_router.get("/{order_id}")
async def get_by_id(order_id: str):
    """Get a orders entry by ID."""
    item = db.get("order_id", order_id)
    if not item:
        raise HTTPException(404, f"Not found: {order_id}")
    return item


@_router.patch("/{order_id}")
async def update_by_id(order_id: str, data: Dict[str, Any]):
    """Update a orders entry."""
    if not db.update("order_id", order_id, data):
        raise HTTPException(404, f"Not found: {order_id}")
    return {"ok": True}


@_router.delete("/{order_id}")
async def delete_by_id(order_id: str):
    """Delete a orders entry (soft delete)."""
    if not db.delete("order_id", order_id):
        raise HTTPException(404, f"Not found: {order_id}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Domain-specific endpoints
# ---------------------------------------------------------------------------


@_router.get("/by-user/{user_id}")
async def get_by_user(user_id: str, limit: int = 50, offset: int = 0):
    """List all orders placed by a specific user."""
    return {"data": db.list(limit=limit, offset=offset, user_id=user_id)}


@_router.get("/by-status/{status}")
async def get_by_status(status: str, limit: int = 50, offset: int = 0):
    """List orders by status (pending, confirmed, shipped, delivered, cancelled)."""
    valid = {"pending", "confirmed", "shipped", "delivered", "cancelled"}
    if status not in valid:
        raise HTTPException(400, f"Invalid status. Must be one of: {sorted(valid)}")
    return {"data": db.list(limit=limit, offset=offset, status=status)}


@_router.post("/{order_id}/confirm")
async def confirm_order(order_id: str):
    """Confirm a pending order."""
    item = db.get("order_id", order_id)
    if not item:
        raise HTTPException(404, f"Not found: {order_id}")
    if item.get("status") != "pending":
        raise HTTPException(409, f"Order status is '{item.get('status')}', not pending")
    db.update("order_id", order_id, {"status": "confirmed"})
    return {"ok": True, "order_id": order_id, "status": "confirmed"}


@_router.post("/{order_id}/ship")
async def ship_order(order_id: str):
    """Mark an order as shipped."""
    item = db.get("order_id", order_id)
    if not item:
        raise HTTPException(404, f"Not found: {order_id}")
    if item.get("status") != "confirmed":
        raise HTTPException(
            409, f"Order must be confirmed before shipping, got '{item.get('status')}'"
        )
    db.update("order_id", order_id, {"status": "shipped"})
    return {"ok": True, "order_id": order_id, "status": "shipped"}


@_router.post("/{order_id}/deliver")
async def deliver_order(order_id: str):
    """Mark an order as delivered."""
    item = db.get("order_id", order_id)
    if not item:
        raise HTTPException(404, f"Not found: {order_id}")
    if item.get("status") != "shipped":
        raise HTTPException(
            409, f"Order must be shipped before delivery, got '{item.get('status')}'"
        )
    db.update("order_id", order_id, {"status": "delivered"})
    return {"ok": True, "order_id": order_id, "status": "delivered"}


@_router.post("/{order_id}/cancel")
async def cancel_order(order_id: str):
    """Cancel an order (only pending or confirmed orders can be cancelled)."""
    item = db.get("order_id", order_id)
    if not item:
        raise HTTPException(404, f"Not found: {order_id}")
    if item.get("status") not in ("pending", "confirmed"):
        raise HTTPException(409, f"Cannot cancel order with status '{item.get('status')}'")
    db.update("order_id", order_id, {"status": "cancelled"})
    return {"ok": True, "order_id": order_id, "status": "cancelled"}


@_router.get("/stats/summary")
async def order_stats():
    """Order counts and total revenue by status."""
    conn = db._get_conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) as count, SUM(total) as revenue FROM orders GROUP BY status"
    ).fetchall()
    return {"stats": [dict(r) for r in rows]}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
