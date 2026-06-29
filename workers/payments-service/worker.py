"""
Royal Bank of Arcadia — Self-Hosted Worker
===========================================
Financial hub: accounts ledger, transfers, deposits, AUM reporting.
Lead AI: Dorris Fontaine

Port: 8013
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

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8013
WORKER_NAME = "royal-bank-of-arcadia"
DB_PATH = Path(__file__).parent / "data" / "royal_bank.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

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
            CREATE TABLE IF NOT EXISTS accounts (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                name        TEXT NOT NULL DEFAULT 'Main Account',
                balance     REAL NOT NULL DEFAULT 0.0,
                currency    TEXT NOT NULL DEFAULT 'ARC',
                status      TEXT NOT NULL DEFAULT 'active',
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id);

            CREATE TABLE IF NOT EXISTS transactions (
                id              TEXT PRIMARY KEY,
                from_account    TEXT,
                to_account      TEXT,
                amount          REAL NOT NULL,
                type            TEXT NOT NULL,
                description     TEXT DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'completed',
                created_at      TEXT NOT NULL,
                FOREIGN KEY (from_account) REFERENCES accounts(id),
                FOREIGN KEY (to_account)   REFERENCES accounts(id)
            );
            CREATE INDEX IF NOT EXISTS idx_tx_from ON transactions(from_account, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tx_to   ON transactions(to_account,   created_at DESC);
        """)
    conn.close()


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class CreateAccountRequest(BaseModel):
    user_id: str
    name: str = "Main Account"
    currency: str = "ARC"
    initial_balance: float = Field(0.0, ge=0)


class TransferRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    amount: float = Field(..., gt=0)
    description: str = ""


class DepositRequest(BaseModel):
    account_id: str
    amount: float = Field(..., gt=0)
    description: str = "Deposit"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.royal-bank")
    except Exception:
        pass
    init_db()
    logger.info("Royal Bank of Arcadia DB ready at %s", DB_PATH)
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="Royal Bank of Arcadia",
    description="Financial hub — accounts ledger, transfers, deposits, AUM. Lead AI: Dorris Fontaine.",
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
    account_count = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    tx_count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "accounts": account_count,
        "transactions": tx_count,
        "entity": {
            "name": "Royal Bank of Arcadia",
            "lead_ai": "Dorris Fontaine",
            "role": "Financial hub — billing, payments",
        },
    }


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
@_router.post("/accounts", status_code=201)
async def create_account(req: CreateAccountRequest):
    """Create a new account for a user."""
    acct_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        with _cursor(conn) as cur:
            cur.execute(
                "INSERT INTO accounts (id, user_id, name, balance, currency, created_at) VALUES (?,?,?,?,?,?)",
                (acct_id, req.user_id, req.name, req.initial_balance, req.currency, now),
            )
            # Record initial deposit if non-zero
            if req.initial_balance > 0:
                cur.execute(
                    "INSERT INTO transactions (id, to_account, amount, type, description, created_at) VALUES (?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        acct_id,
                        req.initial_balance,
                        "deposit",
                        "Initial deposit",
                        now,
                    ),
                )
    finally:
        conn.close()
    return {
        "id": acct_id,
        "user_id": req.user_id,
        "name": req.name,
        "balance": req.initial_balance,
        "currency": req.currency,
        "status": "active",
        "created_at": now,
    }


@_router.get("/accounts/{user_id}")
async def get_user_accounts(user_id: str):
    """Get all accounts and balances for a user."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE user_id=? AND status='active' ORDER BY created_at",
            (user_id,),
        ).fetchall()
        return {"user_id": user_id, "accounts": [dict(r) for r in rows]}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
@_router.post("/transactions/transfer")
async def transfer(req: TransferRequest):
    """Atomic transfer between two accounts."""
    conn = _get_conn()
    try:
        # Use BEGIN EXCLUSIVE for atomicity
        conn.execute("BEGIN EXCLUSIVE")
        from_row = conn.execute(
            "SELECT id, balance, currency, status FROM accounts WHERE id=?", (req.from_account_id,)
        ).fetchone()
        to_row = conn.execute(
            "SELECT id, status FROM accounts WHERE id=?", (req.to_account_id,)
        ).fetchone()

        if not from_row:
            conn.rollback()
            raise HTTPException(404, "Source account not found")
        if not to_row:
            conn.rollback()
            raise HTTPException(404, "Destination account not found")
        if from_row["status"] != "active":
            conn.rollback()
            raise HTTPException(400, "Source account is not active")
        if to_row["status"] != "active":
            conn.rollback()
            raise HTTPException(400, "Destination account is not active")
        if from_row["balance"] < req.amount:
            conn.rollback()
            raise HTTPException(
                409,
                f"Insufficient funds: balance {from_row['balance']:.2f}, requested {req.amount:.2f}",
            )

        now = datetime.now(timezone.utc).isoformat()
        tx_id = str(uuid.uuid4())

        conn.execute(
            "UPDATE accounts SET balance = balance - ? WHERE id=?",
            (req.amount, req.from_account_id),
        )
        conn.execute(
            "UPDATE accounts SET balance = balance + ? WHERE id=?", (req.amount, req.to_account_id)
        )
        conn.execute(
            "INSERT INTO transactions (id, from_account, to_account, amount, type, description, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                tx_id,
                req.from_account_id,
                req.to_account_id,
                req.amount,
                "transfer",
                req.description,
                now,
            ),
        )
        conn.commit()

        new_balance = conn.execute(
            "SELECT balance FROM accounts WHERE id=?", (req.from_account_id,)
        ).fetchone()[0]

        return {
            "ok": True,
            "transaction_id": tx_id,
            "from_account": req.from_account_id,
            "to_account": req.to_account_id,
            "amount": req.amount,
            "from_balance_after": new_balance,
            "created_at": now,
        }
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception("Transfer failed")
        raise HTTPException(500, f"Transfer failed: {exc}") from exc
    finally:
        conn.close()


@_router.post("/transactions/deposit")
async def deposit(req: DepositRequest):
    """Deposit funds into an account."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, status FROM accounts WHERE id=?", (req.account_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Account not found")
        if row["status"] != "active":
            raise HTTPException(400, "Account is not active")

        now = datetime.now(timezone.utc).isoformat()
        tx_id = str(uuid.uuid4())
        with _cursor(conn) as cur:
            cur.execute(
                "UPDATE accounts SET balance = balance + ? WHERE id=?", (req.amount, req.account_id)
            )
            cur.execute(
                "INSERT INTO transactions (id, to_account, amount, type, description, created_at) VALUES (?,?,?,?,?,?)",
                (tx_id, req.account_id, req.amount, "deposit", req.description, now),
            )
        new_balance = conn.execute(
            "SELECT balance FROM accounts WHERE id=?", (req.account_id,)
        ).fetchone()[0]
        return {
            "ok": True,
            "transaction_id": tx_id,
            "account_id": req.account_id,
            "amount": req.amount,
            "balance_after": new_balance,
            "created_at": now,
        }
    finally:
        conn.close()


@_router.get("/transactions/{account_id}")
async def get_transactions(
    account_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Transaction history for an account (both sent and received)."""
    conn = _get_conn()
    try:
        # Verify account exists
        if not conn.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone():
            raise HTTPException(404, "Account not found")
        rows = conn.execute(
            """
            SELECT * FROM transactions
            WHERE from_account=? OR to_account=?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (account_id, account_id, limit, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE from_account=? OR to_account=?",
            (account_id, account_id),
        ).fetchone()[0]
        return {"account_id": account_id, "total": total, "transactions": [dict(r) for r in rows]}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Ledger Summary
# ---------------------------------------------------------------------------
@_router.get("/ledger/summary")
async def ledger_summary():
    """Platform-wide AUM, transaction count, and daily volume."""
    conn = _get_conn()
    try:
        aum = (
            conn.execute("SELECT SUM(balance) FROM accounts WHERE status='active'").fetchone()[0]
            or 0
        )
        total_accounts = conn.execute(
            "SELECT COUNT(*) FROM accounts WHERE status='active'"
        ).fetchone()[0]
        total_txns = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

        # Daily volume (UTC today)
        today = datetime.now(timezone.utc).date().isoformat()
        daily_vol = (
            conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE created_at >= ? AND type IN ('transfer','deposit')",
                (today,),
            ).fetchone()[0]
            or 0
        )

        by_currency = conn.execute(
            "SELECT currency, COUNT(*) as accounts, SUM(balance) as total FROM accounts WHERE status='active' GROUP BY currency"
        ).fetchall()

        return {
            "total_aum": round(aum, 4),
            "total_accounts": total_accounts,
            "total_transactions": total_txns,
            "daily_volume": round(daily_vol, 4),
            "by_currency": [dict(r) for r in by_currency],
            "as_of": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
