# src/models/governance.py
"""Trancendos Models Matrix — governed model-advancement pipeline.

Real skill/feature advancement, benchmarked and gated through three
review stages before it's baked into a named AI's model:

    Prime review      -> rejects proposals with minimal advancement
    Cornelius review  -> assesses Skills & Features, calculates a %,
                         only proceeds if it clears Cornelius's own
                         (higher) bar
    Human approval    -> final sign-off

Each stage's decision, reviewer, notes, and % figures are recorded — this
is what stops routine/minor updates from being silently baked into a
model, and gives real advancements a paper trail through the Trancendos
Universal Network's governance layer, per docs/governance/
TRANCENDOS-MODELS-MATRIX.md.

A proposal reaching APPROVED does *not* auto-mutate `matrix.py`'s
MODEL_VARIANTS at runtime — that table is intentionally a static,
code-reviewed registry (see its own docstring). APPROVED is the signal
that a specialized-variant code change is now justified and should be
made in a follow-up PR, not an instruction to self-modify.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from src.models.benchmark import BenchmarkRegistry, compute_advancement_pct, get_benchmark_registry

DEFAULT_DB_PATH = Path("data/models_governance.db")

# Below this % advancement, the Prime rejects outright — stops routine/minor
# updates from ever reaching Cornelius or a Human.
PRIME_MIN_ADVANCEMENT_PCT = 3.0

# Cornelius's own bar is higher than the Prime's — a real Skills & Features
# assessment, not just the raw benchmark delta the Prime screens on.
CORNELIUS_MIN_ADVANCEMENT_PCT = 8.0


class ProposalStage(str, Enum):
    PRIME_REVIEW = "prime_review"
    REJECTED_BY_PRIME = "rejected_by_prime"
    CORNELIUS_REVIEW = "cornelius_review"
    REJECTED_BY_CORNELIUS = "rejected_by_cornelius"
    HUMAN_REVIEW = "human_review"
    APPROVED = "approved"
    REJECTED_BY_HUMAN = "rejected_by_human"


class InvalidStageTransitionError(ValueError):
    """Raised when a review is attempted on a proposal not currently
    awaiting that reviewer's stage."""


class InsufficientBenchmarkHistoryError(ValueError):
    """Raised when a proposal is submitted for a (model, skill_domain) pair
    that doesn't yet have at least two recorded benchmark scans — there's
    no prior baseline to measure an advancement % against."""


@dataclass
class AdvancementProposal:
    id: int
    model_name: str
    skill_domain: str
    prior_score: float
    new_score: float
    advancement_pct: float
    stage: ProposalStage
    submitted_by: str
    submitted_at: float
    prime_reviewer: Optional[str] = None
    prime_notes: str = ""
    prime_decided_at: Optional[float] = None
    cornelius_reviewer: Optional[str] = None
    cornelius_assessed_pct: Optional[float] = None
    cornelius_notes: str = ""
    cornelius_decided_at: Optional[float] = None
    human_decider: Optional[str] = None
    human_approved: Optional[bool] = None
    human_notes: str = ""
    human_decided_at: Optional[float] = None


def _emit_governance_event(event_type: str, proposal: AdvancementProposal, **extra) -> None:
    """Best-effort audit trail via The Observatory — mirrors the
    non-fatal-on-failure pattern used by src/roles/registry.py's
    _emit_relations_event(), since a governance-stage transition must
    never fail just because Observatory is unavailable in a given
    runtime/test context."""
    try:
        from src.observability.observatory import EventCategory, EventSeverity, observe

        observe(
            event_type,
            actor=extra.pop("actor", "system"),
            target=f"model:{proposal.model_name}",
            category=EventCategory.GOVERNANCE,
            severity=EventSeverity.INFO,
            metadata={
                "proposal_id": proposal.id,
                "skill_domain": proposal.skill_domain,
                "advancement_pct": proposal.advancement_pct,
                "stage": proposal.stage.value,
                **extra,
            },
        )
    except Exception:
        pass


class ModelGovernanceRegistry:
    """SQLite-backed registry of model-advancement proposals and their
    Prime -> Cornelius -> Human review trail."""

    def __init__(
        self,
        db_path: "str | Path" = DEFAULT_DB_PATH,
        benchmark_registry: Optional[BenchmarkRegistry] = None,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._benchmarks = benchmark_registry or get_benchmark_registry()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS advancement_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                skill_domain TEXT NOT NULL,
                prior_score REAL NOT NULL,
                new_score REAL NOT NULL,
                advancement_pct REAL NOT NULL,
                stage TEXT NOT NULL,
                submitted_by TEXT NOT NULL,
                submitted_at REAL NOT NULL,
                prime_reviewer TEXT,
                prime_notes TEXT NOT NULL DEFAULT '',
                prime_decided_at REAL,
                cornelius_reviewer TEXT,
                cornelius_assessed_pct REAL,
                cornelius_notes TEXT NOT NULL DEFAULT '',
                cornelius_decided_at REAL,
                human_decider TEXT,
                human_approved INTEGER,
                human_notes TEXT NOT NULL DEFAULT '',
                human_decided_at REAL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_proposals_model_stage "
            "ON advancement_proposals(model_name, stage)"
        )
        self._conn.commit()

    def _row_to_proposal(self, row: sqlite3.Row) -> AdvancementProposal:
        return AdvancementProposal(
            id=row["id"],
            model_name=row["model_name"],
            skill_domain=row["skill_domain"],
            prior_score=row["prior_score"],
            new_score=row["new_score"],
            advancement_pct=row["advancement_pct"],
            stage=ProposalStage(row["stage"]),
            submitted_by=row["submitted_by"],
            submitted_at=row["submitted_at"],
            prime_reviewer=row["prime_reviewer"],
            prime_notes=row["prime_notes"],
            prime_decided_at=row["prime_decided_at"],
            cornelius_reviewer=row["cornelius_reviewer"],
            cornelius_assessed_pct=row["cornelius_assessed_pct"],
            cornelius_notes=row["cornelius_notes"],
            cornelius_decided_at=row["cornelius_decided_at"],
            human_decider=row["human_decider"],
            human_approved=(
                bool(row["human_approved"]) if row["human_approved"] is not None else None
            ),
            human_notes=row["human_notes"],
            human_decided_at=row["human_decided_at"],
        )

    def _get(self, proposal_id: int) -> Optional[AdvancementProposal]:
        cur = self._conn.execute("SELECT * FROM advancement_proposals WHERE id = ?", (proposal_id,))
        row = cur.fetchone()
        return self._row_to_proposal(row) if row else None

    # ------------------------------------------------------------------
    # Submission — auto-computes advancement_pct from the benchmark registry
    # ------------------------------------------------------------------

    def submit_proposal(
        self, model_name: str, skill_domain: str, submitted_by: str = "system"
    ) -> AdvancementProposal:
        """Open a new advancement proposal from the latest two benchmark
        scans on record for (model_name, skill_domain)."""
        latest, prior = self._benchmarks.latest_two(model_name, skill_domain)
        if latest is None or prior is None:
            raise InsufficientBenchmarkHistoryError(
                f"Need at least 2 benchmark scans for {model_name!r}/{skill_domain!r} "
                f"to compute an advancement % — only found "
                f"{0 if latest is None else 1}"
            )
        advancement_pct = compute_advancement_pct(prior.score, latest.score)
        with self._lock:
            now = time.time()
            cur = self._conn.execute(
                "INSERT INTO advancement_proposals "
                "(model_name, skill_domain, prior_score, new_score, advancement_pct, "
                "stage, submitted_by, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    model_name,
                    skill_domain,
                    prior.score,
                    latest.score,
                    advancement_pct,
                    ProposalStage.PRIME_REVIEW.value,
                    submitted_by,
                    now,
                ),
            )
            self._conn.commit()
            proposal = self._get(cur.lastrowid)
        _emit_governance_event("model.advancement.submitted", proposal, actor=submitted_by)
        return proposal

    # ------------------------------------------------------------------
    # Stage 1 — Prime review
    # ------------------------------------------------------------------

    def prime_review(self, proposal_id: int, reviewer: str, notes: str = "") -> AdvancementProposal:
        """A Prime screens the raw benchmark advancement %. Below
        PRIME_MIN_ADVANCEMENT_PCT, the Prime rejects outright — this is
        exactly what stops minor/routine updates from ever reaching
        Cornelius or a Human."""
        with self._lock:
            proposal = self._get(proposal_id)
            if proposal is None:
                raise KeyError(f"No advancement proposal with id={proposal_id}")
            if proposal.stage != ProposalStage.PRIME_REVIEW:
                raise InvalidStageTransitionError(
                    f"Proposal {proposal_id} is in stage {proposal.stage.value!r}, "
                    f"not awaiting Prime review"
                )
            now = time.time()
            passed = proposal.advancement_pct >= PRIME_MIN_ADVANCEMENT_PCT
            next_stage = (
                ProposalStage.CORNELIUS_REVIEW if passed else ProposalStage.REJECTED_BY_PRIME
            )
            self._conn.execute(
                "UPDATE advancement_proposals SET stage = ?, prime_reviewer = ?, "
                "prime_notes = ?, prime_decided_at = ? WHERE id = ?",
                (next_stage.value, reviewer, notes, now, proposal_id),
            )
            self._conn.commit()
            proposal = self._get(proposal_id)
        _emit_governance_event(
            "model.advancement.prime_reviewed",
            proposal,
            actor=reviewer,
            passed=passed,
            threshold_pct=PRIME_MIN_ADVANCEMENT_PCT,
        )
        return proposal

    # ------------------------------------------------------------------
    # Stage 2 — Cornelius review
    # ------------------------------------------------------------------

    def cornelius_review(
        self,
        proposal_id: int,
        reviewer: str = "Cornelius MacIntyre",
        assessed_pct: Optional[float] = None,
        notes: str = "",
    ) -> AdvancementProposal:
        """Cornelius assesses Skills & Features and calculates a %
        (defaults to the raw benchmark advancement_pct if a distinct
        qualitative assessment isn't supplied). Below
        CORNELIUS_MIN_ADVANCEMENT_PCT, Cornelius rejects; otherwise the
        proposal is presented to a Human for final approval."""
        with self._lock:
            proposal = self._get(proposal_id)
            if proposal is None:
                raise KeyError(f"No advancement proposal with id={proposal_id}")
            if proposal.stage != ProposalStage.CORNELIUS_REVIEW:
                raise InvalidStageTransitionError(
                    f"Proposal {proposal_id} is in stage {proposal.stage.value!r}, "
                    f"not awaiting Cornelius review"
                )
            effective_pct = proposal.advancement_pct if assessed_pct is None else assessed_pct
            now = time.time()
            passed = effective_pct >= CORNELIUS_MIN_ADVANCEMENT_PCT
            next_stage = (
                ProposalStage.HUMAN_REVIEW if passed else ProposalStage.REJECTED_BY_CORNELIUS
            )
            self._conn.execute(
                "UPDATE advancement_proposals SET stage = ?, cornelius_reviewer = ?, "
                "cornelius_assessed_pct = ?, cornelius_notes = ?, cornelius_decided_at = ? "
                "WHERE id = ?",
                (next_stage.value, reviewer, effective_pct, notes, now, proposal_id),
            )
            self._conn.commit()
            proposal = self._get(proposal_id)
        _emit_governance_event(
            "model.advancement.cornelius_reviewed",
            proposal,
            actor=reviewer,
            passed=passed,
            threshold_pct=CORNELIUS_MIN_ADVANCEMENT_PCT,
        )
        return proposal

    # ------------------------------------------------------------------
    # Stage 3 — Human approval
    # ------------------------------------------------------------------

    def human_decide(
        self, proposal_id: int, approved: bool, decided_by: str, notes: str = ""
    ) -> AdvancementProposal:
        """Final Human sign-off. Does not itself mutate matrix.py's
        MODEL_VARIANTS — see this module's docstring."""
        with self._lock:
            proposal = self._get(proposal_id)
            if proposal is None:
                raise KeyError(f"No advancement proposal with id={proposal_id}")
            if proposal.stage != ProposalStage.HUMAN_REVIEW:
                raise InvalidStageTransitionError(
                    f"Proposal {proposal_id} is in stage {proposal.stage.value!r}, "
                    f"not awaiting Human review"
                )
            now = time.time()
            next_stage = ProposalStage.APPROVED if approved else ProposalStage.REJECTED_BY_HUMAN
            self._conn.execute(
                "UPDATE advancement_proposals SET stage = ?, human_decider = ?, "
                "human_approved = ?, human_notes = ?, human_decided_at = ? WHERE id = ?",
                (next_stage.value, decided_by, int(approved), notes, now, proposal_id),
            )
            self._conn.commit()
            proposal = self._get(proposal_id)
        _emit_governance_event(
            "model.advancement.human_decided", proposal, actor=decided_by, approved=approved
        )
        return proposal

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, proposal_id: int) -> Optional[AdvancementProposal]:
        with self._lock:
            return self._get(proposal_id)

    def list_proposals(
        self, stage: Optional[ProposalStage] = None, model_name: Optional[str] = None
    ) -> List[AdvancementProposal]:
        with self._lock:
            query = "SELECT * FROM advancement_proposals WHERE 1=1"
            params: list = []
            if stage is not None:
                query += " AND stage = ?"
                params.append(stage.value)
            if model_name is not None:
                query += " AND model_name = ?"
                params.append(model_name)
            query += " ORDER BY submitted_at DESC"
            cur = self._conn.execute(query, params)
            return [self._row_to_proposal(row) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()


_registry: Optional[ModelGovernanceRegistry] = None
_registry_lock = threading.Lock()


def get_governance_registry() -> ModelGovernanceRegistry:
    """Module-level singleton, matching the `get_<x>()` pattern used across
    this codebase."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ModelGovernanceRegistry()
    return _registry
