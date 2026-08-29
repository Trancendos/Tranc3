"""The Arcadian Exchange's opportunity book.

Pulls every sellable resource the estate produces, values each one, puts it
through the eligibility gate, and ranks what survives. This is the "smartly
calculates the potential opportunities, values and profit" half of the external
mandate -- the part that runs before anything is sold, and that
`PassiveRevenueEngine` only ever sees the settled end of.

**It composes with the existing ledger rather than shadowing it.** Realised
income still books through `PassiveRevenueEngine`'s twelve streams; every
resource in the catalogue names the stream it settles into. Recording an
outcome here feeds the realisation ratio and nothing else, so there is one
ledger and one place a number can come from.

**Adaptive in a way that can be checked.** Each source carries a rolling ratio
of realised to estimated value. A source that consistently over-promises loses
confidence in future rankings without anyone editing a table, and the ratio is
readable, so the adaptation can be inspected rather than trusted.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log
from src.exchange.governance import Decision, Ruling, rule
from src.exchange.sources import SELLABLE_RESOURCES, get_resource, validate_catalogue
from src.exchange.valuation import Basis, Valuation, value

logger = logging.getLogger("tranc3.exchange.engine")

DEFAULT_DB_PATH = Path("data/exchange_opportunities.db")

#: How many recent outcomes feed a source's realisation ratio. Short enough
#: that a source which starts pricing accurately recovers within a quarter of
#: normal trading, long enough that one unusual settlement does not swing it.
REALISATION_WINDOW = 20


@dataclass(frozen=True)
class Opportunity:
    """One valued, ruled-on candidate."""

    resource_id: str
    location: str
    owning_seat: str
    revenue_stream: str
    description: str
    valuation: Valuation
    ruling: Ruling

    @property
    def pursuable(self) -> bool:
        """CLEAR and worth money. ESCALATE is not pursuable until signed off."""
        return self.ruling.decision is Decision.CLEAR and self.valuation.net > 0

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe form, with the derived fields a reader needs.

        `priceable` and `risk_adjusted` are properties rather than stored
        values, so a caller reading the serialised book would otherwise
        have to recompute the two things the ranking was sorted on.
        """
        return {
            "resource_id": self.resource_id,
            "location": self.location,
            "owning_seat": self.owning_seat,
            "revenue_stream": self.revenue_stream,
            "description": self.description,
            "valuation": {
                **asdict(self.valuation),
                "basis": self.valuation.basis.value,
                "priceable": self.valuation.priceable,
                "risk_adjusted": round(self.valuation.risk_adjusted, 2),
            },
            "ruling": {
                "decision": self.ruling.decision.value,
                "reason": self.ruling.reason,
                "sign_off": self.ruling.sign_off,
            },
            "pursuable": self.pursuable,
        }


@dataclass(frozen=True)
class Candidate:
    """What a seat proposes selling, and the facts the gate needs to rule.

    Every field the gate consults defaults to the unsafe-to-assume value, so a
    candidate raised without a fact is escalated or refused rather than
    cleared. Omission is not evidence.
    """

    resource_id: str
    units: float = 0.0
    unit_price: Optional[float] = None
    basis: Basis = Basis.NONE
    cost_to_serve: float = 0.0
    aggregation_cohort: Optional[int] = None
    counterparty_authorisation: bool = False
    content_is_own_work: Optional[bool] = None


class OpportunityEngine:
    """Values and ranks what the estate could sell, and learns from outcomes."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        """Open the outcome store, refusing to start on a bad catalogue."""
        problems = validate_catalogue()
        if problems:
            # Refusing to start is deliberate. An opportunity book built on a
            # catalogue that references a Location the platform no longer has,
            # or a revenue stream the ledger will not accept, produces numbers
            # that look authoritative and settle into nothing.
            raise ValueError(
                "The sellable-resource catalogue is inconsistent, so the "
                "opportunity engine will not start:\n  " + "\n  ".join(problems)
            )
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        """Close the connection. Safe to call once; the engine is done after."""
        with self._lock:
            self._conn.close()

    def _create_schema(self) -> None:
        """Two tables: settled outcomes, and point-in-time book snapshots.

        Outcomes are append-only -- a realisation ratio that could be
        edited after the fact would not be evidence of anything.
        """
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_id TEXT NOT NULL,
                    estimated REAL NOT NULL,
                    realised REAL NOT NULL,
                    recorded_at REAL NOT NULL,
                    note TEXT NOT NULL DEFAULT ''
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_outcomes_resource "
                "ON outcomes (resource_id, recorded_at DESC)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS book_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    taken_at REAL NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    # ── adaptation ──────────────────────────────────────────────────────────

    def realisation_ratio(self, resource_id: str) -> float:
        """Realised over estimated across this source's recent outcomes.

        Returns 1.0 with no history: an unproven source is neither penalised
        nor flattered, and its confidence comes from its pricing basis alone.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT estimated, realised FROM outcomes WHERE resource_id = ? "
                "ORDER BY recorded_at DESC, id DESC LIMIT ?",
                (resource_id, REALISATION_WINDOW),
            ).fetchall()
        estimated = sum(r["estimated"] for r in rows)
        if not rows or estimated <= 0:
            return 1.0
        return sum(r["realised"] for r in rows) / estimated

    def record_outcome(
        self, resource_id: str, *, estimated: float, realised: float, note: str = ""
    ) -> float:
        """Book what an opportunity was thought to be worth against what it made.

        Returns the source's updated realisation ratio. This does not book
        income -- `PassiveRevenueEngine` owns the ledger, and duplicating it
        here would create two answers to "what did we earn".
        """
        if get_resource(resource_id) is None:
            raise ValueError(f"{resource_id!r} is not a resource in the catalogue")
        if estimated < 0 or realised < 0:
            raise ValueError("estimated and realised must both be non-negative")
        with self._lock:
            self._conn.execute(
                "INSERT INTO outcomes (resource_id, estimated, realised, recorded_at, note) "
                "VALUES (?, ?, ?, ?, ?)",
                (resource_id, estimated, realised, time.time(), note),
            )
            self._conn.commit()
        ratio = self.realisation_ratio(resource_id)
        # Every value here reaches the log from a request body. `resource_id`
        # is already constrained to the catalogue by the check above and the
        # two amounts are floats, so none of them can carry a newline today --
        # but "today" is doing load-bearing work in that sentence, and the
        # estate has a sanitiser for exactly this. Composed into one string so
        # a single barrier covers all four rather than three of them.
        logger.info(
            "Exchange outcome recorded: %s",
            sanitize_for_log(
                f"{resource_id} estimated {estimated:.2f}, realised {realised:.2f}, "
                f"realisation ratio now {ratio:.3f}"
            ),
        )
        return ratio

    # ── the book ────────────────────────────────────────────────────────────

    def evaluate(self, candidate: Candidate) -> Opportunity:
        """Value one candidate and rule on it."""
        resource = get_resource(candidate.resource_id)
        if resource is None:
            raise ValueError(f"{candidate.resource_id!r} is not a resource in the catalogue")

        valuation = value(
            resource.resource_id,
            units=candidate.units,
            unit_price=candidate.unit_price,
            basis=candidate.basis,
            cost_to_serve=candidate.cost_to_serve,
            realisation_ratio=self.realisation_ratio(resource.resource_id),
        )
        ruling = rule(
            resource,
            estimated_value=valuation.net,
            aggregation_cohort=candidate.aggregation_cohort,
            counterparty_authorisation=candidate.counterparty_authorisation,
            content_is_own_work=candidate.content_is_own_work,
        )
        return Opportunity(
            resource_id=resource.resource_id,
            location=resource.location,
            owning_seat=resource.owning_seat,
            revenue_stream=resource.revenue_stream,
            description=resource.description,
            valuation=valuation,
            ruling=ruling,
        )

    def build_book(self, candidates: List[Candidate]) -> Dict[str, Any]:
        """Value, rule on and rank a set of candidates.

        Refused opportunities are returned in their own list rather than merged
        into the ranking. Ranking something the gate refused would put a
        forbidden sale in a sorted list of things to do next, which is how a
        gate that "reports" becomes a gate that does not hold.
        """
        evaluated = [self.evaluate(c) for c in candidates]

        refused = [o for o in evaluated if o.ruling.decision is Decision.REFUSED]
        escalated = [o for o in evaluated if o.ruling.decision is Decision.ESCALATE]
        clear = [o for o in evaluated if o.ruling.decision is Decision.CLEAR]
        unpriced = [o for o in evaluated if not o.valuation.priceable]

        ranked = sorted(
            (o for o in clear if o.valuation.priceable),
            key=lambda o: o.valuation.risk_adjusted,
            reverse=True,
        )

        return {
            "generated_at": time.time(),
            "candidates_considered": len(evaluated),
            # Only CLEAR, priceable opportunities contribute. An escalated or
            # refused one is not pipeline until somebody signs it off.
            "pursuable_value": round(
                sum(o.valuation.net for o in ranked if o.valuation.net > 0), 2
            ),
            "risk_adjusted_value": round(
                sum(o.valuation.risk_adjusted for o in ranked if o.valuation.net > 0), 2
            ),
            "ranked": [o.to_dict() for o in ranked],
            "escalated": [o.to_dict() for o in escalated],
            "refused": [o.to_dict() for o in refused],
            "unpriced": [o.to_dict() for o in unpriced],
        }

    def snapshot_book(self, book: Dict[str, Any]) -> int:
        """Persist a book so a later reading can be compared with this one."""
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO book_snapshots (taken_at, payload) VALUES (?, ?)",
                (book.get("generated_at", time.time()), json.dumps(book, default=str)),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    # ── inventory ───────────────────────────────────────────────────────────

    def inventory(self) -> Dict[str, Any]:
        """What the estate could sell, before anyone proposes a price.

        The question that comes before any valuation: what is even on the
        shelf, who owns selling it, and what is not simply sellable.
        """
        return {
            "resources": [
                {
                    "resource_id": r.resource_id,
                    "location": r.location,
                    "description": r.description,
                    "owning_seat": r.owning_seat,
                    "revenue_stream": r.revenue_stream,
                    "unit": r.unit,
                    "constraint": r.constraint.value,
                    "constraint_note": r.constraint_note,
                    "realisation_ratio": round(self.realisation_ratio(r.resource_id), 4),
                }
                for r in SELLABLE_RESOURCES
            ],
            "total": len(SELLABLE_RESOURCES),
        }


_engine: Optional[OpportunityEngine] = None
_engine_lock = threading.Lock()


def get_engine() -> OpportunityEngine:
    """Module-level singleton, matching the `get_<x>()` pattern used across
    this codebase (`get_registry()`, `get_devocity()`, `get_library()`)."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = OpportunityEngine()
    return _engine
