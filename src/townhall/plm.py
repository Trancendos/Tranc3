"""The Town Hall — product lifecycle gates that actually block.

Why this exists
---------------
`src/townhall/governance.py` registers PRINCE2 as a Policy with a hardcoded
``score=0.92`` and no ``check`` function, so ``Policy.evaluate`` returns
UNKNOWN for it and ``/townhall/check`` reports PASS overall. That is a policy
*registry*. It is not a lifecycle: there was no product record, no stages, no
gate criteria, no evidence and no decision. Nothing built anywhere in the
estate passed through it — a grep across ``workers/`` for the Town Hall finds
one health check and no callers.

So a game, an application, an image or a design went from request to artefact
with no boundary in between. This module is that boundary.

What makes it a gate and not a report
-------------------------------------
The estate's recurring defect is a control that exists, runs and reports but
does not act. Three decisions here are aimed squarely at it:

**``advance`` raises.** An unmet mandatory criterion raises ``GateBlocked``
carrying the criteria that are unmet. It does not return a warning for a
caller to ignore, because a gate a caller may ignore is a report.

**Failed evidence does not satisfy.** Evidence carries an outcome. A test run
that ran and failed is evidence *against* the gate; treating the existence of
a record as satisfaction is how a red suite passes a release gate. The most
recent evidence for a criterion is the one that counts, so a re-run that
fails takes the satisfaction away again.

**A waiver is not a pass.** Skipping a criterion needs a written reason and a
named approver, and the gate decision records ``waived`` rather than
``passed``. A waiver that looked like a pass would be indistinguishable from
having done the work six months later, which is precisely when somebody asks.

Criteria are per deliverable kind
---------------------------------
An image does not need a build artefact and a module does not need an
accessibility audit. The criteria are declared against kinds, so the gate a
deliverable faces is the one its own nature justifies rather than a single
checklist that everything half-fails.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.event_bus.types import PlatformEventType

logger = logging.getLogger("tranc3.townhall.plm")

DEFAULT_DB_PATH = Path("data/townhall_plm.db")


class Stage(str, Enum):
    """PRINCE2-shaped stages. The gate is the boundary *leaving* a stage."""

    CONCEPT = "concept"
    INITIATION = "initiation"
    DESIGN = "design"
    BUILD = "build"
    VALIDATION = "validation"
    RELEASE = "release"
    CLOSED = "closed"


STAGE_ORDER: tuple[Stage, ...] = (
    Stage.CONCEPT,
    Stage.INITIATION,
    Stage.DESIGN,
    Stage.BUILD,
    Stage.VALIDATION,
    Stage.RELEASE,
    Stage.CLOSED,
)


class DeliverableKind(str, Enum):
    GAME = "game"
    APPLICATION = "application"
    IMAGE = "image"
    VIDEO = "video"
    DESIGN_SYSTEM = "design_system"
    MODULE = "module"
    TEMPLATE = "template"
    DOCUMENT = "document"


class EvidenceKind(str, Enum):
    """What kind of proof satisfies a criterion, and which Location supplies it."""

    BUSINESS_CASE = "business_case"  # Think Tank / the requester
    DESIGN_REVIEW = "design_review"  # Fabulousa
    ACCESSIBILITY_AUDIT = "accessibility_audit"  # Fabulousa
    BUILD_ARTEFACT = "build_artefact"  # The Artifactory
    SECURITY_SCAN = "security_scan"  # Cryptex
    TEST_RUN = "test_run"  # The Chaos Party
    DOCUMENTATION = "documentation"  # The Library / DocUtari
    APPROVAL = "approval"  # The Town Hall
    LESSONS_LEARNED = "lessons_learned"  # The Basement


class Outcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"


class GateDecision(str, Enum):
    PASSED = "passed"
    WAIVED = "waived"


class GateBlocked(RuntimeError):
    """Raised by `advance` when a mandatory criterion is not satisfied.

    Carries the unmet criteria so a caller can act on them instead of having
    to re-derive what stopped it.
    """

    def __init__(self, deliverable_id: str, stage: Stage, unmet: list["Criterion"]) -> None:
        self.deliverable_id = deliverable_id
        self.stage = stage
        self.unmet = unmet
        names = ", ".join(c.id for c in unmet)
        super().__init__(f"{deliverable_id} cannot leave {stage.value}: unmet criteria: {names}")


class GateAlreadyPassed(RuntimeError):
    """Raised when another caller crossed this boundary first.

    Distinct from `GateBlocked`: nothing is missing, the work simply already
    happened. Collapsing the two would tell an operator to go and find
    evidence that is already filed.
    """

    def __init__(self, deliverable_id: str, expected: "Stage", actual: "Stage") -> None:
        self.deliverable_id = deliverable_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"{deliverable_id} was at {expected.value} when the gate was evaluated "
            f"and is now at {actual.value}: another caller advanced it first"
        )


class UnknownDeliverableError(KeyError):
    pass


class UnknownCriterionError(KeyError):
    pass


# Everything with a user interface. Kept as one name because the design and
# accessibility criteria must never drift apart: a thing that gets a design
# review and no accessibility audit is exactly the pairing this platform
# already had in web/, where ARIA attributes are hand-written and nothing
# verifies them.
_INTERACTIVE = (
    DeliverableKind.GAME,
    DeliverableKind.APPLICATION,
    DeliverableKind.DESIGN_SYSTEM,
    DeliverableKind.TEMPLATE,
)
_BUILT = (
    DeliverableKind.GAME,
    DeliverableKind.APPLICATION,
    DeliverableKind.MODULE,
    DeliverableKind.TEMPLATE,
)
_VISUAL = _INTERACTIVE + (DeliverableKind.IMAGE, DeliverableKind.VIDEO)
_ALL = tuple(DeliverableKind)


@dataclass(frozen=True)
class Criterion:
    """One thing that must be evidenced before a deliverable leaves a stage."""

    id: str
    stage: Stage
    evidence_kind: EvidenceKind
    description: str
    supplied_by: str
    applies_to: tuple[DeliverableKind, ...] = _ALL
    mandatory: bool = True

    def applies(self, kind: DeliverableKind) -> bool:
        return kind in self.applies_to

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "stage": self.stage.value,
            "evidence_kind": self.evidence_kind.value,
            "description": self.description,
            "supplied_by": self.supplied_by,
            "applies_to": [k.value for k in self.applies_to],
            "mandatory": self.mandatory,
        }


CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        id="concept.business-case",
        stage=Stage.CONCEPT,
        evidence_kind=EvidenceKind.BUSINESS_CASE,
        description="Why this is worth building, and what it costs to run.",
        supplied_by="Think Tank",
    ),
    Criterion(
        id="initiation.authorised",
        stage=Stage.INITIATION,
        evidence_kind=EvidenceKind.APPROVAL,
        description="The Town Hall has authorised the work to start.",
        supplied_by="The Town Hall",
    ),
    Criterion(
        id="design.reviewed",
        stage=Stage.DESIGN,
        evidence_kind=EvidenceKind.DESIGN_REVIEW,
        description="Fabulousa has reviewed the design against the token set.",
        supplied_by="Fabulousa",
        applies_to=_VISUAL,
    ),
    Criterion(
        id="design.accessible",
        stage=Stage.DESIGN,
        evidence_kind=EvidenceKind.ACCESSIBILITY_AUDIT,
        description="ARIA roles, contrast and keyboard reach audited against WCAG.",
        supplied_by="Fabulousa",
        applies_to=_INTERACTIVE,
    ),
    Criterion(
        id="build.artefact-registered",
        stage=Stage.BUILD,
        evidence_kind=EvidenceKind.BUILD_ARTEFACT,
        description="The build is in The Artifactory and addressable by digest.",
        supplied_by="The Artifactory",
        applies_to=_BUILT,
    ),
    Criterion(
        id="build.scanned",
        stage=Stage.BUILD,
        evidence_kind=EvidenceKind.SECURITY_SCAN,
        description="Cryptex has scanned the build and its dependencies.",
        supplied_by="Cryptex",
        applies_to=_BUILT,
    ),
    Criterion(
        id="validation.tested",
        stage=Stage.VALIDATION,
        evidence_kind=EvidenceKind.TEST_RUN,
        description="The Chaos Party's suite has run against this deliverable.",
        supplied_by="The Chaos Party",
    ),
    Criterion(
        id="release.documented",
        stage=Stage.RELEASE,
        evidence_kind=EvidenceKind.DOCUMENTATION,
        description="Guide, procedure and policy published to The Library.",
        supplied_by="The Library",
    ),
    Criterion(
        id="release.authorised",
        stage=Stage.RELEASE,
        evidence_kind=EvidenceKind.APPROVAL,
        description="The Town Hall has authorised release.",
        supplied_by="The Town Hall",
    ),
    Criterion(
        id="release.lessons",
        stage=Stage.RELEASE,
        evidence_kind=EvidenceKind.LESSONS_LEARNED,
        description="Lessons recorded and archived to The Basement.",
        supplied_by="The Basement",
        mandatory=False,
    ),
)

_CRITERIA_BY_ID = {c.id: c for c in CRITERIA}


def criteria_for(kind: DeliverableKind, stage: Stage) -> list[Criterion]:
    """The criteria a deliverable of this kind must meet to leave this stage."""
    return [c for c in CRITERIA if c.stage is stage and c.applies(kind)]


def criterion(criterion_id: str) -> Optional[Criterion]:
    return _CRITERIA_BY_ID.get(criterion_id)


def next_stage(stage: Stage) -> Optional[Stage]:
    """The stage after this one, or None at the end of the lifecycle."""
    index = STAGE_ORDER.index(stage)
    if index + 1 >= len(STAGE_ORDER):
        return None
    return STAGE_ORDER[index + 1]


@dataclass
class Evidence:
    id: str
    deliverable_id: str
    criterion_id: str
    outcome: Outcome
    reference: str
    recorded_by: str
    recorded_at: float = field(default_factory=time.time)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "deliverable_id": self.deliverable_id,
            "criterion_id": self.criterion_id,
            "outcome": self.outcome.value,
            "reference": self.reference,
            "recorded_by": self.recorded_by,
            "recorded_at": self.recorded_at,
            "detail": self.detail,
        }


@dataclass
class Waiver:
    criterion_id: str
    reason: str
    approver: str
    waived_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "reason": self.reason,
            "approver": self.approver,
            "waived_at": self.waived_at,
        }


@dataclass
class Deliverable:
    id: str
    title: str
    kind: DeliverableKind
    location: str
    stage: Stage = Stage.CONCEPT
    requested_by: str = "system"
    created_at: float = field(default_factory=time.time)
    ownership: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind.value,
            "location": self.location,
            "stage": self.stage.value,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "ownership": self.ownership,
        }


@dataclass
class CriterionStatus:
    criterion: Criterion
    satisfied: bool
    waived: bool = False
    evidence: Optional[Evidence] = None
    waiver: Optional[Waiver] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion.to_dict(),
            "satisfied": self.satisfied,
            "waived": self.waived,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "waiver": self.waiver.to_dict() if self.waiver else None,
        }


@dataclass
class GateStatus:
    deliverable_id: str
    stage: Stage
    criteria: list[CriterionStatus]

    @property
    def unmet(self) -> list[Criterion]:
        """Mandatory criteria that are neither satisfied nor waived."""
        return [
            cs.criterion
            for cs in self.criteria
            if cs.criterion.mandatory and not cs.satisfied and not cs.waived
        ]

    @property
    def can_advance(self) -> bool:
        return not self.unmet

    def to_dict(self) -> dict[str, Any]:
        return {
            "deliverable_id": self.deliverable_id,
            "stage": self.stage.value,
            "can_advance": self.can_advance,
            "unmet": [c.id for c in self.unmet],
            "criteria": [cs.to_dict() for cs in self.criteria],
        }


def _emit(event_type: PlatformEventType, data: dict[str, Any]) -> None:
    """Announce a transition that has already been committed.

    Best-effort, exactly as `src/townhall/itsm.py` documents: the SQLite write
    is the record, the event is the notification. A consumer that missed one
    can still read the row.
    """
    try:
        from src.event_bus import get_event_bus  # noqa: PLC0415

        get_event_bus().emit_async(event_type=event_type.value, data=data, source="townhall.plm")
    except Exception as exc:  # noqa: BLE001 - a notification must not fail the write
        logger.debug("plm: emit %s: %s", event_type.value, exc)


class PlmService:
    """Durable deliverable records whose gates refuse to open unevidenced."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS deliverables (
                    id           TEXT PRIMARY KEY,
                    title        TEXT NOT NULL,
                    kind         TEXT NOT NULL,
                    location     TEXT NOT NULL,
                    stage        TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    created_at   REAL NOT NULL,
                    ownership    TEXT
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    id             TEXT PRIMARY KEY,
                    deliverable_id TEXT NOT NULL,
                    criterion_id   TEXT NOT NULL,
                    outcome        TEXT NOT NULL,
                    reference      TEXT NOT NULL,
                    recorded_by    TEXT NOT NULL,
                    recorded_at    REAL NOT NULL,
                    detail         TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS waivers (
                    deliverable_id TEXT NOT NULL,
                    criterion_id   TEXT NOT NULL,
                    reason         TEXT NOT NULL,
                    approver       TEXT NOT NULL,
                    waived_at      REAL NOT NULL,
                    PRIMARY KEY (deliverable_id, criterion_id)
                );
                CREATE TABLE IF NOT EXISTS gate_decisions (
                    id             TEXT PRIMARY KEY,
                    deliverable_id TEXT NOT NULL,
                    stage          TEXT NOT NULL,
                    decision       TEXT NOT NULL,
                    approver       TEXT NOT NULL,
                    decided_at     REAL NOT NULL,
                    waived_criteria TEXT DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_deliverable
                    ON evidence(deliverable_id, criterion_id, recorded_at);
                CREATE INDEX IF NOT EXISTS idx_decisions_deliverable
                    ON gate_decisions(deliverable_id, decided_at);
            """)
            self._conn.commit()

    # ── deliverables ────────────────────────────────────────────────────────

    def create(
        self,
        title: str,
        kind: DeliverableKind | str,
        location: str,
        requested_by: str = "system",
    ) -> Deliverable:
        kind = DeliverableKind(kind)
        ownership = self._ownership(location)
        item = Deliverable(
            id=f"PLM-{uuid.uuid4().hex[:10].upper()}",
            title=title,
            kind=kind,
            location=location,
            requested_by=requested_by,
            ownership=ownership,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO deliverables "
                "(id, title, kind, location, stage, requested_by, created_at, ownership) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    item.id,
                    item.title,
                    item.kind.value,
                    item.location,
                    item.stage.value,
                    item.requested_by,
                    item.created_at,
                    json.dumps(ownership) if ownership else None,
                ),
            )
            self._conn.commit()
        _emit(PlatformEventType.PLM_DELIVERABLE_RAISED, item.to_dict())
        return item

    @staticmethod
    def _ownership(location: str) -> Optional[dict[str, Any]]:
        """Who answers for the Location building this, via the CMDB spine."""
        try:
            from src.townhall.itsm import resolve_ownership  # noqa: PLC0415

            return resolve_ownership(location).to_dict()
        except Exception as exc:  # noqa: BLE001 - a missing owner is recorded, not fatal
            # %r, not %s: `location` arrives in a request body, and a raw newline
            # in it would forge a second log record.
            logger.debug("plm: ownership for %r: %r", location, exc)
            return None

    def get(self, deliverable_id: str) -> Deliverable:
        row = self._conn.execute(
            "SELECT * FROM deliverables WHERE id=?", (deliverable_id,)
        ).fetchone()
        if row is None:
            raise UnknownDeliverableError(deliverable_id)
        return Deliverable(
            id=row["id"],
            title=row["title"],
            kind=DeliverableKind(row["kind"]),
            location=row["location"],
            stage=Stage(row["stage"]),
            requested_by=row["requested_by"],
            created_at=row["created_at"],
            ownership=json.loads(row["ownership"]) if row["ownership"] else None,
        )

    def list_deliverables(self, stage: Optional[Stage] = None) -> list[Deliverable]:
        if stage is None:
            rows = self._conn.execute(
                "SELECT id FROM deliverables ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id FROM deliverables WHERE stage=? ORDER BY created_at DESC",
                (stage.value,),
            ).fetchall()
        return [self.get(r["id"]) for r in rows]

    # ── evidence and waivers ────────────────────────────────────────────────

    def submit_evidence(
        self,
        deliverable_id: str,
        criterion_id: str,
        reference: str,
        outcome: Outcome | str = Outcome.PASS,
        recorded_by: str = "system",
        detail: str = "",
    ) -> Evidence:
        """Record proof against a criterion — including proof that it failed.

        An unknown criterion is rejected rather than stored. Evidence filed
        against a name no gate reads would satisfy nothing while looking, in
        every listing, exactly like evidence that did.
        """
        self.get(deliverable_id)  # raises for an unknown deliverable
        if criterion_id not in _CRITERIA_BY_ID:
            raise UnknownCriterionError(criterion_id)
        if not reference.strip():
            # Evidence is a pointer to the thing that was done — a run id, a
            # digest, a document. Without one the gate opens on an assertion,
            # which is the state this module exists to end.
            raise ValueError("evidence needs a reference to what was produced")
        if not recorded_by.strip():
            raise ValueError("evidence needs to say who recorded it")
        outcome = Outcome(outcome)
        ev = Evidence(
            id=f"EV-{uuid.uuid4().hex[:10].upper()}",
            deliverable_id=deliverable_id,
            criterion_id=criterion_id,
            outcome=outcome,
            reference=reference,
            recorded_by=recorded_by,
            detail=detail,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO evidence "
                "(id, deliverable_id, criterion_id, outcome, reference, recorded_by, "
                "recorded_at, detail) VALUES (?,?,?,?,?,?,?,?)",
                (
                    ev.id,
                    ev.deliverable_id,
                    ev.criterion_id,
                    ev.outcome.value,
                    ev.reference,
                    ev.recorded_by,
                    ev.recorded_at,
                    ev.detail,
                ),
            )
            self._conn.commit()
        _emit(PlatformEventType.PLM_EVIDENCE_RECORDED, ev.to_dict())
        return ev

    def waive(self, deliverable_id: str, criterion_id: str, reason: str, approver: str) -> Waiver:
        """Excuse one criterion, on the record.

        Both a reason and an approver are required. A waiver with neither is
        indistinguishable from the work having been done, which is the state
        this whole module exists to prevent.
        """
        self.get(deliverable_id)
        if criterion_id not in _CRITERIA_BY_ID:
            raise UnknownCriterionError(criterion_id)
        if not reason.strip():
            raise ValueError("a waiver needs a written reason")
        if not approver.strip():
            raise ValueError("a waiver needs a named approver")
        waiver = Waiver(criterion_id=criterion_id, reason=reason, approver=approver)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO waivers "
                "(deliverable_id, criterion_id, reason, approver, waived_at) VALUES (?,?,?,?,?)",
                (deliverable_id, criterion_id, reason, approver, waiver.waived_at),
            )
            self._conn.commit()
        _emit(
            PlatformEventType.PLM_CRITERION_WAIVED,
            dict(waiver.to_dict(), deliverable_id=deliverable_id),
        )
        return waiver

    def _latest_evidence(self, deliverable_id: str, criterion_id: str) -> Optional[Evidence]:
        """The most recent evidence wins, so a failing re-run un-satisfies."""
        row = self._conn.execute(
            "SELECT * FROM evidence WHERE deliverable_id=? AND criterion_id=? "
            "ORDER BY recorded_at DESC, rowid DESC LIMIT 1",
            (deliverable_id, criterion_id),
        ).fetchone()
        if row is None:
            return None
        return Evidence(
            id=row["id"],
            deliverable_id=row["deliverable_id"],
            criterion_id=row["criterion_id"],
            outcome=Outcome(row["outcome"]),
            reference=row["reference"],
            recorded_by=row["recorded_by"],
            recorded_at=row["recorded_at"],
            detail=row["detail"],
        )

    def _waiver(self, deliverable_id: str, criterion_id: str) -> Optional[Waiver]:
        row = self._conn.execute(
            "SELECT * FROM waivers WHERE deliverable_id=? AND criterion_id=?",
            (deliverable_id, criterion_id),
        ).fetchone()
        if row is None:
            return None
        return Waiver(
            criterion_id=row["criterion_id"],
            reason=row["reason"],
            approver=row["approver"],
            waived_at=row["waived_at"],
        )

    # ── the gate ────────────────────────────────────────────────────────────

    def gate_status(self, deliverable_id: str) -> GateStatus:
        """What this deliverable still needs before it can leave its stage."""
        return self._gate_status_for(self.get(deliverable_id))

    def _gate_status_for(self, item: Deliverable) -> GateStatus:
        """Gate status for an already-read deliverable, against *its* stage.

        `advance` evaluates the gate and then writes conditionally on the
        same stage. If this re-read the row instead, a caller acting on a
        stale view would be judged against a boundary it was not trying to
        cross, and would be told a criterion is missing when the real answer
        is that somebody else already advanced it.
        """
        deliverable_id = item.id
        statuses = []
        for crit in criteria_for(item.kind, item.stage):
            ev = self._latest_evidence(deliverable_id, crit.id)
            waiver = self._waiver(deliverable_id, crit.id)
            statuses.append(
                CriterionStatus(
                    criterion=crit,
                    # Only a PASS satisfies. A FAIL is evidence against, and a
                    # PENDING is evidence that somebody started.
                    satisfied=ev is not None and ev.outcome is Outcome.PASS,
                    waived=waiver is not None,
                    evidence=ev,
                    waiver=waiver,
                )
            )
        return GateStatus(deliverable_id=deliverable_id, stage=item.stage, criteria=statuses)

    def advance(self, deliverable_id: str, approver: str = "system") -> Deliverable:
        """Move the deliverable through its gate, or refuse and say why.

        Raises `GateBlocked` rather than returning a warning. A gate a caller
        can ignore is a report, and this platform has enough of those.
        """
        return self._advance_from(self.get(deliverable_id), approver=approver)

    def _advance_from(self, item: Deliverable, approver: str = "system") -> Deliverable:
        """Advance from an already-read deliverable.

        Split out from `advance` so the stale-read case is reachable in a
        test: the race this guards against is exactly "act on a view of the
        stage that another caller has already moved past", and a test that
        can only go through `advance` re-reads the fresh stage every time and
        can never construct it.
        """
        deliverable_id = item.id
        following = next_stage(item.stage)
        if following is None:
            raise GateBlocked(deliverable_id, item.stage, [])

        status = self._gate_status_for(item)
        if not status.can_advance:
            _emit(
                PlatformEventType.PLM_GATE_BLOCKED,
                {
                    "deliverable_id": deliverable_id,
                    "stage": item.stage.value,
                    "unmet": [c.id for c in status.unmet],
                },
            )
            raise GateBlocked(deliverable_id, item.stage, status.unmet)

        waived = [cs.criterion.id for cs in status.criteria if cs.waived and not cs.satisfied]
        decision = GateDecision.WAIVED if waived else GateDecision.PASSED
        now = time.time()
        with self._lock:
            # The stage read above happened outside this lock, so two callers
            # can both see `concept` and both arrive here. The UPDATE is
            # therefore conditional on the stage still being what was
            # evaluated: whichever transaction lands second changes no row,
            # and is refused rather than writing a second gate decision for a
            # boundary that was already crossed.
            #
            # `self._lock` alone would not do it — it coordinates threads in
            # one process, and this worker can run under several.
            cursor = self._conn.execute(
                "UPDATE deliverables SET stage=? WHERE id=? AND stage=?",
                (following.value, deliverable_id, item.stage.value),
            )
            if cursor.rowcount == 0:
                self._conn.rollback()
                current = self.get(deliverable_id)
                raise GateAlreadyPassed(deliverable_id, item.stage, current.stage)
            self._conn.execute(
                "INSERT INTO gate_decisions "
                "(id, deliverable_id, stage, decision, approver, decided_at, waived_criteria) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    f"GD-{uuid.uuid4().hex[:10].upper()}",
                    deliverable_id,
                    item.stage.value,
                    decision.value,
                    approver,
                    now,
                    json.dumps(waived),
                ),
            )
            self._conn.commit()

        payload = {
            "deliverable_id": deliverable_id,
            "from_stage": item.stage.value,
            "to_stage": following.value,
            "decision": decision.value,
            "waived_criteria": waived,
            "approver": approver,
        }
        _emit(PlatformEventType.PLM_GATE_PASSED, payload)
        if following is Stage.CLOSED:
            _emit(PlatformEventType.PLM_DELIVERABLE_CLOSED, payload)
        return self.get(deliverable_id)

    def history(self, deliverable_id: str) -> list[dict[str, Any]]:
        """Every gate decision made about this deliverable, oldest first."""
        self.get(deliverable_id)
        rows = self._conn.execute(
            "SELECT * FROM gate_decisions WHERE deliverable_id=? ORDER BY decided_at ASC",
            (deliverable_id,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "stage": r["stage"],
                "decision": r["decision"],
                "approver": r["approver"],
                "decided_at": r["decided_at"],
                "waived_criteria": json.loads(r["waived_criteria"]),
            }
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()


_service: Optional[PlmService] = None


def get_plm() -> PlmService:
    global _service
    if _service is None:
        _service = PlmService()
    return _service


def reset_plm() -> None:
    """Drop the module-level service. For tests that supply their own path."""
    global _service
    if _service is not None:
        _service.close()
    _service = None
