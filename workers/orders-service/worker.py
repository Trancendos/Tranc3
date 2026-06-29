"""
Arcadian Exchange — Self-Hosted Worker
=======================================
Resource marketplace: listings, orders, stats.
Lead AI: The Porter Family

Port: 8012
Zero-cost: FastAPI + SQLite, no external dependencies.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8012
WORKER_NAME = "arcadian-exchange"
DB_PATH = Path(__file__).parent / "data" / "exchange.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

RESOURCE_TYPES = frozenset(
    [
        "api_credits",
        "compute_time",
        "storage_gb",
        "model_weights",
        "workflow_slots",
        "agent_hours",
        "training_tokens",
        "bandwidth_gb",
    ]
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def _cursor(conn: sqlite3.Connection):
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def init_db() -> None:
    conn = _get_conn()
    with _cursor(conn) as cur:
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS listings (
                id              TEXT PRIMARY KEY,
                seller_id       TEXT NOT NULL,
                resource_type   TEXT NOT NULL,
                quantity        REAL NOT NULL,
                price_per_unit  REAL NOT NULL,
                currency        TEXT NOT NULL DEFAULT 'ARC',
                description     TEXT DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'active',
                created_at      TEXT NOT NULL,
                updated_at      TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_listings_type_status
                ON listings(resource_type, status, price_per_unit);

            CREATE TABLE IF NOT EXISTS orders (
                id              TEXT PRIMARY KEY,
                buyer_id        TEXT NOT NULL,
                listing_id      TEXT NOT NULL,
                quantity        REAL NOT NULL,
                total_price     REAL NOT NULL,
                status          TEXT NOT NULL DEFAULT 'completed',
                created_at      TEXT NOT NULL,
                FOREIGN KEY (listing_id) REFERENCES listings(id)
            );
            CREATE INDEX IF NOT EXISTS idx_orders_buyer ON orders(buyer_id, created_at DESC);
        """)
    conn.close()
    logger.info("Arcadian Exchange DB ready at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.arcadian-exchange")
    except Exception:
        pass
    init_db()
    yield


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class CreateListingRequest(BaseModel):
    seller_id: str
    resource_type: str
    quantity: float = Field(..., gt=0)
    price_per_unit: float = Field(..., ge=0)
    currency: str = "ARC"
    description: str = ""


class PurchaseRequest(BaseModel):
    buyer_id: str
    listing_id: str
    quantity: float = Field(..., gt=0)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="Arcadian Exchange",
    description="Resource marketplace — API credits, compute, storage, models, workflows. Lead AI: The Porter Family.",
    version="2.0.0",
    lifespan=lifespan,
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


@app.get("/health")
async def health():
    conn = _get_conn()
    listing_count = conn.execute("SELECT COUNT(*) FROM listings WHERE status='active'").fetchone()[
        0
    ]
    order_count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "active_listings": listing_count,
        "total_orders": order_count,
        "entity": {
            "name": "Arcadian Exchange",
            "lead_ai": "The Porter Family",
            "role": "Financial exchange — procurement & resource trading",
        },
    }


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------
@_router.post("/listings", status_code=201)
async def create_listing(req: CreateListingRequest):
    """Create a resource listing on the exchange."""
    if req.resource_type not in RESOURCE_TYPES:
        raise HTTPException(
            400,
            f"Unknown resource_type '{req.resource_type}'. Valid types: {sorted(RESOURCE_TYPES)}",
        )
    listing_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        with _cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO listings (id, seller_id, resource_type, quantity, price_per_unit, currency, description, created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    listing_id,
                    req.seller_id,
                    req.resource_type,
                    req.quantity,
                    req.price_per_unit,
                    req.currency,
                    req.description,
                    now,
                ),
            )
    finally:
        conn.close()
    return {
        "id": listing_id,
        "seller_id": req.seller_id,
        "resource_type": req.resource_type,
        "quantity": req.quantity,
        "price_per_unit": req.price_per_unit,
        "currency": req.currency,
        "status": "active",
        "created_at": now,
    }


@_router.get("/listings")
async def browse_listings(
    resource_type: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    seller_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Browse the marketplace with optional filters."""
    # Build conditions and params as parallel lists to avoid SQL concatenation.
    # All user inputs are bound via parameterized placeholders — never interpolated.
    conditions = ["status='active'"]
    params: list = []
    if resource_type:
        conditions.append("resource_type=?")
        params.append(resource_type)
    if min_price is not None:
        conditions.append("price_per_unit >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("price_per_unit <= ?")
        params.append(max_price)
    if seller_id:
        conditions.append("seller_id=?")
        params.append(seller_id)

    where_clause = " AND ".join(conditions)
    listing_sql = (
        f"SELECT * FROM listings WHERE {where_clause} ORDER BY price_per_unit ASC LIMIT ? OFFSET ?"  # noqa: S608
    )
    count_sql = f"SELECT COUNT(*) FROM listings WHERE {where_clause}"  # noqa: S608

    conn = _get_conn()
    try:
        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query
        # `listing_sql` and `count_sql` are built from a hardcoded conditions list;
        # all user-supplied values are passed as bound parameters, never interpolated.
        rows = conn.execute(listing_sql, [*params, limit, offset]).fetchall()  # nosec B608
        total = conn.execute(count_sql, params).fetchone()[0]  # nosec B608
        return {"total": total, "listings": [dict(r) for r in rows]}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
@_router.post("/orders", status_code=201)
async def purchase(req: PurchaseRequest):
    """Purchase from a listing (atomic quantity check + deduct)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        conn.execute("BEGIN EXCLUSIVE")
        listing = conn.execute(
            "SELECT * FROM listings WHERE id=? AND status='active'", (req.listing_id,)
        ).fetchone()
        if not listing:
            conn.rollback()
            raise HTTPException(404, "Listing not found or not active")
        if listing["quantity"] < req.quantity:
            conn.rollback()
            raise HTTPException(
                409,
                f"Insufficient quantity: available {listing['quantity']}, requested {req.quantity}",
            )

        total_price = round(listing["price_per_unit"] * req.quantity, 6)
        order_id = str(uuid.uuid4())

        # Deduct quantity from listing; mark sold-out if depleted
        new_qty = listing["quantity"] - req.quantity
        new_status = "active" if new_qty > 0 else "sold"
        conn.execute(
            "UPDATE listings SET quantity=?, status=?, updated_at=? WHERE id=?",
            (new_qty, new_status, now, req.listing_id),
        )
        conn.execute(
            """
            INSERT INTO orders (id, buyer_id, listing_id, quantity, total_price, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (order_id, req.buyer_id, req.listing_id, req.quantity, total_price, now),
        )
        conn.commit()

        return {
            "order_id": order_id,
            "buyer_id": req.buyer_id,
            "listing_id": req.listing_id,
            "resource_type": listing["resource_type"],
            "quantity": req.quantity,
            "price_per_unit": listing["price_per_unit"],
            "total_price": total_price,
            "currency": listing["currency"],
            "status": "completed",
            "created_at": now,
        }
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception("Purchase failed")
        raise HTTPException(500, f"Purchase failed: {exc}") from exc
    finally:
        conn.close()


@_router.get("/orders/{buyer_id}")
async def buyer_orders(
    buyer_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Buyer's order history with listing detail."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT o.*, l.resource_type, l.price_per_unit, l.currency, l.seller_id
            FROM orders o
            JOIN listings l ON l.id = o.listing_id
            WHERE o.buyer_id=?
            ORDER BY o.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (buyer_id, limit, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE buyer_id=?", (buyer_id,)
        ).fetchone()[0]
        return {"buyer_id": buyer_id, "total": total, "orders": [dict(r) for r in rows]}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Exchange Stats
# ---------------------------------------------------------------------------
@_router.get("/exchange/stats")
async def exchange_stats():
    """Total listings, volume traded, most traded resources."""
    conn = _get_conn()
    try:
        total_active = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE status='active'"
        ).fetchone()[0]
        total_volume = (
            conn.execute("SELECT COALESCE(SUM(total_price),0) FROM orders").fetchone()[0] or 0
        )
        total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]

        most_traded = conn.execute(
            """
            SELECT l.resource_type, COUNT(o.id) as order_count, SUM(o.quantity) as total_qty, SUM(o.total_price) as total_value
            FROM orders o JOIN listings l ON l.id=o.listing_id
            GROUP BY l.resource_type
            ORDER BY order_count DESC
            LIMIT 10
            """
        ).fetchall()

        return {
            "active_listings": total_active,
            "total_orders": total_orders,
            "total_volume": round(total_volume, 4),
            "resource_types_available": sorted(RESOURCE_TYPES),
            "most_traded": [dict(r) for r in most_traded],
            "as_of": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
