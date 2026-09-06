"""What each seat is allowed to reason about, and how that changes.

Every external seat starts with one domain it was designed for. It can widen
that horizon -- but only into a domain adjacent to one it has already proven
itself in, and only by proving itself first. Widening is earned from settled
outcomes, not granted, and it reverses when the evidence stops supporting it.

The alternative designs both fail in an obvious way. A fixed horizon means a
seat that has become genuinely good at pricing storage still cannot say
anything about compute, which is the same market with a different unit. An
unbounded one means every seat opines on everything, the ranking fills with
confident guesses from seats with no track record in that market, and the
realisation ratios that were supposed to calibrate it get averaged across
domains until they mean nothing.

So: bounded, earned, and reversible. A seat's horizon is a claim about where
its judgement has been tested, and the evidence for it is on record.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.exchange.domains import (
    CAPITAL_AT_RISK,
    TAXONOMY_OWNER,
    TAXONOMY_OWNER_TITLE,
    Domain,
    adjacent_to,
)

logger = logging.getLogger("tranc3.exchange.expertise")

#: Settled outcomes a seat needs in a domain before that domain can vouch for
#: an expansion out of it. Below this, a high ratio is noise -- two lucky
#: settlements should not unlock a new market.
MIN_OUTCOMES_TO_EXPAND = 8

#: Realisation ratio a seat must sustain in a domain to expand out of it. Set
#: where it is because the ratio is realised-over-estimated: 0.8 means the
#: seat's estimates in that market have been landing within a fifth of the
#: truth, which is the point at which its judgement is worth extending.
EXPANSION_THRESHOLD = 0.80

#: Below this in a domain the seat loses it, unless it is the primary. A seat
#: is never stripped of what it was designed for -- that would leave the
#: Location with a mandate nobody holds. It is stripped of what it reached for.
CONTRACTION_THRESHOLD = 0.50

#: Settled outcomes before contraction can trigger. Same reasoning as the
#: expansion minimum, in the other direction: one bad settlement is not a
#: verdict.
MIN_OUTCOMES_TO_CONTRACT = 5

#: seat_id -> the domain it was designed for. Mirrors EXTERNAL_SEATS in
#: src/entities/platform.py; the Chief Revenue Officer has no primary domain
#: because the seat ranks what the others raise rather than proposing itself.
PRIMARY_DOMAINS: Dict[str, Domain] = {
    "ann-porter-external": Domain.CAPACITY,
    "george-porter-external": Domain.COMPUTE,
    "edward-porter-external": Domain.EXPERT_SERVICES,
    "james-porter-external": Domain.DATA_PRODUCTS,
}


@dataclass(frozen=True)
class HorizonChange:
    """One recorded widening or narrowing of a seat's horizon."""

    changed_at: float
    seat_id: str
    domain: str
    direction: str
    evidence: str


@dataclass(frozen=True)
class Horizon:
    """Where one seat's judgement is currently accepted."""

    seat_id: str
    primary: Optional[Domain]
    domains: Tuple[Domain, ...]

    def covers(self, domain: Domain) -> bool:
        return domain in self.domains

    @property
    def expanded_into(self) -> Tuple[Domain, ...]:
        """Domains held beyond the one the seat was designed for."""
        return tuple(d for d in self.domains if d != self.primary)


class ExpertiseRegistry:
    """Tracks each seat's horizon and the evidence that moved it.

    Per-domain outcomes are recorded here rather than reusing the engine's
    per-resource realisation ratio, because they answer different questions.
    The engine asks "how reliable have estimates for THIS resource been", which
    calibrates a valuation. This asks "how reliable has THIS SEAT been in THIS
    MARKET", which decides whether the seat may speak about that market at all.
    Averaging one into the other would let a seat's strong record on storage
    unlock compute without it ever having priced compute.
    """

    def __init__(self, db_path: Path | str = Path("data/exchange_expertise.db")) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _create_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seat_domain_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seat_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    estimated REAL NOT NULL,
                    realised REAL NOT NULL,
                    recorded_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_seat_domain "
                "ON seat_domain_outcomes (seat_id, domain, recorded_at DESC)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS granted_domains (
                    seat_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    granted_at REAL NOT NULL,
                    evidence TEXT NOT NULL,
                    PRIMARY KEY (seat_id, domain)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS horizon_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    changed_at REAL NOT NULL,
                    seat_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    evidence TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    # ── evidence ────────────────────────────────────────────────────────────

    def record_outcome(
        self, seat_id: str, domain: Domain, *, estimated: float, realised: float
    ) -> None:
        """Book one settled outcome against a seat's record in a market."""
        if estimated < 0 or realised < 0:
            raise ValueError("estimated and realised must both be non-negative")
        with self._lock:
            self._conn.execute(
                "INSERT INTO seat_domain_outcomes "
                "(seat_id, domain, estimated, realised, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (seat_id, domain.value, estimated, realised, time.time()),
            )
            self._conn.commit()

    def accuracy(self, seat_id: str, domain: Domain, window: int = 20) -> Tuple[float, int]:
        """(realisation ratio, settled outcomes) for one seat in one market.

        Returns (1.0, 0) with no history -- an untested seat is neither
        penalised nor credited, and the count is returned alongside so a caller
        can tell "perfect record" from "no record", which the ratio alone
        cannot.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT estimated, realised FROM seat_domain_outcomes "
                "WHERE seat_id = ? AND domain = ? ORDER BY recorded_at DESC, id DESC LIMIT ?",
                (seat_id, domain.value, window),
            ).fetchall()
        if not rows:
            return 1.0, 0
        estimated = sum(r["estimated"] for r in rows)
        if estimated <= 0:
            return 1.0, len(rows)
        return sum(r["realised"] for r in rows) / estimated, len(rows)

    # ── horizon ─────────────────────────────────────────────────────────────

    def horizon(self, seat_id: str) -> Horizon:
        """Where this seat's judgement is currently accepted."""
        primary = PRIMARY_DOMAINS.get(seat_id)
        domains = {primary} if primary else set()
        with self._lock:
            rows = self._conn.execute(
                "SELECT domain FROM granted_domains WHERE seat_id = ?", (seat_id,)
            ).fetchall()
        domains.update(Domain(r["domain"]) for r in rows)
        return Horizon(
            seat_id=seat_id,
            primary=primary,
            domains=tuple(sorted(domains, key=lambda d: d.value)),
        )

    def review(self, seat_id: str) -> List[HorizonChange]:
        """Re-derive one seat's horizon from its record, and apply the change.

        Called after outcomes settle. Widening and narrowing are the same
        operation looked at from either end, so they are decided together -- a
        seat that has just earned one market while losing another should end
        the review holding the right set, not whichever the caller happened to
        ask about.
        """
        horizon = self.horizon(seat_id)
        changes: List[HorizonChange] = []
        now = time.time()

        # ── contraction first: a domain that no longer holds up cannot then
        # vouch for an expansion out of itself in the same review.
        for domain in horizon.expanded_into:
            ratio, count = self.accuracy(seat_id, domain)
            if count >= MIN_OUTCOMES_TO_CONTRACT and ratio < CONTRACTION_THRESHOLD:
                evidence = (
                    f"realisation ratio {ratio:.2f} over {count} settled outcomes, "
                    f"below the {CONTRACTION_THRESHOLD:.2f} floor"
                )
                self._revoke(seat_id, domain, evidence, now)
                changes.append(HorizonChange(now, seat_id, domain.value, "narrowed", evidence))

        horizon = self.horizon(seat_id)

        # ── expansion: into a domain adjacent to one already proven.
        for held in horizon.domains:
            ratio, count = self.accuracy(seat_id, held)
            if count < MIN_OUTCOMES_TO_EXPAND or ratio < EXPANSION_THRESHOLD:
                continue
            for candidate in adjacent_to(held):
                if candidate in horizon.domains:
                    continue
                if candidate in CAPITAL_AT_RISK:
                    # Never reached by earning. See domains.CAPITAL_AT_RISK:
                    # being wrong here spends capital the platform already has,
                    # and the activity is regulated. A person assigns it.
                    continue
                if self._lost_and_not_recovered(seat_id, candidate):
                    # A neighbour's strong record cannot hand back a market
                    # this seat lost on its own record there. Without this the
                    # contraction above re-granted the same domain in the same
                    # review, which made the whole mechanism decorative --
                    # found by exercising it rather than by reading it.
                    continue
                evidence = (
                    f"realisation ratio {ratio:.2f} over {count} settled outcomes in "
                    f"{held.value}, which is adjacent to {candidate.value}"
                )
                self._grant(seat_id, candidate, evidence, now)
                changes.append(HorizonChange(now, seat_id, candidate.value, "widened", evidence))

        for change in changes:
            logger.info(
                "Exchange horizon %s: %s %s %s (%s)",
                change.direction,
                change.seat_id,
                "into" if change.direction == "widened" else "out of",
                change.domain,
                change.evidence,
            )
        return changes

    def _lost_and_not_recovered(self, seat_id: str, domain: Domain) -> bool:
        """Whether this seat was narrowed out of a domain and has not earned it back.

        Getting a lost market back is about the record IN that market, not
        about a neighbour's. A seat whose compute estimates were landing at
        0.30 does not become trustworthy on compute because its storage
        estimates are strong -- those are different price models. So the bar
        is the seat's own compute ratio recovering above the expansion
        threshold, which it can only do by settling more compute outcomes.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT direction FROM horizon_changes WHERE seat_id = ? AND domain = ? "
                "ORDER BY changed_at DESC, id DESC LIMIT 1",
                (seat_id, domain.value),
            ).fetchone()
        if row is None or row["direction"] != "narrowed":
            return False
        ratio, count = self.accuracy(seat_id, domain)
        return not (count >= MIN_OUTCOMES_TO_EXPAND and ratio >= EXPANSION_THRESHOLD)

    def assign(self, seat_id: str, domain: Domain, *, assigned_by: str, reason: str) -> None:
        """Put a seat into a domain it cannot reach by earning.

        The only route into a capital-at-risk domain, and deliberately manual.
        Owner-gated for the same reason reclassify() and record_measure() are:
        without the check, a seat could pass its own id as `assigned_by` and
        grant itself TREASURY outright -- which would make the two defences
        keeping treasury unreachable by earning (adjacency isolation and the
        CAPITAL_AT_RISK skip in review()) decorative, since the front door
        was open the whole time. Verified by reproducing it before fixing.
        """
        if assigned_by != TAXONOMY_OWNER:
            raise PermissionError(
                f"Only {TAXONOMY_OWNER_TITLE} ({TAXONOMY_OWNER}) may place a seat "
                f"into a market it cannot earn; {assigned_by!r} cannot assign "
                f"{domain.value} to {seat_id!r}. A seat assigning itself a domain "
                f"is the widening this registry exists to prevent."
            )
        if not reason.strip():
            raise ValueError("A manual horizon assignment needs a written reason")
        evidence = f"assigned by {assigned_by}: {reason}"
        self._grant(seat_id, domain, evidence, time.time())
        logger.info("Exchange horizon assigned: %s -> %s (%s)", seat_id, domain.value, evidence)

    def _grant(self, seat_id: str, domain: Domain, evidence: str, now: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO granted_domains "
                "(seat_id, domain, granted_at, evidence) VALUES (?, ?, ?, ?)",
                (seat_id, domain.value, now, evidence),
            )
            self._conn.execute(
                "INSERT INTO horizon_changes "
                "(changed_at, seat_id, domain, direction, evidence) VALUES (?, ?, ?, ?, ?)",
                (now, seat_id, domain.value, "widened", evidence),
            )
            self._conn.commit()

    def _revoke(self, seat_id: str, domain: Domain, evidence: str, now: float) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM granted_domains WHERE seat_id = ? AND domain = ?",
                (seat_id, domain.value),
            )
            self._conn.execute(
                "INSERT INTO horizon_changes "
                "(changed_at, seat_id, domain, direction, evidence) VALUES (?, ?, ?, ?, ?)",
                (now, seat_id, domain.value, "narrowed", evidence),
            )
            self._conn.commit()

    def changes(self, seat_id: Optional[str] = None, limit: int = 100) -> List[HorizonChange]:
        """Recorded horizon movements, newest first."""
        # Two complete literal queries rather than one built by concatenation.
        # Every value still travels as a bound parameter either way, so this is
        # not a behaviour change -- but a SELECT assembled from string pieces
        # trips bandit's B608 on sight, and a reader then has to reconstruct the
        # statement to satisfy themselves it is safe. Two readable literals cost
        # four lines and remove the question.
        if seat_id:
            sql = (
                "SELECT changed_at, seat_id, domain, direction, evidence "
                "FROM horizon_changes WHERE seat_id = ? "
                "ORDER BY changed_at DESC, id DESC LIMIT ?"
            )
            args: tuple = (seat_id, limit)
        else:
            sql = (
                "SELECT changed_at, seat_id, domain, direction, evidence "
                "FROM horizon_changes "
                "ORDER BY changed_at DESC, id DESC LIMIT ?"
            )
            args = (limit,)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [
            HorizonChange(
                changed_at=r["changed_at"],
                seat_id=r["seat_id"],
                domain=r["domain"],
                direction=r["direction"],
                evidence=r["evidence"],
            )
            for r in rows
        ]
