"""What happens to a gain, and what happens after a loss.

Dorris Fontaine's half of the Exchange. The Porters find and price
opportunities; this decides what the platform does with the result.

**A gain is split, not banked.** A configured share of every realised gain is
reinvested into the platform -- the founder's server, the paid tiers the
zero-cost architecture currently works around, the funding the Local/Hybrid
deployment modes are blocked on (`CLAUDE.md`, "Zero-Cost Self-Hosted
Architecture"). The rest is retained. The split is one number in one place so
it is a decision somebody made rather than an emergent property of whoever
spent what.

**A loss stops the domain until somebody says why.** Not a warning, not a
metric on a dashboard: the domain is barred from further proposals until a
remediation measure is recorded against the loss. This estate's recurring
failure is a control that reports and does not hold, and a loss register that
merely accumulates rows would be another one. The bar is the control; the
register is only its evidence.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from src.exchange.domains import TAXONOMY_OWNER, TAXONOMY_OWNER_TITLE, Domain

logger = logging.getLogger("tranc3.exchange.treasury")

#: Share of a realised gain returned to the platform rather than retained.
#: A round number chosen deliberately rather than modelled: there is no
#: earnings history to optimise against, and a precise-looking figure derived
#: from nothing would be exactly the fabrication the valuation layer refuses.
#: Revisit it against real settlements, not against a spreadsheet.
DEFAULT_REINVESTMENT_RATE = 0.40


class Allocation(str, Enum):
    """Where a reinvested share goes.

    Drawn from what the platform is actually blocked on rather than invented
    as general categories. `INFRASTRUCTURE` is the founder's server, which
    `CLAUDE.md` records as the reason every Location is Cloud Only today.
    """

    INFRASTRUCTURE = "infrastructure"
    CAPABILITY = "capability"
    COMPLIANCE = "compliance"
    RESERVE = "reserve"


@dataclass(frozen=True)
class Settlement:
    """One realised outcome, after the split."""

    resource_id: str
    domain: str
    estimated: float
    realised: float
    #: realised - estimated. Negative is a loss.
    variance: float
    reinvested: float
    retained: float
    allocation: Optional[str]
    settled_at: float

    @property
    def is_loss(self) -> bool:
        return self.variance < 0


@dataclass(frozen=True)
class LossEntry:
    """A recorded loss and the measure taken, if any."""

    loss_id: int
    resource_id: str
    domain: str
    estimated: float
    realised: float
    variance: float
    recorded_at: float
    measure: Optional[str]
    measure_by: Optional[str]
    measure_at: Optional[float]

    @property
    def is_open(self) -> bool:
        """A loss with no measure against it. Bars its domain."""
        return self.measure is None


class Treasury:
    """Dorris's ledger: the split, the loss register, and the bar."""

    def __init__(
        self,
        db_path: Path | str = Path("data/exchange_treasury.db"),
        reinvestment_rate: float = DEFAULT_REINVESTMENT_RATE,
    ) -> None:
        if not 0.0 <= reinvestment_rate <= 1.0:
            raise ValueError(
                f"reinvestment_rate must be a share between 0 and 1; got {reinvestment_rate}"
            )
        self._rate = reinvestment_rate
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @property
    def reinvestment_rate(self) -> float:
        return self._rate

    def _create_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settlements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    estimated REAL NOT NULL,
                    realised REAL NOT NULL,
                    variance REAL NOT NULL,
                    reinvested REAL NOT NULL,
                    retained REAL NOT NULL,
                    allocation TEXT,
                    settled_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS losses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    estimated REAL NOT NULL,
                    realised REAL NOT NULL,
                    variance REAL NOT NULL,
                    recorded_at REAL NOT NULL,
                    measure TEXT,
                    measure_by TEXT,
                    measure_at REAL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_losses_open ON losses (domain, measure)"
            )
            self._conn.commit()

    # ── settlement ──────────────────────────────────────────────────────────

    def settle(
        self,
        resource_id: str,
        domain: Domain,
        *,
        estimated: float,
        realised: float,
        allocation: Allocation = Allocation.INFRASTRUCTURE,
    ) -> Settlement:
        """Book a realised outcome, split any gain, register any loss.

        A loss is a shortfall against what the opportunity was estimated at,
        not a negative amount of money -- the estate can realise £400 on a
        £1,000 estimate without ever going below zero, and that is still a
        £600 misjudgement worth a measure. Nothing is reinvested out of a
        shortfall; there is no gain to split.
        """
        if estimated < 0 or realised < 0:
            raise ValueError("estimated and realised must both be non-negative")

        variance = realised - estimated
        now = time.time()

        if variance >= 0:
            reinvested = round(realised * self._rate, 2)
            retained = round(realised - reinvested, 2)
            alloc: Optional[str] = allocation.value
        else:
            # A shortfall funds nothing. Splitting it would reinvest money the
            # estate did not make and report a contribution it did not give.
            reinvested = 0.0
            retained = round(realised, 2)
            alloc = None

        with self._lock:
            self._conn.execute(
                "INSERT INTO settlements (resource_id, domain, estimated, realised, variance, "
                "reinvested, retained, allocation, settled_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    resource_id,
                    domain.value,
                    estimated,
                    realised,
                    variance,
                    reinvested,
                    retained,
                    alloc,
                    now,
                ),
            )
            if variance < 0:
                self._conn.execute(
                    "INSERT INTO losses (resource_id, domain, estimated, realised, variance, "
                    "recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (resource_id, domain.value, estimated, realised, variance, now),
                )
            self._conn.commit()

        if variance < 0:
            logger.warning(
                "Exchange loss registered in %s: estimated %.2f, realised %.2f. "
                "That domain is barred from further proposals until %s records a measure.",
                domain.value,
                estimated,
                realised,
                TAXONOMY_OWNER_TITLE,
            )

        return Settlement(
            resource_id=resource_id,
            domain=domain.value,
            estimated=estimated,
            realised=realised,
            variance=variance,
            reinvested=reinvested,
            retained=retained,
            allocation=alloc,
            settled_at=now,
        )

    # ── loss review ─────────────────────────────────────────────────────────

    def open_losses(self, domain: Optional[Domain] = None) -> List[LossEntry]:
        """Losses with no measure recorded against them."""
        sql = "SELECT * FROM losses WHERE measure IS NULL"
        args: tuple = ()
        if domain is not None:
            sql += " AND domain = ?"
            args = (domain.value,)
        sql += " ORDER BY recorded_at DESC, id DESC"
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [self._row_to_loss(r) for r in rows]

    def is_barred(self, domain: Domain) -> bool:
        """Whether this market is closed to new proposals.

        True while any loss in it is unreviewed. The bar is what makes the
        register a control rather than a report: without it, a domain could
        lose money repeatedly and the only consequence would be more rows.
        """
        return bool(self.open_losses(domain))

    def record_measure(self, loss_id: int, *, measure: str, recorded_by: str) -> LossEntry:
        """Close a loss with the measure taken, lifting the bar on its domain.

        Only the taxonomy owner may do this. A seat clearing its own loss would
        be marking its own homework, and the bar would stop meaning anything
        the moment a domain wanted to keep trading.
        """
        if recorded_by != TAXONOMY_OWNER:
            raise PermissionError(
                f"Only {TAXONOMY_OWNER_TITLE} ({TAXONOMY_OWNER}) reviews Exchange "
                f"losses; {recorded_by!r} cannot close loss {loss_id}. A seat "
                f"clearing its own loss would be marking its own homework."
            )
        if not measure.strip():
            raise ValueError(
                "A loss needs a written measure -- what changes so this does not "
                "recur. Closing one with an empty reason would lift the bar and "
                "record nothing anybody could act on."
            )
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE losses SET measure = ?, measure_by = ?, measure_at = ? "
                "WHERE id = ? AND measure IS NULL",
                (measure, recorded_by, now, loss_id),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                raise ValueError(f"Loss {loss_id} does not exist or already has a measure recorded")
            row = self._conn.execute("SELECT * FROM losses WHERE id = ?", (loss_id,)).fetchone()
        logger.info("Exchange loss %d closed by %s: %s", loss_id, recorded_by, measure)
        return self._row_to_loss(row)

    @staticmethod
    def _row_to_loss(row: sqlite3.Row) -> LossEntry:
        return LossEntry(
            loss_id=row["id"],
            resource_id=row["resource_id"],
            domain=row["domain"],
            estimated=row["estimated"],
            realised=row["realised"],
            variance=row["variance"],
            recorded_at=row["recorded_at"],
            measure=row["measure"],
            measure_by=row["measure_by"],
            measure_at=row["measure_at"],
        )

    # ── position ────────────────────────────────────────────────────────────

    def position(self) -> Dict[str, object]:
        """What the Exchange has returned to the platform, and what it owes."""
        with self._lock:
            totals = self._conn.execute(
                "SELECT COALESCE(SUM(realised), 0) AS realised, "
                "COALESCE(SUM(reinvested), 0) AS reinvested, "
                "COALESCE(SUM(retained), 0) AS retained, "
                "COUNT(*) AS settlements FROM settlements"
            ).fetchone()
            by_allocation = self._conn.execute(
                "SELECT allocation, COALESCE(SUM(reinvested), 0) AS total FROM settlements "
                "WHERE allocation IS NOT NULL GROUP BY allocation"
            ).fetchall()
            open_count = self._conn.execute(
                "SELECT COUNT(*) AS n FROM losses WHERE measure IS NULL"
            ).fetchone()["n"]
            barred = self._conn.execute(
                "SELECT DISTINCT domain FROM losses WHERE measure IS NULL"
            ).fetchall()
        return {
            "reinvestment_rate": self._rate,
            "settlements": totals["settlements"],
            "realised_total": round(totals["realised"], 2),
            "reinvested_total": round(totals["reinvested"], 2),
            "retained_total": round(totals["retained"], 2),
            "reinvested_by_allocation": {
                r["allocation"]: round(r["total"], 2) for r in by_allocation
            },
            "open_losses": open_count,
            "barred_domains": sorted(r["domain"] for r in barred),
            "reviewed_by": TAXONOMY_OWNER_TITLE,
        }
