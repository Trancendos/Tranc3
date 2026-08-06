# src/compliance/escalation_fsm.py
# Unified Escalation State Machine — AI Governance Constitution Phase 2
#
# Implements the design in docs/governance/AI-GOVERNANCE-CONSTITUTION.md §3: takes an action
# request from a Tier 4/5 entity, resolves it against a per-capability-class charter
# (docs/governance/schemas/agent-charter.schema.json), and routes it through a small state
# machine to either approval, CAB Gate (src/compliance/cab_gate.py), or escalation.
#
# Deliberately reuses existing platform systems instead of inventing parallel ones:
#   - approval_required charters route through CABGate (MC-RULE-007), not a new gate
#   - escalated/frozen transitions log to ai_governance.AIIncident, not a new incident table
#   - every transition is recorded to The Observatory, the platform's one real audit log
#
# This closes the aggregation gap docs/governance/HARD-STOP-MATRIX.md already documented:
# "there is no single place that answers 'has anything been hard-stopped right now'" — see
# list_halted() below.

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema

from Dimensional.sanitize import sanitize_for_log
from src.compliance.ai_governance import IncidentSeverity, log_ai_incident
from src.compliance.cab_gate import cab_gate
from src.observability.observatory import EventCategory, EventSeverity, get_observatory

logger = logging.getLogger("tranc3.compliance.escalation_fsm")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _REPO_ROOT / "docs" / "governance" / "schemas" / "agent-charter.schema.json"
_DEFAULT_CHARTERS_DIR = _REPO_ROOT / "docs" / "governance" / "charters"
_DB_PATH = Path(os.environ.get("ESCALATION_FSM_DB_PATH", "data/escalation_fsm.db"))

_SEVERITY_TO_OBSERVATORY: Dict[str, EventSeverity] = {
    "low": EventSeverity.INFO,
    "medium": EventSeverity.WARNING,
    "high": EventSeverity.WARNING,
    "critical": EventSeverity.CRITICAL,
}
_SEVERITY_TO_INCIDENT: Dict[str, IncidentSeverity] = {
    "low": IncidentSeverity.LOW,
    "medium": IncidentSeverity.MEDIUM,
    "high": IncidentSeverity.HIGH,
    "critical": IncidentSeverity.CRITICAL,
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class EscalationError(Exception):
    """Base error for the escalation FSM."""


class CharterNotFoundError(EscalationError):
    """No loaded charter covers the requested (tier, domain, action)."""


class CharterValidationError(EscalationError):
    """A charter file failed validation against agent-charter.schema.json."""


class ActionForbiddenError(EscalationError):
    """The requested action is explicitly listed in the charter's forbidden_actions."""


class RecordNotFoundError(EscalationError):
    """No escalation record exists for the given record_id."""


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

# Matches docs/governance/AI-GOVERNANCE-CONSTITUTION.md §3.2 exactly.
STATES = frozenset(
    {
        "draft",
        "validated",
        "rejected",
        "policy_checked",
        "approved",
        "pending_cab",
        "executing",
        "completed",
        "escalated",
        "frozen",
        "halted",
    }
)

# Terminal states an ActionRequest can settle in without further FSM action.
_TERMINAL_STATES = frozenset({"completed", "rejected", "halted"})


# ---------------------------------------------------------------------------
# Charter loading + validation
# ---------------------------------------------------------------------------


@dataclass
class Charter:
    """A validated per-capability-class charter (agent-charter.schema.json)."""

    charter_id: str
    version: str
    tier: int
    domain: str
    mission: str
    allowed_actions: List[str]
    forbidden_actions: List[str]
    risk_tier: str
    approval_required: bool
    escalation_triggers: List[str]
    escalation_severity: str
    fallback_behavior: str
    confidence_model: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Charter":
        return cls(
            charter_id=data["charter_id"],
            version=data["version"],
            tier=data["tier"],
            domain=data["domain"],
            mission=data["mission"],
            allowed_actions=list(data["allowed_actions"]),
            forbidden_actions=list(data["forbidden_actions"]),
            risk_tier=data["risk_tier"],
            approval_required=data["approval_required"],
            escalation_triggers=list(data["escalation_triggers"]),
            escalation_severity=data["escalation_severity"],
            fallback_behavior=data["fallback_behavior"],
            confidence_model=data.get("confidence_model"),
        )

    def confidence_threshold(self) -> Optional[float]:
        if self.confidence_model is None:
            return None
        return self.confidence_model.get("threshold")


def _load_schema() -> Dict[str, Any]:
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


class CharterRegistry:
    """Loads and validates all charter files in a directory against the schema.

    Charters are scoped to (tier, domain) capability classes, not one per named AI —
    see AI-GOVERNANCE-CONSTITUTION.md §2.1 for why a per-AI model was rejected.
    """

    def __init__(self, charters_dir: Optional[Path] = None) -> None:
        self._dir = charters_dir or _DEFAULT_CHARTERS_DIR
        self._charters: Dict[str, Charter] = {}
        self._by_tier_domain: Dict[tuple, List[Charter]] = {}
        self._schema = _load_schema()
        self._validator = jsonschema.Draft202012Validator(self._schema)
        self.reload()

    def reload(self) -> None:
        charters: Dict[str, Charter] = {}
        by_tier_domain: Dict[tuple, List[Charter]] = {}

        if not self._dir.is_dir():
            logger.warning("CharterRegistry directory not found: %s", self._dir)
            self._charters = charters
            self._by_tier_domain = by_tier_domain
            return

        for path in sorted(self._dir.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                raise CharterValidationError(
                    f"Failed to read charter file {path.name}: {exc}"
                ) from exc

            errors = sorted(self._validator.iter_errors(data), key=lambda e: e.path)
            if errors:
                first = errors[0]
                raise CharterValidationError(
                    f"Charter {path.name} failed schema validation: {first.message}"
                )

            charter = Charter.from_dict(data)
            if charter.charter_id in charters:
                raise CharterValidationError(
                    f"Duplicate charter_id across charter files: {charter.charter_id!r}"
                )
            charters[charter.charter_id] = charter
            by_tier_domain.setdefault((charter.tier, charter.domain), []).append(charter)

        self._charters = charters
        self._by_tier_domain = by_tier_domain
        logger.info("CharterRegistry loaded %d charter(s) from %s", len(charters), self._dir)

    def get(self, charter_id: str) -> Charter:
        try:
            return self._charters[charter_id]
        except KeyError:
            raise CharterNotFoundError(f"Unknown charter_id: {charter_id!r}") from None

    def list_all(self) -> List[Charter]:
        return list(self._charters.values())

    def find_for(self, tier: int, domain: str, action: str) -> Charter:
        """Find the charter covering `action` for a given (tier, domain).

        Raises CharterNotFoundError if no charter matches, and ActionForbiddenError if a
        matching charter exists but explicitly forbids the action — callers should let
        ActionForbiddenError propagate to submit() rather than catching it here, so the
        FSM records a real 'rejected' transition instead of silently swallowing it.
        """
        candidates = self._by_tier_domain.get((tier, domain), [])
        for charter in candidates:
            if action in charter.forbidden_actions:
                raise ActionForbiddenError(
                    f"Action {action!r} is forbidden by charter {charter.charter_id!r}"
                )
            if action in charter.allowed_actions:
                return charter
        raise CharterNotFoundError(
            f"No charter for tier={tier} domain={domain!r} covers action={action!r}"
        )


_registry_lock = threading.Lock()
_registry: Optional[CharterRegistry] = None


def get_charter_registry() -> CharterRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = CharterRegistry()
        return _registry


_fsm_lock = threading.Lock()
_fsm: Optional["EscalationFSM"] = None


def get_escalation_fsm() -> "EscalationFSM":
    """Process-wide EscalationFSM singleton for in-process callers (e.g.
    AgentOrchestrator) — Phase 3 wiring. Cross-service callers (e.g. tranc3-bots,
    a separately deployed package) go through the HTTP /governance/actions route
    instead; see governance_routes.py."""
    global _fsm
    with _fsm_lock:
        if _fsm is None:
            _fsm = EscalationFSM()
        return _fsm


# ---------------------------------------------------------------------------
# Escalation records (SQLite-backed, mirrors cab_gate.py's storage pattern)
# ---------------------------------------------------------------------------


@dataclass
class ActionRequest:
    tier: int
    domain: str
    action: str
    requestor: str
    confidence: Optional[float] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EscalationRecord:
    record_id: str
    charter_id: str
    action: str
    requestor: str
    state: str
    created_at: float
    updated_at: float
    cab_change_id: Optional[str] = None
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "charter_id": self.charter_id,
            "action": self.action,
            "requestor": self.requestor,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "cab_change_id": self.cab_change_id,
            "reason": self.reason,
        }


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS escalation_records (
            record_id     TEXT PRIMARY KEY,
            charter_id    TEXT NOT NULL,
            action        TEXT NOT NULL,
            requestor     TEXT NOT NULL,
            state         TEXT NOT NULL,
            created_at    REAL NOT NULL,
            updated_at    REAL NOT NULL,
            cab_change_id TEXT,
            reason        TEXT
        )
        """
    )
    # Append-only, mirroring src/roles/registry.py's role_assignment_history pattern —
    # escalation_records above holds current state only (UPDATE overwrites it), so this
    # table is the only place the full transition path survives a process restart or an
    # Observatory ring-buffer rotation.
    transitions_table_existed = (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='escalation_transitions'"
        ).fetchone()
        is not None
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS escalation_transitions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id  TEXT NOT NULL,
            state      TEXT NOT NULL,
            reason     TEXT,
            ts         REAL NOT NULL
        )
        """
    )
    if not transitions_table_existed:
        # First time this table is created on a DB that may already have escalation_records
        # rows predating it (an upgrade, not a fresh install) — backfill one synthetic
        # "current state as of upgrade" transition per existing record so
        # list_transitions() doesn't silently report an empty history for them. This can't
        # recover the actual lost intermediate states, only the last known one.
        conn.execute(
            """
            INSERT INTO escalation_transitions (record_id, state, reason, ts)
            SELECT record_id, state, reason, updated_at FROM escalation_records
            """
        )
    conn.commit()
    return conn


def _row_to_record(row: sqlite3.Row) -> EscalationRecord:
    return EscalationRecord(
        record_id=row["record_id"],
        charter_id=row["charter_id"],
        action=row["action"],
        requestor=row["requestor"],
        state=row["state"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        cab_change_id=row["cab_change_id"],
        reason=row["reason"],
    )


# ---------------------------------------------------------------------------
# The FSM
# ---------------------------------------------------------------------------


class EscalationFSM:
    """The Phase 2 enforcement engine described in AI-GOVERNANCE-CONSTITUTION.md §3.

    submit() is the only entry point that matters operationally: it resolves an
    ActionRequest against the charter registry and drives it to its first resting
    state (approved / pending_cab / rejected / escalated), writing every transition to
    both the local SQLite table and The Observatory.
    """

    def __init__(self, registry: Optional[CharterRegistry] = None) -> None:
        self._registry = registry or get_charter_registry()
        self._lock = threading.Lock()

    # -- persistence -------------------------------------------------------

    def _insert(self, record: EscalationRecord) -> None:
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO escalation_records
                    (record_id, charter_id, action, requestor, state,
                     created_at, updated_at, cab_change_id, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.charter_id,
                    record.action,
                    record.requestor,
                    record.state,
                    record.created_at,
                    record.updated_at,
                    record.cab_change_id,
                    record.reason,
                ),
            )
            conn.execute(
                "INSERT INTO escalation_transitions (record_id, state, reason, ts) VALUES (?, ?, ?, ?)",
                (record.record_id, record.state, record.reason, record.created_at),
            )
            conn.commit()

    def _update_state(
        self, record_id: str, state: str, reason: Optional[str] = None
    ) -> EscalationRecord:
        now = time.time()
        with _get_conn() as conn:
            cur = conn.execute(
                """
                UPDATE escalation_records
                SET state = ?, updated_at = ?, reason = COALESCE(?, reason)
                WHERE record_id = ?
                """,
                (state, now, reason, record_id),
            )
            # Only append a transition row when the UPDATE actually matched a record —
            # otherwise an unknown record_id (e.g. a bogus halt()/resolve_cab() call)
            # would leave a phantom transition row for a record_id that was never
            # inserted, polluting escalation_transitions without a parent action.
            if cur.rowcount > 0:
                conn.execute(
                    "INSERT INTO escalation_transitions (record_id, state, reason, ts) VALUES (?, ?, ?, ?)",
                    (record_id, state, reason, now),
                )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM escalation_records WHERE record_id = ?", (record_id,)
            ).fetchone()
        if row is None:
            raise RecordNotFoundError(f"Unknown record_id: {record_id!r}")
        return _row_to_record(row)

    def list_transitions(self, record_id: str) -> List[Dict[str, Any]]:
        """The durable transition path for a record — survives process restarts and
        Observatory ring-buffer rotation, unlike the current-state-only row above."""
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT state, reason, ts FROM escalation_transitions "
                "WHERE record_id = ? ORDER BY id ASC",
                (record_id,),
            ).fetchall()
        return [{"state": r["state"], "reason": r["reason"], "ts": r["ts"]} for r in rows]

    def get(self, record_id: str) -> EscalationRecord:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM escalation_records WHERE record_id = ?", (record_id,)
            ).fetchone()
        if row is None:
            raise RecordNotFoundError(f"Unknown record_id: {record_id!r}")
        return _row_to_record(row)

    def list_halted(self) -> List[EscalationRecord]:
        """The Hard Stop Matrix aggregation point: everything currently halted, in one place."""
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM escalation_records WHERE state = 'halted' ORDER BY updated_at DESC"
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    # -- Observatory + incident wiring --------------------------------------

    def _emit(self, event_type: str, record: EscalationRecord, severity: EventSeverity) -> None:
        obs = get_observatory()
        obs.record(
            event_type,
            actor=sanitize_for_log(record.requestor),  # codeql[py/log-injection]
            target=record.record_id,
            category=EventCategory.GOVERNANCE,
            severity=severity,
            service="trancendos-governance",
            metadata={
                "charter_id": record.charter_id,
                "action": record.action,
                "state": record.state,
            },
        )

    def _log_incident(
        self,
        record: EscalationRecord,
        description: str,
        charter: Optional[Charter] = None,
        severity: Optional[IncidentSeverity] = None,
    ) -> None:
        """Log an AIIncident for every escalation/freeze — cubic P2: these were previously
        only logged from the confidence-threshold branch, so unknown-action escalations and
        freezes were invisible to governance incident views. Falls back to charter_id
        'unassigned' and IncidentSeverity.MEDIUM when no charter could be resolved."""
        if severity is None:
            severity = (
                _SEVERITY_TO_INCIDENT.get(charter.escalation_severity, IncidentSeverity.MEDIUM)
                if charter is not None
                else IncidentSeverity.MEDIUM
            )
        log_ai_incident(
            model_id=charter.charter_id if charter is not None else "unassigned",
            description=description,
            severity=severity,
            reporter=record.requestor,
        )

    def _observatory_severity(self, charter: Optional[Charter]) -> EventSeverity:
        """Map a charter's escalation_severity onto the Observatory's EventSeverity scale.

        cubic P2: escalations were previously always emitted as EventSeverity.WARNING
        regardless of the charter's own severity, so a 'critical'-severity charter's
        escalation could miss Observatory's CRITICAL archival path."""
        if charter is None:
            return EventSeverity.WARNING
        return _SEVERITY_TO_OBSERVATORY.get(charter.escalation_severity, EventSeverity.WARNING)

    # Signals an ActionRequest.context can carry that map 1:1 onto charter escalation_triggers
    # (excluding confidence_below_threshold, which has its own dedicated numeric check above).
    _CONTEXT_TRIGGERS = frozenset(
        {
            "policy_conflict",
            "sensitive_data_detected",
            "irreversible_action_requested",
            "external_communication",
            "production_change",
            "prompt_injection_suspected",
            "audit_gap",
        }
    )

    # -- the entry point -----------------------------------------------------

    def submit(self, request: ActionRequest) -> EscalationRecord:
        """Resolve an ActionRequest to its first resting state.

        Follows AI-GOVERNANCE-CONSTITUTION.md §3.2/§3.4: ambiguity and forbidden actions
        escalate or reject rather than defaulting permissive.
        """
        now = time.time()
        record_id = f"ESC-{uuid.uuid4().hex[:10].upper()}"

        try:
            charter = self._registry.find_for(request.tier, request.domain, request.action)
        except ActionForbiddenError as exc:
            # We still need a charter_id for the record; re-resolve via the candidate list
            # that raised, since find_for's contract guarantees the charter exists when it
            # raises ActionForbiddenError (only reachable after a match on forbidden_actions).
            charter_id = str(exc).rsplit("charter ", 1)[-1].strip("'")
            record = EscalationRecord(
                record_id=record_id,
                charter_id=charter_id,
                action=request.action,
                requestor=request.requestor,
                state="rejected",
                created_at=now,
                updated_at=now,
                reason=str(exc),
            )
            self._insert(record)
            self._emit("governance.action.rejected", record, EventSeverity.WARNING)
            return record
        except CharterNotFoundError as exc:
            # No charter covers this action at all: per §3.4, ambiguity escalates — it is
            # never treated as implicitly allowed.
            record = EscalationRecord(
                record_id=record_id,
                charter_id="unassigned",
                action=request.action,
                requestor=request.requestor,
                state="escalated",
                created_at=now,
                updated_at=now,
                reason=str(exc),
            )
            self._insert(record)
            self._emit("governance.action.escalated", record, EventSeverity.WARNING)
            self._log_incident(record, f"Unassigned action {request.action!r} escalated")
            return record

        record = EscalationRecord(
            record_id=record_id,
            charter_id=charter.charter_id,
            action=request.action,
            requestor=request.requestor,
            state="validated",
            created_at=now,
            updated_at=now,
        )
        self._insert(record)
        self._emit("governance.action.validated", record, EventSeverity.INFO)

        threshold = charter.confidence_threshold()
        if (
            "confidence_below_threshold" in charter.escalation_triggers
            and threshold is not None
            and request.confidence is not None
            and request.confidence < threshold
        ):
            record = self._update_state(
                record_id,
                "escalated",
                reason=f"confidence {request.confidence} below charter threshold {threshold}",
            )
            self._emit("governance.action.escalated", record, self._observatory_severity(charter))
            self._log_incident(
                record, f"Low-confidence action {request.action!r} escalated", charter=charter
            )
            return record

        # cubic P1: configured safety signals (sensitive_data_detected,
        # prompt_injection_suspected, etc.) previously had no effect — a charter could
        # declare them in escalation_triggers and a caller could set them in context, and
        # the action would still sail through to approved/pending_cab. Evaluate every
        # trigger the charter actually declares against the caller-supplied context before
        # policy_checked, same as the confidence check above.
        active_triggers = [
            t
            for t in charter.escalation_triggers
            if t in self._CONTEXT_TRIGGERS and request.context.get(t)
        ]
        if active_triggers:
            record = self._update_state(
                record_id,
                "escalated",
                reason=f"context signal(s) triggered: {', '.join(sorted(active_triggers))}",
            )
            self._emit("governance.action.escalated", record, self._observatory_severity(charter))
            self._log_incident(
                record,
                f"Action {request.action!r} escalated on signal(s): {', '.join(sorted(active_triggers))}",
                charter=charter,
            )
            return record

        record = self._update_state(record_id, "policy_checked")
        self._emit("governance.action.policy_checked", record, EventSeverity.INFO)

        if not charter.approval_required:
            record = self._update_state(record_id, "approved")
            self._emit("governance.action.approved", record, EventSeverity.INFO)
            return record

        change_id = cab_gate.register_change(
            change_type=f"governance.{charter.domain}.{request.action}",
            description=f"{charter.mission} — action={request.action!r}",
            requestor=request.requestor,
            risk=charter.risk_tier if charter.risk_tier != "unacceptable" else "critical",
        )
        with _get_conn() as conn:
            conn.execute(
                "UPDATE escalation_records SET cab_change_id = ? WHERE record_id = ?",
                (change_id, record_id),
            )
            conn.commit()
        record = self._update_state(record_id, "pending_cab")
        record.cab_change_id = change_id
        self._emit("governance.action.pending_cab", record, EventSeverity.WARNING)
        return record

    def resolve_cab(self, record_id: str, approver: str, approved: bool) -> EscalationRecord:
        """Apply a CAB Gate decision to a record.

        cubic P1: this previously trusted the caller's `approved` boolean directly and
        flipped FSM state without ever touching cab_gate's own `cab_changes` row — so a
        record could read 'approved' here while its underlying CAB change stayed 'pending'
        forever, letting a caller bypass MC-RULE-007 and leaving the two governance stores
        (escalation_records, cab_changes) permanently diverged. Now calls into CABGate for
        both outcomes and only transitions FSM state if that persisted decision succeeds.
        """
        record = self.get(record_id)
        if record.state != "pending_cab":
            raise EscalationError(
                f"Record {record_id!r} is not pending_cab (state={record.state!r})"
            )
        if not record.cab_change_id:
            raise EscalationError(f"Record {record_id!r} has no associated cab_change_id")

        if approved:
            applied = cab_gate.approve_change(record.cab_change_id, approver)
        else:
            applied = cab_gate.reject_change(record.cab_change_id, approver)
        if not applied:
            raise EscalationError(
                f"CAB Gate decision for change {record.cab_change_id!r} was not applied "
                "(not found, or already resolved) — FSM state left unchanged"
            )

        new_state = "approved" if approved else "rejected"
        record = self._update_state(record_id, new_state, reason=f"CAB decision by {approver}")
        self._emit(f"governance.action.{new_state}", record, EventSeverity.INFO)
        return record

    def freeze(self, record_id: str, reason: str) -> EscalationRecord:
        record = self._update_state(record_id, "frozen", reason=reason)
        self._emit("governance.action.frozen", record, EventSeverity.CRITICAL)
        charter: Optional[Charter] = None
        try:
            charter = self._registry.get(record.charter_id)
        except CharterNotFoundError:
            pass
        self._log_incident(record, f"Action {record.action!r} frozen: {reason}", charter=charter)
        return record

    def halt(self, record_id: str, reason: str) -> EscalationRecord:
        """Irreversible: no transition leads out of 'halted' except a fresh submit()."""
        record = self._update_state(record_id, "halted", reason=reason)
        self._emit("governance.action.halted", record, EventSeverity.CRITICAL)
        return record

    def complete(self, record_id: str) -> EscalationRecord:
        record = self.get(record_id)
        if record.state != "approved":
            raise EscalationError(
                f"Record {record_id!r} must be 'approved' before completing (state={record.state!r})"
            )
        record = self._update_state(record_id, "executing")
        self._emit("governance.action.executing", record, EventSeverity.INFO)
        record = self._update_state(record_id, "completed")
        self._emit("governance.action.completed", record, EventSeverity.INFO)
        return record
