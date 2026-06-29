"""
Generate remaining P2 and P3 worker stubs for the Tranc3 platform.
Each worker follows the zero-cost FastAPI + SQLite pattern.
"""

import os

WORKERS = {
    # P2 workers
    "products-service": {
        "port": 8011,
        "title": "Products Service",
        "description": "Product catalog CRUD API. Replaces CF trancendos-products-service.",
        "table": "products",
        "fields": [
            ("product_id", "TEXT PRIMARY KEY"),
            ("name", "TEXT NOT NULL"),
            ("description", "TEXT DEFAULT ''"),
            ("price", "REAL NOT NULL DEFAULT 0"),
            ("category", "TEXT DEFAULT ''"),
            ("tags", "TEXT DEFAULT '[]'"),
            ("metadata", "TEXT DEFAULT '{}'"),
            ("is_active", "INTEGER DEFAULT 1"),
            ("created_at", "TEXT NOT NULL"),
            ("updated_at", "TEXT"),
        ],
        "sample_data": True,
    },
    "orders-service": {
        "port": 8012,
        "title": "Orders Service",
        "description": "Order management CRUD API. Replaces CF trancendos-orders-service.",
        "table": "orders",
        "fields": [
            ("order_id", "TEXT PRIMARY KEY"),
            ("user_id", "TEXT NOT NULL"),
            ("items", "TEXT NOT NULL DEFAULT '[]'"),
            ("total", "REAL NOT NULL DEFAULT 0"),
            ("status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("shipping_address", "TEXT DEFAULT '{}'"),
            ("metadata", "TEXT DEFAULT '{}'"),
            ("created_at", "TEXT NOT NULL"),
            ("updated_at", "TEXT"),
        ],
        "sample_data": True,
    },
    "payments-service": {
        "port": 8013,
        "title": "Payments Service",
        "description": "Payment processing API. Replaces CF trancendos-payments-service.",
        "table": "payments",
        "fields": [
            ("payment_id", "TEXT PRIMARY KEY"),
            ("order_id", "TEXT NOT NULL"),
            ("user_id", "TEXT NOT NULL"),
            ("amount", "REAL NOT NULL"),
            ("currency", "TEXT DEFAULT 'USD'"),
            ("status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("provider", "TEXT DEFAULT 'internal'"),
            ("provider_ref", "TEXT"),
            ("metadata", "TEXT DEFAULT '{}'"),
            ("created_at", "TEXT NOT NULL"),
        ],
        "sample_data": True,
    },
    "files-service": {
        "port": 8014,
        "title": "Files Service",
        "description": "File storage API with local filesystem + IPFS pinning. Replaces CF trancendos-files-service (R2).",
        "table": "files",
        "fields": [
            ("file_id", "TEXT PRIMARY KEY"),
            ("filename", "TEXT NOT NULL"),
            ("content_type", "TEXT DEFAULT 'application/octet-stream'"),
            ("size_bytes", "INTEGER DEFAULT 0"),
            ("path", "TEXT NOT NULL"),
            ("ipfs_cid", "TEXT"),
            ("user_id", "TEXT"),
            ("is_public", "INTEGER DEFAULT 0"),
            ("metadata", "TEXT DEFAULT '{}'"),
            ("created_at", "TEXT NOT NULL"),
        ],
        "sample_data": True,
    },
    "identity-service": {
        "port": 8015,
        "title": "Identity Service",
        "description": "Identity and access management API. Replaces CF infinity-identity-api.",
        "table": "identities",
        "fields": [
            ("identity_id", "TEXT PRIMARY KEY"),
            ("user_id", "TEXT NOT NULL"),
            ("provider", "TEXT NOT NULL"),
            ("provider_id", "TEXT NOT NULL"),
            ("email", "TEXT"),
            ("display_name", "TEXT"),
            ("avatar_url", "TEXT"),
            ("metadata", "TEXT DEFAULT '{}'"),
            ("verified", "INTEGER DEFAULT 0"),
            ("created_at", "TEXT NOT NULL"),
            ("updated_at", "TEXT"),
        ],
        "sample_data": True,
    },
}

# P3 stub workers — minimal endpoints, TODO markers for future implementation
P3_WORKERS = {
    "analytics-service": {"port": 8016, "desc": "Analytics and reporting API"},
    "search-service": {"port": 8017, "desc": "Full-text search API"},
    "email-service": {"port": 8018, "desc": "Email sending and template API"},
    "sms-service": {"port": 8019, "desc": "SMS messaging API"},
    "storage-service": {"port": 8020, "desc": "Object storage management API"},
    "cron-service": {"port": 8021, "desc": "Scheduled job management API"},
    "queue-service": {"port": 8022, "desc": "Message queue API"},
    "cache-service": {"port": 8023, "desc": "Distributed cache API"},
    "config-service": {"port": 8024, "desc": "Configuration management API"},
    "audit-service": {"port": 8025, "desc": "Audit log API"},
    "rate-limit-service": {"port": 8026, "desc": "Rate limiting service"},
    "geo-service": {"port": 8027, "desc": "Geolocation API"},
    "cdn-service": {"port": 8028, "desc": "CDN origin API"},
    "health-aggregator": {"port": 8029, "desc": "Health aggregation API"},
}


def generate_p2_worker(name: str, config: dict) -> str:
    port = config["port"]
    title = config["title"]
    desc = config["description"]
    table = config["table"]
    fields = config["fields"]

    # Build CREATE TABLE SQL
    col_defs = ",\n                    ".join(f"{f[0]} {f[1]}" for f in fields)
    # Build INSERT columns
    insert_cols = ", ".join(f[0] for f in fields if f[0] not in ("created_at", "updated_at"))
    ", ".join("?" for _ in insert_cols.split(", "))
    # Build SELECT all columns
    ", ".join(f[0] for f in fields)

    return f'''"""
Trancendos {title} — Self-Hosted Worker
{"=" * (40 + len(title))}
{desc}

Port: {port}
Zero-cost: FastAPI + SQLite, no external dependencies.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = {port}
WORKER_NAME = "{name}"
DB_PATH = Path(__file__).parent / "data" / "{table}.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class {table.title().replace("_", "")}Database:
    """SQLite-backed storage for {table}."""

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
                CREATE TABLE IF NOT EXISTS {table} (
                    {col_defs}
                )
            """)

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        data.setdefault("created_at", now)
        cols = list(data.keys())
        vals = list(data.values())
        placeholders = ", ".join("?" for _ in cols)
        with self._cursor() as cur:
            cur.execute(f"INSERT INTO {table} ({{', '.join(cols)}}) VALUES ({{placeholders}})", vals)
        return data

    def get(self, id_field: str, id_value: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(f"SELECT * FROM {table} WHERE {{id_field}}=?", (id_value,)).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 50, offset: int = 0, **filters) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = f"SELECT * FROM {table} WHERE 1=1"
        params: list = []
        for key, val in filters.items():
            query += f" AND {{key}}=?"
            params.append(val)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def update(self, id_field: str, id_value: str, data: Dict[str, Any]) -> bool:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ", ".join(f"{{k}}=?" for k in data.keys())
        vals = list(data.values()) + [id_value]
        with self._cursor() as cur:
            cur.execute(f"UPDATE {table} SET {{sets}} WHERE {{id_field}}=?", vals)
            return cur.rowcount > 0

    def delete(self, id_field: str, id_value: str, soft: bool = True) -> bool:
        if soft:
            with self._cursor() as cur:
                cur.execute(f"UPDATE {table} SET is_active=0, updated_at=? WHERE {{id_field}}=?",
                            (datetime.now(timezone.utc).isoformat(), id_value))
                return cur.rowcount > 0
        else:
            with self._cursor() as cur:
                cur.execute(f"DELETE FROM {table} WHERE {{id_field}}=?", (id_value,))
                return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
db = {table.title().replace("_", "")}Database(DB_PATH)

app = FastAPI(
    title="{title}",
    description="{desc}",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

STARTED_AT = datetime.now(timezone.utc)


@app.get("/health")
async def health():
    return {{
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }}


# TODO: Add specific CRUD endpoints for {name}
# The database class above provides create(), get(), list(), update(), delete() methods
# Implement domain-specific endpoints based on business requirements

@app.get("/")
async def list_all(limit: int = 50, offset: int = 0):
    """List all {table}."""
    return {{"data": db.list(limit=limit, offset=offset)}}


@app.post("/")
async def create(data: Dict[str, Any]):
    """Create a new {table} entry."""
    item_id = data.get("{fields[0][0]}", str(uuid.uuid4()))
    data["{fields[0][0]}"] = item_id
    created = db.create(data)
    return {{"ok": True, **created}}


@app.get("/{{{fields[0][0]}}}")
async def get_by_id({fields[0][0]}: str):
    """Get a {table} entry by ID."""
    item = db.get("{fields[0][0]}", {fields[0][0]})
    if not item:
        raise HTTPException(404, f"Not found: {{{fields[0][0]}}}")
    return item


@app.patch("/{{{fields[0][0]}}}")
async def update_by_id({fields[0][0]}: str, data: Dict[str, Any]):
    """Update a {table} entry."""
    if not db.update("{fields[0][0]}", {fields[0][0]}, data):
        raise HTTPException(404, f"Not found: {{{fields[0][0]}}}")
    return {{"ok": True}}


@app.delete("/{{{fields[0][0]}}}")
async def delete_by_id({fields[0][0]}: str):
    """Delete a {table} entry (soft delete)."""
    if not db.delete("{fields[0][0]}", {fields[0][0]}):
        raise HTTPException(404, f"Not found: {{{fields[0][0]}}}")
    return {{"ok": True}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
'''


def generate_p3_worker(name: str, config: dict) -> str:
    port = config["port"]
    desc = config["desc"]
    return f'''"""
Trancendos {name} — Self-Hosted Worker (STUB)
{"=" * (40 + len(name))}
{desc}
**STUB**: This worker provides basic health and placeholder endpoints.
Full implementation is TODO — replace with domain-specific logic.

Port: {port}
Zero-cost: FastAPI + SQLite pattern, no external dependencies.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = {port}
WORKER_NAME = "{name}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="{name}",
    description="{desc} (Stub — TODO: Full implementation)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

STARTED_AT = datetime.now(timezone.utc)


@app.get("/health")
async def health():
    return {{
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "note": "Stub worker — full implementation TODO",
    }}


@app.get("/")
async def root():
    """Placeholder root endpoint."""
    return {{
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "status": "stub",
        "message": "This worker is a stub. Full implementation is TODO.",
        "endpoints": ["/health", "/", "/docs"],
    }}


# TODO: Implement domain-specific endpoints for {name}
# - Add SQLite database class following the standard pattern
# - Add Pydantic models for request/response validation
# - Add CRUD endpoints specific to this service
# - Add any domain-specific business logic


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
'''


def write_worker_files(name: str, worker_code: str, port: int):
    """Write worker.py, requirements-worker.txt, and Dockerfile for a worker."""
    worker_dir = f"Tranc3/workers/{name}"
    os.makedirs(worker_dir, exist_ok=True)
    os.makedirs(f"{worker_dir}/data", exist_ok=True)

    with open(f"{worker_dir}/worker.py", "w") as f:
        f.write(worker_code)

    with open(f"{worker_dir}/requirements-worker.txt", "w") as f:
        f.write("fastapi>=0.110.0\nuvicorn>=0.29.0\npydantic>=2.0.0\n")

    with open(f"{worker_dir}/Dockerfile", "w") as f:
        f.write(f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY worker.py .
RUN mkdir -p /app/data
EXPOSE {port}
CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "{port}"]
""")


if __name__ == "__main__":
    # Generate P2 workers
    for name, config in WORKERS.items():
        code = generate_p2_worker(name, config)
        write_worker_files(name, code, config["port"])
        print(f"✅ Generated P2 worker: {name} (port {config['port']})")

    # Generate P3 stub workers
    for name, config in P3_WORKERS.items():
        code = generate_p3_worker(name, config)
        write_worker_files(name, code, config["port"])
        print(f"✅ Generated P3 stub: {name} (port {config['port']})")

    print(
        f"\n🎉 Total: {len(WORKERS)} P2 workers + {len(P3_WORKERS)} P3 stubs = {len(WORKERS) + len(P3_WORKERS)} workers generated"
    )
