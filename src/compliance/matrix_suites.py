# src/compliance/matrix_suites.py
# Matrix Suites — Observatory event emission (Magna Carta Stage 7.2)
#
# Reads compliance/magna-carta/compliance/matrix_suites.yaml (the Magna Carta submodule's
# machine-readable Suite registry — docs/governance/MATRIX-SUITES.md) and emits the four
# suite-lifecycle events that doc's §4 promises, through the same Observatory.record() path
# already used by src/capacity/guard.py's capacity.threshold_crossed events:
#
#   governance.suite.<name>.review.completed  — a steward closes a cadence review
#   governance.suite.<name>.review.overdue    — next_review passed without one
#   governance.suite.<name>.matrix.changed    — a member matrix file changed (CI-detected)
#   governance.suite.<name>.escalated         — an item moved up the escalation chain
#
# This module is read-only against the registry: it never writes matrix_suites.yaml (that
# file is owned by the Magna Carta repo). "Review completed" advances no date here — the
# actual next_review value is a Magna Carta-side edit; this module only reports the event.

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a standard project dependency
    yaml = None  # type: ignore[assignment]

from src.observability.observatory import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    Observatory,
    get_observatory,
)

logger = logging.getLogger("tranc3.compliance.matrix_suites")

_DEFAULT_MATRIX_SUITES_PATH = "./compliance/magna-carta/compliance/matrix_suites.yaml"


def _default_path() -> str:
    """Read MATRIX_SUITES_PATH at call time, not at import time — so tests
    (and any runtime env change) that set it via monkeypatch/os.environ take
    effect without needing a module reload."""
    return os.getenv("MATRIX_SUITES_PATH", _DEFAULT_MATRIX_SUITES_PATH)


class MatrixSuitesError(ValueError):
    """Raised for unknown suite/matrix/role identifiers or a malformed registry."""


@dataclass
class SuiteHealth:
    suite_id: str
    name: str
    pillar: str
    steward_ai: str
    steward_location: str
    review_cadence: str
    next_review: str
    overdue: bool
    days_overdue: int
    event_prefix: str
    matrix_count: int


def _event_prefix(suite: Dict[str, Any]) -> str:
    """observatory_events is stored as e.g. 'governance.suite.financial.*'."""
    raw = suite.get("observatory_events", "")
    return raw[:-2] if raw.endswith(".*") else raw.rstrip(".")


def load_suites(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load the raw `suites` list from matrix_suites.yaml. Returns [] if the
    registry isn't present yet (e.g. submodule not checked out) rather than
    raising — suite events are additive observability, not a startup gate."""
    if yaml is None:
        raise ImportError("PyYAML is required: pip install pyyaml")

    p = Path(path or _default_path())
    if not p.is_file():
        logger.warning("Matrix Suites registry not found at %s", p)
        return []

    with p.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}

    suites = doc.get("suites", [])
    if not isinstance(suites, list):
        raise MatrixSuitesError("matrix_suites.yaml: 'suites' must be a list")
    return suites


def _find_suite(suites: List[Dict[str, Any]], suite_id: str) -> Dict[str, Any]:
    for suite in suites:
        if suite.get("suite_id") == suite_id:
            return suite
    raise MatrixSuitesError(f"Unknown suite_id: {suite_id!r}")


def list_suite_health(
    path: Optional[str] = None, today: Optional[date] = None
) -> List[SuiteHealth]:
    """Compute per-suite health (overdue reviews) from the registry."""
    today = today or datetime.utcnow().date()
    results: List[SuiteHealth] = []
    for suite in load_suites(path):
        next_review_str = suite.get("next_review", "")
        overdue = False
        days_overdue = 0
        try:
            next_review_date = datetime.strptime(next_review_str, "%Y-%m-%d").date()
            if next_review_date < today:
                overdue = True
                days_overdue = (today - next_review_date).days
        except ValueError:
            logger.warning(
                "Suite %s has an unparseable next_review value: %r",
                suite.get("suite_id"),
                next_review_str,
            )
        results.append(
            SuiteHealth(
                suite_id=suite.get("suite_id", ""),
                name=suite.get("name", ""),
                pillar=suite.get("pillar", ""),
                steward_ai=suite.get("steward_ai", ""),
                steward_location=suite.get("steward_location", ""),
                review_cadence=suite.get("review_cadence", ""),
                next_review=next_review_str,
                overdue=overdue,
                days_overdue=days_overdue,
                event_prefix=_event_prefix(suite),
                matrix_count=len(suite.get("matrices", []) or []),
            )
        )
    return results


# Per-suite date of the last emitted overdue event, so a repeatedly-polled
# check (e.g. a ChronosSphere cron hitting /compliance/suites/check-overdue)
# doesn't flood the Observatory with a duplicate event every tick.
_last_overdue_emit: Dict[str, date] = {}
_last_overdue_emit_lock = threading.Lock()


def emit_overdue_events(
    observatory: Optional[Observatory] = None,
    path: Optional[str] = None,
    today: Optional[date] = None,
) -> List[AuditEvent]:
    """Emit governance.suite.<name>.review.overdue for every suite whose
    next_review has passed, at most once per suite per calendar day."""
    obs = observatory or get_observatory()
    today = today or datetime.utcnow().date()
    emitted: List[AuditEvent] = []

    for health in list_suite_health(path=path, today=today):
        if not health.overdue or not health.event_prefix:
            continue
        with _last_overdue_emit_lock:
            if _last_overdue_emit.get(health.suite_id) == today:
                continue
            _last_overdue_emit[health.suite_id] = today
        event = obs.record(
            f"{health.event_prefix}.review.overdue",
            actor="system",
            target=health.suite_id,
            category=EventCategory.GOVERNANCE,
            severity=EventSeverity.WARNING,
            service="tranc3-matrix-suites",
            location=health.steward_location,
            outcome="warning",
            metadata={
                "suite_id": health.suite_id,
                "suite_name": health.name,
                "steward_ai": health.steward_ai,
                "next_review": health.next_review,
                "days_overdue": health.days_overdue,
            },
        )
        emitted.append(event)
    return emitted


def record_review_completed(
    suite_id: str,
    reviewer: str,
    notes: str = "",
    observatory: Optional[Observatory] = None,
    path: Optional[str] = None,
) -> AuditEvent:
    """Emit governance.suite.<name>.review.completed. Does not mutate the
    registry's next_review — that's a Magna Carta-side edit; this only
    records that a steward closed this cadence's review."""
    suites = load_suites(path)
    suite = _find_suite(suites, suite_id)
    prefix = _event_prefix(suite)
    obs = observatory or get_observatory()
    return obs.record(
        f"{prefix}.review.completed",
        actor=reviewer,
        target=suite_id,
        category=EventCategory.GOVERNANCE,
        severity=EventSeverity.INFO,
        service="tranc3-matrix-suites",
        location=suite.get("steward_location"),
        outcome="success",
        metadata={
            "suite_id": suite_id,
            "suite_name": suite.get("name", ""),
            "reviewer": reviewer,
            "notes": notes,
            "cadence": suite.get("review_cadence", ""),
        },
    )


def record_matrix_changed(
    suite_id: str,
    matrix_id: str,
    observatory: Optional[Observatory] = None,
    path: Optional[str] = None,
) -> AuditEvent:
    """Emit governance.suite.<name>.matrix.changed for a member matrix file
    change (CI-detected, per docs/governance/MATRIX-SUITES.md §4)."""
    suites = load_suites(path)
    suite = _find_suite(suites, suite_id)
    matrix_ids = {m.get("id") for m in (suite.get("matrices") or [])}
    if matrix_id not in matrix_ids:
        raise MatrixSuitesError(f"Matrix {matrix_id!r} is not a member of suite {suite_id!r}")

    prefix = _event_prefix(suite)
    obs = observatory or get_observatory()
    return obs.record(
        f"{prefix}.matrix.changed",
        actor="ci",
        target=matrix_id,
        category=EventCategory.GOVERNANCE,
        severity=EventSeverity.INFO,
        service="tranc3-matrix-suites",
        location=suite.get("steward_location"),
        outcome="success",
        metadata={"suite_id": suite_id, "matrix_id": matrix_id},
    )


def record_escalated(
    suite_id: str,
    from_role: str,
    to_role: str,
    reason: str,
    observatory: Optional[Observatory] = None,
    path: Optional[str] = None,
) -> AuditEvent:
    """Emit governance.suite.<name>.escalated for a move up the suite's
    declared escalation chain. Both roles must be links in that chain
    (steward_ai or a name in `escalation`) — this validates the move is
    structurally legitimate, not an arbitrary reassignment."""
    suites = load_suites(path)
    suite = _find_suite(suites, suite_id)
    chain = [suite.get("steward_ai", "")] + list(suite.get("escalation") or [])
    if from_role not in chain:
        raise MatrixSuitesError(
            f"from_role {from_role!r} is not in suite {suite_id!r}'s escalation chain: {chain}"
        )
    if to_role not in chain:
        raise MatrixSuitesError(
            f"to_role {to_role!r} is not in suite {suite_id!r}'s escalation chain: {chain}"
        )
    if chain.index(to_role) <= chain.index(from_role):
        raise MatrixSuitesError(
            f"to_role {to_role!r} is not further up the chain than from_role {from_role!r}"
        )

    prefix = _event_prefix(suite)
    obs = observatory or get_observatory()
    return obs.record(
        f"{prefix}.escalated",
        actor=from_role,
        target=to_role,
        category=EventCategory.GOVERNANCE,
        severity=EventSeverity.WARNING,
        service="tranc3-matrix-suites",
        location=suite.get("steward_location"),
        outcome="success",
        metadata={
            "suite_id": suite_id,
            "from_role": from_role,
            "to_role": to_role,
            "reason": reason,
        },
    )
