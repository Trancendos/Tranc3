"""
Trancendos Products Service — Self-Hosted Worker
========================================================
Product catalog CRUD API. Replaces CF trancendos-products-service.

Port: 8011
Zero-cost: FastAPI + SQLite, no external dependencies.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8011
WORKER_NAME = "products-service"
DB_PATH = Path(__file__).parent / "data" / "products.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class ProductsDatabase:
    """SQLite-backed storage for products."""

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
                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    price REAL NOT NULL DEFAULT 0,
                    category TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    is_active INTEGER DEFAULT 1,
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
            cur.execute(f"INSERT INTO products ({', '.join(cols)}) VALUES ({placeholders})", vals)
        return data

    def get(self, id_field: str, id_value: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(f"SELECT * FROM products WHERE {id_field}=?", (id_value,)).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 50, offset: int = 0, **filters) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = "SELECT * FROM products WHERE 1=1"
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
            cur.execute(f"UPDATE products SET {sets} WHERE {id_field}=?", vals)
            return cur.rowcount > 0

    def delete(self, id_field: str, id_value: str, soft: bool = True) -> bool:
        if soft:
            with self._cursor() as cur:
                cur.execute(
                    f"UPDATE products SET is_active=0, updated_at=? WHERE {id_field}=?",
                    (datetime.now(timezone.utc).isoformat(), id_value),
                )
                return cur.rowcount > 0
        else:
            with self._cursor() as cur:
                cur.execute(f"DELETE FROM products WHERE {id_field}=?", (id_value,))
                return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
db = ProductsDatabase(DB_PATH)

app = FastAPI(
    title="Products Service",
    description="Product catalog CRUD API. Replaces CF trancendos-products-service.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STARTED_AT = datetime.now(timezone.utc)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


# TODO: Add specific CRUD endpoints for products-service
# The database class above provides create(), get(), list(), update(), delete() methods
# Implement domain-specific endpoints based on business requirements


@app.get("/")
async def list_all(limit: int = 50, offset: int = 0):
    """List all products."""
    return {"data": db.list(limit=limit, offset=offset)}


@app.post("/")
async def create(data: Dict[str, Any]):
    """Create a new products entry."""
    item_id = data.get("product_id", str(uuid.uuid4()))
    data["product_id"] = item_id
    created = db.create(data)
    return {"ok": True, **created}


@app.get("/{product_id}")
async def get_by_id(product_id: str):
    """Get a products entry by ID."""
    item = db.get("product_id", product_id)
    if not item:
        raise HTTPException(404, f"Not found: {product_id}")
    return item


@app.patch("/{product_id}")
async def update_by_id(product_id: str, data: Dict[str, Any]):
    """Update a products entry."""
    if not db.update("product_id", product_id, data):
        raise HTTPException(404, f"Not found: {product_id}")
    return {"ok": True}


@app.delete("/{product_id}")
async def delete_by_id(product_id: str):
    """Delete a products entry (soft delete)."""
    if not db.delete("product_id", product_id):
        raise HTTPException(404, f"Not found: {product_id}")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
