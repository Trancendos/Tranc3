# src/compliance/waivers.py — Governance waivers/exceptions.
#
# A waiver records a deliberate, time-boxed exception to a standard, policy, or
# control — e.g. "the Matrix Suites review cadence for suite X is waived for 30
# days while a dependent system is migrated" or "charter Y's approval_required
# constraint is waived for this specific escalation record". Modeled after the
# ARB/ISSC "waiver must be time-boxed, justified, and linked to compensating
# controls" pattern: an exception with no expiry date, no reason, and no
# accountable approver is not a waiver, it's just an unmonitored gap.
#
# Deliberately NOT a CAB-style pending/approve/reject workflow (see cab_gate.py):
# a waiver is granted at creation time by its approver, since in the ARB/ISSC
# process the waiver request record *is* the approval record — there is no
# separate "pending waiver" state to model. What does need tracking is what
# happens *after* grant: revocation, and expiry.
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log
from src.observability.observatory import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    get_observatory,
)

logger = logging.getLogger("tranc3.compliance.waivers")

_DB_PATH = Path("./data/waivers.db")

# Observatory service identity for this module — "trancendos-*", not "tranc3-*":
# this is a platform-level governance subsystem, not part of the Tier-3 model
# engine (see CLAUDE.md's naming rule and Qodo rule 2441126).
_SERVICE = "trancendos-waivers"


class WaiverError(Exception):
    """Base class for waiver errors."""


class WaiverNotFoundError(WaiverError):
    """No waiver exists for the given waiver_id."""


class WaiverValidationError(WaiverError):
    """The waiver request or requested transition is invalid."""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS waivers (
            waiver_id              TEXT PRIMARY KEY,
            subject                TEXT NOT NULL,
            justification          TEXT NOT NULL,
            compensating_controls  TEXT NOT NULL DEFAULT '[]',
            requestor               TEXT NOT NULL,
            approver               TEXT NOT NULL,
            granted_at             REAL NOT NULL,
            effective_from         REAL NOT NULL,
            expires_on             REAL NOT NULL,
            revoked_at             REAL,
            revoked_by             TEXT,
            revoke_reason          TEXT,
            expiry_notified        INTEGER NOT NULL DEFAULT 0,
            expiry_claim_expires_at REAL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_waivers_expires_on ON waivers (expires_on)")
    conn.commit()


with _get_conn() as _conn:
    _init_db(_conn)


# ---------------------------------------------------------------------------
# Waiver
# ---------------------------------------------------------------------------


@dataclass
class Waiver:
    waiver_id: str
    subject: str
    justification: str
    compensating_controls: List[str]
    requestor: str
    approver: str
    granted_at: float
    effective_from: float
    expires_on: float
    revoked_at: Optional[float] = None
    revoked_by: Optional[str] = None
    revoke_reason: Optional[str] = None
    expiry_notified: bool = False

    @property
    def status(self) -> str:
        """Computed, not stored — a waiver's status is a pure function of 'now'
        plus whether it was explicitly revoked, so it can never drift out of sync
        with a clock the way a persisted status column could."""
        if self.revoked_at is not None:
            return "revoked"
        now = time.time()
        if now < self.effective_from:
            return "pending"
        if now >= self.expires_on:
            return "expired"
        return "active"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "waiver_id": self.waiver_id,
            "subject": self.subject,
            "justification": self.justification,
            "compensating_controls": self.compensating_controls,
            "requestor": self.requestor,
            "approver": self.approver,
            "granted_at": self.granted_at,
            "effective_from": self.effective_from,
            "expires_on": self.expires_on,
            "revoked_at": self.revoked_at,
            "revoked_by": self.revoked_by,
            "revoke_reason": self.revoke_reason,
            "status": self.status,
        }
        return d


def _row_to_waiver(row: sqlite3.Row) -> Waiver:
    return Waiver(
        waiver_id=row["waiver_id"],
        subject=row["subject"],
        justification=row["justification"],
        compensating_controls=json.loads(row["compensating_controls"]),
        requestor=row["requestor"],
        approver=row["approver"],
        granted_at=row["granted_at"],
        effective_from=row["effective_from"],
        expires_on=row["expires_on"],
        revoked_at=row["revoked_at"],
        revoked_by=row["revoked_by"],
        revoke_reason=row["revoke_reason"],
        expiry_notified=bool(row["expiry_notified"]),
    )


def _emit(event_type: str, waiver: Waiver, severity: EventSeverity, **extra: Any) -> AuditEvent:
    return get_observatory().record(
        event_type,
        actor=waiver.approver,
        target=waiver.waiver_id,
        category=EventCategory.GOVERNANCE,
        severity=severity,
        service=_SERVICE,
        metadata={"subject": waiver.subject, "status": waiver.status, **extra},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register_waiver(
    subject: str,
    justification: str,
    requestor: str,
    approver: str,
    expires_on: float,
    compensating_controls: Optional[List[str]] = None,
    effective_from: Optional[float] = None,
) -> Waiver:
    """Grant a new waiver. Time-boxed by design — expires_on is required, not
    optional, matching the ARB policy this models ("waivers must be time-boxed").
    """
    for name, value in (
        ("subject", subject),
        ("justification", justification),
        ("requestor", requestor),
        ("approver", approver),
    ):
        if not value or not value.strip():
            raise WaiverValidationError(f"{name} must not be blank")

    now = time.time()
    effective_from = now if effective_from is None else effective_from
    if expires_on <= effective_from:
        raise WaiverValidationError("expires_on must be after effective_from")

    controls = list(compensating_controls or [])
    if not all(isinstance(c, str) for c in controls):
        raise WaiverValidationError("compensating_controls must be a list of strings")

    waiver = Waiver(
        waiver_id=f"WVR-{uuid.uuid4().hex[:8].upper()}",
        subject=subject.strip(),
        justification=justification.strip(),
        compensating_controls=controls,
        requestor=requestor.strip(),
        approver=approver.strip(),
        granted_at=now,
        effective_from=effective_from,
        expires_on=expires_on,
    )

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO waivers
                (waiver_id, subject, justification, compensating_controls, requestor,
                 approver, granted_at, effective_from, expires_on)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                waiver.waiver_id,
                waiver.subject,
                waiver.justification,
                json.dumps(waiver.compensating_controls),
                waiver.requestor,
                waiver.approver,
                waiver.granted_at,
                waiver.effective_from,
                waiver.expires_on,
            ),
        )
        conn.commit()

    logger.info(
        "Waiver granted | waiver_id=%s subject=%s approver=%s expires_on=%s",
        sanitize_for_log(waiver.waiver_id),  # codeql[py/log-injection]
        sanitize_for_log(waiver.subject),  # codeql[py/log-injection]
        sanitize_for_log(waiver.approver),  # codeql[py/log-injection]
        waiver.expires_on,
    )
    _emit("governance.waiver.granted", waiver, EventSeverity.WARNING)
    return waiver


def get_waiver(waiver_id: str) -> Waiver:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM waivers WHERE waiver_id = ?", (waiver_id,)).fetchone()
    if row is None:
        raise WaiverNotFoundError(f"No waiver found for waiver_id={waiver_id!r}")
    return _row_to_waiver(row)


def list_waivers(status: Optional[str] = None) -> List[Waiver]:
    """Return all waivers, optionally filtered by computed status
    ('pending' | 'active' | 'expired' | 'revoked')."""
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM waivers ORDER BY granted_at DESC").fetchall()
    waivers = [_row_to_waiver(r) for r in rows]
    if status is not None:
        waivers = [w for w in waivers if w.status == status]
    return waivers


def revoke_waiver(waiver_id: str, revoked_by: str, reason: str) -> Waiver:
    """Explicitly end a waiver before its natural expiry. Only a currently
    'active' or 'pending' waiver can be revoked — revoking an already-expired
    or already-revoked one would misrepresent the audit trail (the waiver ended
    for a different reason than the one being recorded now).

    cubic P1: the original check-then-write (get_waiver() status check, then an
    unconditional UPDATE) was a TOCTOU race — a waiver could cross expires_on, or
    a second concurrent revoke() call could land, between the read and the write.
    The UPDATE's WHERE clause now re-asserts both conditions atomically, and a
    zero-row result (meaning either race actually happened) raises instead of
    silently 'succeeding' over a decision that was no longer valid to make.
    """
    if not revoked_by or not revoked_by.strip():
        raise WaiverValidationError("revoked_by must not be blank")

    waiver = get_waiver(waiver_id)
    if waiver.status not in ("active", "pending"):
        raise WaiverValidationError(
            f"Waiver {waiver_id!r} cannot be revoked from status {waiver.status!r}"
        )

    now = time.time()
    with _get_conn() as conn:
        cur = conn.execute(
            "UPDATE waivers SET revoked_at = ?, revoked_by = ?, revoke_reason = ? "
            "WHERE waiver_id = ? AND revoked_at IS NULL AND expires_on > ?",
            (now, revoked_by.strip(), reason, waiver_id, now),
        )
        conn.commit()
        if cur.rowcount != 1:
            raise WaiverValidationError(
                f"Waiver {waiver_id!r} was already revoked or has since expired"
            )

    waiver.revoked_at = now
    waiver.revoked_by = revoked_by.strip()
    waiver.revoke_reason = reason
    logger.info(
        "Waiver revoked | waiver_id=%s revoked_by=%s",
        sanitize_for_log(waiver_id),  # codeql[py/log-injection]
        sanitize_for_log(revoked_by),  # codeql[py/log-injection]
    )
    _emit("governance.waiver.revoked", waiver, EventSeverity.WARNING, reason=reason)
    return waiver


_EXPIRY_CLAIM_LEASE_SECONDS = 60.0


def emit_expiry_events() -> List[AuditEvent]:
    """Scan for waivers that have crossed expires_on and haven't been notified
    yet, emit one governance.waiver.expired event per waiver, and mark them
    notified — a waiver only expires once, so unlike Matrix Suites' per-calendar-
    day overdue throttle this is a one-shot latch, not a recurring window.
    Intended to be called on a cadence (e.g. by ChronosSphere), same pattern as
    matrix_suites.emit_overdue_events().

    cubic P1/P2/P1: three rounds on this function's atomicity —
    1. The original version SELECTed candidates, bulk-UPDATEd them all notified,
       then emitted: two concurrent callers could both SELECT the same row
       before either UPDATE committed (duplicate emission).
    2. Claiming each row individually via `UPDATE ... WHERE expiry_notified = 0`
       (rowcount proving sole ownership) fixed the duplicate-emission race, and
       rolling the claim back in a `except Exception` handler recovered from a
       *Python* exception during _emit() — but not from the *process* exiting
       between the claim commit and the _emit() call (a crash, not a raise):
       expiry_notified=1 would survive in SQLite with no event ever recorded,
       permanently.
    3. The claim is now a time-boxed lease (expiry_claim_expires_at), not a
       one-way flag: a row is only truly done once expiry_notified is set,
       which only happens *after* _emit() returns successfully. A crash between
       claiming and emitting leaves expiry_notified=0 with a lease that expires
       within _EXPIRY_CLAIM_LEASE_SECONDS, so the next scan reclaims it instead
       of leaking it forever — closing the gap a plain exception handler can't
       reach, without reintroducing the original concurrent-duplicate race.
    """
    now = time.time()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM waivers WHERE expires_on <= ? AND revoked_at IS NULL "
            "AND expiry_notified = 0 "
            "AND (expiry_claim_expires_at IS NULL OR expiry_claim_expires_at < ?)",
            (now, now),
        ).fetchall()
    candidates = [_row_to_waiver(r) for r in rows]

    events = []
    for waiver in candidates:
        claim_now = time.time()
        lease_until = claim_now + _EXPIRY_CLAIM_LEASE_SECONDS
        with _get_conn() as conn:
            cur = conn.execute(
                "UPDATE waivers SET expiry_claim_expires_at = ? "
                "WHERE waiver_id = ? AND expiry_notified = 0 "
                "AND (expiry_claim_expires_at IS NULL OR expiry_claim_expires_at < ?)",
                (lease_until, waiver.waiver_id, claim_now),
            )
            conn.commit()
            if cur.rowcount != 1:
                continue  # another caller already holds (or just took) the lease

        try:
            event = _emit("governance.waiver.expired", waiver, EventSeverity.CRITICAL)
        except Exception:
            # Don't bother clearing the lease — letting it expire naturally in
            # _EXPIRY_CLAIM_LEASE_SECONDS is simpler and behaves identically to
            # the crash case this whole redesign exists to handle.
            logger.warning(
                "Waiver expiry event emission failed for waiver_id=%s — "
                "reclaimable after the lease expires",
                sanitize_for_log(waiver.waiver_id),  # codeql[py/log-injection]
            )
            continue

        with _get_conn() as conn:
            conn.execute(
                "UPDATE waivers SET expiry_notified = 1 WHERE waiver_id = ?",
                (waiver.waiver_id,),
            )
            conn.commit()
        events.append(event)
    return events
