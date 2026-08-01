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
from datetime import date, datetime, timezone
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

# Resolved from this module's own location (src/compliance/ -> repo root is
# two parents up), not the process CWD — a relative path here would silently
# return an empty suite list if a worker/cron is launched from a different
# working directory than the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MATRIX_SUITES_PATH = str(
    _REPO_ROOT / "compliance" / "magna-carta" / "compliance" / "matrix_suites.yaml"
)


def _default_path() -> str:
    """Read MATRIX_SUITES_PATH at call time, not at import time — so tests
    (and any runtime env change) that set it via monkeypatch/os.environ take
    effect without needing a module reload."""
    return os.getenv("MATRIX_SUITES_PATH", _DEFAULT_MATRIX_SUITES_PATH)


class MatrixSuitesError(ValueError):
    """Raised for an unknown suite_id or a malformed registry — the caller's
    identifier doesn't resolve to anything, or the registry itself is broken.
    Routes map this to 404."""


class MatrixSuitesValidationError(MatrixSuitesError):
    """Raised when a suite_id resolves fine but the rest of the request is
    invalid — a matrix that isn't a member, a role outside the escalation
    chain, or a backwards escalation move. This is still a MatrixSuitesError
    (existing `except MatrixSuitesError` callers keep working) but routes
    distinguish it to return 400/422 instead of 404 — the suite exists, the
    request doesn't."""


class MatrixSuitesRegistryError(MatrixSuitesError):
    """Raised when a suite_id resolves fine but the suite's *own registry
    entry* is misconfigured (e.g. missing observatory_events) — unlike
    MatrixSuitesValidationError, this isn't something the caller's request
    can fix by being different; it's a Magna Carta-side data problem. Routes
    map this the same way as a malformed registry (404 invalid_registry),
    not as a 400 client error."""


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
    next_review_valid: bool


def _event_prefix(suite: Dict[str, Any]) -> str:
    """observatory_events is stored as e.g. 'governance.suite.financial.*'.
    A missing key, an explicit `null`, or a non-string value all resolve to
    "" here — callers treat "" as "no usable prefix" (see _require_prefix)
    rather than crashing on .endswith()/.rstrip()."""
    raw = suite.get("observatory_events") or ""
    if not isinstance(raw, str):
        return ""
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

    try:
        with p.open(encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise MatrixSuitesError(f"matrix_suites.yaml: invalid YAML: {exc}") from exc
    except UnicodeDecodeError as exc:
        # A registry file that isn't valid UTF-8 (encoding drift, a bad merge,
        # a stray binary write) must classify the same as any other malformed
        # registry, not surface as an unhandled 500 — UnicodeDecodeError is a
        # ValueError subclass, not a yaml.YAMLError, so it needs its own catch.
        raise MatrixSuitesError(f"matrix_suites.yaml: not valid UTF-8: {exc}") from exc
    except OSError as exc:
        # The is_file() check above is inherently racy: the submodule file
        # can be removed/become unreadable between that check and this open()
        # (concurrent submodule update, permission change). Wrap it the same
        # way as a YAML parse failure rather than letting a raw OSError
        # surface as an unhandled 500.
        raise MatrixSuitesError(f"matrix_suites.yaml: unreadable: {exc}") from exc

    if not isinstance(doc, dict):
        raise MatrixSuitesError("matrix_suites.yaml: document root must be a mapping")

    suites = doc.get("suites", [])
    if not isinstance(suites, list):
        raise MatrixSuitesError("matrix_suites.yaml: 'suites' must be a list")
    return suites


def _matrix_list(suite: Dict[str, Any]) -> List[Any]:
    """suite["matrices"] should be a list of matrix mappings; normalize any
    other type (missing, null, or wrong-typed registry drift) to []."""
    matrices = suite.get("matrices")
    return matrices if isinstance(matrices, list) else []


def _coerce_suite_id(raw: Any) -> str:
    """str()-coerce-and-strip a raw registry suite_id value, treating an
    explicit `null` the same as a missing key (both -> "") rather than the
    literal string "None" -- shared by list_suite_health() and
    _find_suite() so both apply the exact same missing/blank rule."""
    return "" if raw is None else str(raw).strip()


def _find_suite(suites: List[Dict[str, Any]], suite_id: str) -> Dict[str, Any]:
    # Coerced the same way as list_suite_health(): a registry entry whose
    # suite_id coerces to "" (missing, null, or blank) is unusable there and
    # must be equally unreachable here — otherwise a null id could still be
    # addressed literally as /compliance/suites/None/... and emit events.
    matches = [
        suite
        for suite in suites
        if isinstance(suite, dict) and _coerce_suite_id(suite.get("suite_id")) == suite_id
    ]
    if not matches:
        raise MatrixSuitesError(f"Unknown suite_id: {suite_id!r}")
    if len(matches) > 1:
        # Two registry entries sharing one suite_id are already excluded
        # from list_suite_health() entirely (see its duplicate check) —
        # resolving to "whichever came first" here would let an action
        # silently apply to the wrong suite's configuration instead of
        # matching that same ambiguity-is-unusable rule.
        raise MatrixSuitesError(f"Ambiguous suite_id (registry has duplicates): {suite_id!r}")
    return matches[0]


def _require_prefix(suite: Dict[str, Any], suite_id: str) -> str:
    """Resolve the suite's event prefix, refusing to emit a malformed event
    name (e.g. a leading-dot '.review.completed') when observatory_events is
    missing or empty in the registry."""
    prefix = _event_prefix(suite)
    if not prefix:
        raise MatrixSuitesRegistryError(
            f"Suite {suite_id!r} has no observatory_events prefix configured"
        )
    return prefix


def _parse_next_review(raw: Any) -> Optional[date]:
    """Parse a suite's `next_review` value into a date, or None if it can't be.
    A real matrix_suites.yaml quotes next_review as a string, but an unquoted
    YAML date literal (e.g. `next_review: 2026-08-31`) is auto-parsed by
    PyYAML into a `datetime.date` (or `datetime.datetime` for a date+time
    literal) rather than a string — that's a genuine, valid date and must be
    accepted as such, not treated as corrupt merely for not being a str."""
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def list_suite_health(
    path: Optional[str] = None, today: Optional[date] = None
) -> List[SuiteHealth]:
    """Compute per-suite health (overdue reviews) from the registry."""
    today = today or datetime.now(timezone.utc).date()
    results: List[SuiteHealth] = []
    suites = load_suites(path)
    # Two registry entries sharing one suite_id would collide on the same
    # overdue throttle key, and _find_suite() would always resolve to
    # whichever came first — a caller acting on "the suite" could silently
    # be acting on the wrong one. Pre-count occurrences so duplicates are
    # excluded entirely below rather than the first one winning by accident.
    id_counts: Dict[str, int] = {}
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        cid = _coerce_suite_id(suite.get("suite_id"))
        if cid:
            id_counts[cid] = id_counts.get(cid, 0) + 1

    for suite in suites:
        if not isinstance(suite, dict):
            logger.warning("Skipping malformed suite entry (not a mapping): %r", suite)
            continue
        coerced_suite_id = _coerce_suite_id(suite.get("suite_id"))
        if not coerced_suite_id:
            # A missing/blank suite_id str()-coerces to "" — a non-string but
            # otherwise present id (e.g. an unquoted YAML int) is fine and
            # still coerced below, matching _find_suite()'s own coercion, but
            # an EMPTY id can't be a usable identifier. Every consumer of
            # SuiteHealth.suite_id (the GET routes, the action endpoints, and
            # emit_overdue_events()'s per-suite throttle dict) needs a real,
            # distinct key — two different malformed entries would otherwise
            # both coerce to "" and silently share (and suppress) each
            # other's overdue-event throttle state.
            logger.warning("Skipping suite entry with missing/blank suite_id: %r", suite)
            continue
        if id_counts.get(coerced_suite_id, 0) > 1:
            logger.warning("Skipping suite entry with duplicate suite_id: %r", suite)
            continue
        next_review_raw = suite.get("next_review")
        next_review_date = _parse_next_review(next_review_raw)
        overdue = False
        days_overdue = 0
        next_review_valid = next_review_date is not None
        if next_review_valid:
            if next_review_date < today:
                overdue = True
                days_overdue = (today - next_review_date).days
        else:
            # Fail-safe, not fail-silent: a suite whose next_review is missing
            # or corrupt is a governance gap in its own right (per this
            # module's whole purpose — surfacing overdue reviews), so it must
            # show up as needing attention rather than quietly read as
            # healthy. next_review_valid=False distinguishes this from a
            # real, computed day count.
            overdue = True
            logger.warning(
                "Suite %s has an unparseable next_review value: %r",
                suite.get("suite_id"),
                next_review_raw,
            )
        next_review_display = (
            next_review_date.isoformat()
            if next_review_date is not None
            else ("" if next_review_raw is None else str(next_review_raw))
        )
        results.append(
            SuiteHealth(
                # Reuse the already str()-coerced-and-stripped id computed
                # above (not a fresh str(suite.get(...)) here) so the listed
                # identifier exactly matches what _find_suite() and the
                # overdue throttle key use — otherwise a registry id with
                # surrounding whitespace (e.g. " fin ") would be listed as
                # " fin " but unreachable via /compliance/suites/fin/....
                suite_id=coerced_suite_id,
                name=suite.get("name", ""),
                pillar=suite.get("pillar", ""),
                steward_ai=suite.get("steward_ai", ""),
                steward_location=suite.get("steward_location", ""),
                review_cadence=suite.get("review_cadence", ""),
                next_review=next_review_display,
                overdue=overdue,
                days_overdue=days_overdue,
                event_prefix=_event_prefix(suite),
                matrix_count=len(_matrix_list(suite)),
                next_review_valid=next_review_valid,
            )
        )
    return results


# Per-suite date of the last emitted overdue event, so a repeatedly-polled
# check (e.g. a ChronosSphere cron hitting /compliance/suites/check-overdue)
# doesn't flood the Observatory with a duplicate event every tick.
#
# In-process only — per CLAUDE.md's architecture principles ("In-memory rate
# limiting over Cloudflare KV — Token-bucket algorithm per-worker", "SQLite
# over Cloudflare D1 — no shared state"), this repo's convention for exactly
# this kind of per-worker dedup is process-local memory, not a shared store.
# The bound this accepts: under multiple uvicorn workers, each worker throttles
# independently, so a genuinely overdue suite can emit review.overdue once per
# worker per day rather than once globally — a duplicate signal, not a missed
# one, and consistent with the platform's existing zero-shared-state posture.
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
    today = today or datetime.now(timezone.utc).date()
    emitted: List[AuditEvent] = []

    for health in list_suite_health(path=path, today=today):
        if not health.overdue:
            continue
        if not health.event_prefix:
            # Don't let the single most important governance signal here
            # (a suite genuinely overdue) vanish silently just because the
            # registry entry is missing observatory_events — surface it as
            # a warning so registry drift is visible, matching the explicit
            # MatrixSuitesRegistryError the other three emit functions raise
            # via _require_prefix for the same underlying condition.
            logger.warning(
                "Suite %s is overdue but has no observatory_events prefix configured; "
                "skipping event emission",
                health.suite_id,
            )
            continue
        with _last_overdue_emit_lock:
            if _last_overdue_emit.get(health.suite_id) == today:
                continue
        event = obs.record(
            f"{health.event_prefix}.review.overdue",
            actor="system",
            target=health.suite_id,
            category=EventCategory.GOVERNANCE,
            severity=EventSeverity.WARNING,
            service="trancendos-matrix-suites",
            location=health.steward_location,
            outcome="warning",
            metadata={
                "suite_id": health.suite_id,
                "suite_name": health.name,
                "steward_ai": health.steward_ai,
                "next_review": health.next_review,
                "days_overdue": health.days_overdue,
                # days_overdue is always 0 for the missing/unparseable-date
                # fail-safe case (there's no real date to compute a count
                # from) — without this flag that reads identically to "1 day
                # overdue" to anything consuming the event, when it actually
                # means "registry value unusable, needs a steward to fix it".
                "next_review_valid": health.next_review_valid,
            },
        )
        # Marked only after obs.record() succeeds — if it raised, marking the
        # suite emitted here would suppress the signal for the rest of the
        # day even though no event actually reached the Observatory.
        with _last_overdue_emit_lock:
            _last_overdue_emit[health.suite_id] = today
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
    prefix = _require_prefix(suite, suite_id)
    obs = observatory or get_observatory()
    return obs.record(
        f"{prefix}.review.completed",
        actor=reviewer,
        target=suite_id,
        category=EventCategory.GOVERNANCE,
        severity=EventSeverity.INFO,
        service="trancendos-matrix-suites",
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
    # Checked before the membership test (not after) so a suite with a
    # misconfigured registry entry always classifies as MatrixSuitesRegistryError
    # (404 invalid_registry), regardless of whether matrix_id also happens to
    # be invalid — the caller's request can't fix a registry-side problem, so
    # that classification shouldn't depend on request contents.
    prefix = _require_prefix(suite, suite_id)
    # Restricted to str: a malformed registry entry's `id` could be any
    # YAML-parsed type (list, dict, ...), and an unhashable value would raise
    # TypeError while building this set rather than the intended
    # MatrixSuitesValidationError below.
    matrix_ids = {
        m.get("id")
        for m in _matrix_list(suite)
        if isinstance(m, dict) and isinstance(m.get("id"), str)
    }
    if matrix_id not in matrix_ids:
        raise MatrixSuitesValidationError(
            f"Matrix {matrix_id!r} is not a member of suite {suite_id!r}"
        )

    obs = observatory or get_observatory()
    return obs.record(
        f"{prefix}.matrix.changed",
        actor="ci",
        target=matrix_id,
        category=EventCategory.GOVERNANCE,
        severity=EventSeverity.INFO,
        service="trancendos-matrix-suites",
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
    # Checked before the chain/direction validation (not after) — same
    # reasoning as record_matrix_changed(): registry misconfiguration must
    # always classify as MatrixSuitesRegistryError regardless of whether the
    # request also happens to be invalid.
    prefix = _require_prefix(suite, suite_id)
    escalation = suite.get("escalation")
    escalation = escalation if isinstance(escalation, list) else []
    # Coerced to stripped strings, blanks dropped, de-duplicated preserving
    # first-seen order: escalation is raw registry data and can repeat
    # steward_ai or contain non-string/blank entries — chain.index() would
    # otherwise return the first occurrence, letting a legitimate forward
    # move be rejected or a backward one accepted.
    chain: List[str] = []
    for link in [suite.get("steward_ai", "")] + escalation:
        text = "" if link is None else str(link).strip()
        if text and text not in chain:
            chain.append(text)
    if from_role not in chain:
        raise MatrixSuitesValidationError(
            f"from_role {from_role!r} is not in suite {suite_id!r}'s escalation chain: {chain}"
        )
    if to_role not in chain:
        raise MatrixSuitesValidationError(
            f"to_role {to_role!r} is not in suite {suite_id!r}'s escalation chain: {chain}"
        )
    if chain.index(to_role) <= chain.index(from_role):
        raise MatrixSuitesValidationError(
            f"to_role {to_role!r} is not further up the chain than from_role {from_role!r}"
        )

    obs = observatory or get_observatory()
    return obs.record(
        f"{prefix}.escalated",
        actor=from_role,
        target=to_role,
        category=EventCategory.GOVERNANCE,
        severity=EventSeverity.WARNING,
        service="trancendos-matrix-suites",
        location=suite.get("steward_location"),
        outcome="success",
        metadata={
            "suite_id": suite_id,
            "from_role": from_role,
            "to_role": to_role,
            "reason": reason,
        },
    )
