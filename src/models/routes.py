# src/models/routes.py
"""HTTP routes for the Trancendos Models Matrix.

Read routes (matrix, benchmark history, proposal listing) are
unauthenticated, matching `src/roles/routes.py`'s convention for
registry-style modules. Mutating routes (recording a benchmark, submitting
a proposal, and each of the three review stages) require an authenticated
admin — advancing what model powers a platform-wide AI is a governance
action, not a per-user-owned resource.

Handlers are plain `def`, not `async def` — same rationale as
`src/roles/routes.py`: they call synchronous SQLite-backed registries
directly, and FastAPI runs sync handlers in a threadpool instead of on the
event loop.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from src.models.benchmark import BenchmarkResult, get_benchmark_registry
from src.models.governance import (
    AdvancementProposal,
    InsufficientBenchmarkHistoryError,
    InvalidStageTransitionError,
    ProposalStage,
    get_governance_registry,
)
from src.models.matrix import get_variant, list_variants, matrix_summary, resolve_effective_model

router = APIRouter(prefix="/models", tags=["models"])


def _require_admin(current_user: dict) -> None:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403, detail="Admin role required to modify the Models Matrix"
        )


# ---------------------------------------------------------------------------
# Matrix — base tiers + specialized variants
# ---------------------------------------------------------------------------


@router.get("/matrix")
def get_matrix() -> Dict[str, Any]:
    return matrix_summary()


@router.get("/matrix/{ai_name}")
def get_ai_model(ai_name: str) -> Dict[str, Any]:
    variant = get_variant(ai_name)
    return {
        "ai_name": ai_name,
        "effective_model": resolve_effective_model(ai_name),
        "specialized": variant is not None,
        "skill_domain": variant.skill_domain if variant else None,
        "description": variant.description if variant else None,
    }


@router.get("/variants")
def get_variants() -> List[Dict[str, Any]]:
    return [
        {
            "ai_name": v.ai_name,
            "base_tier": v.base_tier,
            "specialized_name": v.specialized_name,
            "skill_domain": v.skill_domain,
            "description": v.description,
        }
        for v in list_variants()
    ]


# ---------------------------------------------------------------------------
# Benchmarking
# ---------------------------------------------------------------------------


class BenchmarkRequest(BaseModel):
    model_name: str
    skill_domain: str
    score: float
    notes: str = ""


def _serialize_benchmark(result: BenchmarkResult) -> Dict[str, Any]:
    return {
        "id": result.id,
        "model_name": result.model_name,
        "skill_domain": result.skill_domain,
        "score": result.score,
        "notes": result.notes,
        "recorded_at": result.recorded_at,
        "recorded_by": result.recorded_by,
    }


@router.post("/benchmark")
def record_benchmark(
    body: BenchmarkRequest, current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    _require_admin(current_user)
    recorded_by = current_user.get("sub") or current_user.get("id") or "operator"
    result = get_benchmark_registry().record_benchmark(
        body.model_name,
        body.skill_domain,
        body.score,
        notes=body.notes,
        recorded_by=str(recorded_by),
    )
    return _serialize_benchmark(result)


@router.get("/benchmark/{model_name:path}")
def get_benchmark_history(
    model_name: str, skill_domain: Optional[str] = None
) -> List[Dict[str, Any]]:
    return [
        _serialize_benchmark(r)
        for r in get_benchmark_registry().history(model_name, skill_domain=skill_domain)
    ]


# ---------------------------------------------------------------------------
# Governance — Prime -> Cornelius -> Human advancement pipeline
# ---------------------------------------------------------------------------


class SubmitProposalRequest(BaseModel):
    model_name: str
    skill_domain: str


class PrimeReviewRequest(BaseModel):
    reviewer: str
    notes: str = ""


class CorneliusReviewRequest(BaseModel):
    reviewer: str = "Cornelius MacIntyre"
    assessed_pct: Optional[float] = None
    notes: str = ""


class HumanDecisionRequest(BaseModel):
    approved: bool
    notes: str = ""


def _serialize_proposal(p: AdvancementProposal) -> Dict[str, Any]:
    return {
        "id": p.id,
        "model_name": p.model_name,
        "skill_domain": p.skill_domain,
        "prior_score": p.prior_score,
        "new_score": p.new_score,
        "advancement_pct": p.advancement_pct,
        "stage": p.stage.value,
        "submitted_by": p.submitted_by,
        "submitted_at": p.submitted_at,
        "prime_reviewer": p.prime_reviewer,
        "prime_notes": p.prime_notes,
        "prime_decided_at": p.prime_decided_at,
        "cornelius_reviewer": p.cornelius_reviewer,
        "cornelius_assessed_pct": p.cornelius_assessed_pct,
        "cornelius_notes": p.cornelius_notes,
        "cornelius_decided_at": p.cornelius_decided_at,
        "human_decider": p.human_decider,
        "human_approved": p.human_approved,
        "human_notes": p.human_notes,
        "human_decided_at": p.human_decided_at,
    }


@router.post("/proposals")
def submit_proposal(
    body: SubmitProposalRequest, current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    _require_admin(current_user)
    submitted_by = current_user.get("sub") or current_user.get("id") or "operator"
    try:
        proposal = get_governance_registry().submit_proposal(
            body.model_name, body.skill_domain, submitted_by=str(submitted_by)
        )
    except InsufficientBenchmarkHistoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize_proposal(proposal)


@router.get("/proposals")
def list_proposals(
    stage: Optional[str] = None, model_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    stage_enum: Optional[ProposalStage] = None
    if stage is not None:
        try:
            stage_enum = ProposalStage(stage)
        except ValueError as exc:
            valid = ", ".join(s.value for s in ProposalStage)
            raise HTTPException(
                status_code=422, detail=f"Invalid stage {stage!r} — valid values: {valid}"
            ) from exc
    return [
        _serialize_proposal(p)
        for p in get_governance_registry().list_proposals(stage=stage_enum, model_name=model_name)
    ]


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: int) -> Dict[str, Any]:
    proposal = get_governance_registry().get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"No proposal with id={proposal_id}")
    return _serialize_proposal(proposal)


@router.post("/proposals/{proposal_id}/prime-review")
def prime_review(
    proposal_id: int,
    body: PrimeReviewRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        proposal = get_governance_registry().prime_review(
            proposal_id, reviewer=body.reviewer, notes=body.notes
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStageTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_proposal(proposal)


@router.post("/proposals/{proposal_id}/cornelius-review")
def cornelius_review(
    proposal_id: int,
    body: CorneliusReviewRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        proposal = get_governance_registry().cornelius_review(
            proposal_id,
            reviewer=body.reviewer,
            assessed_pct=body.assessed_pct,
            notes=body.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStageTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_proposal(proposal)


@router.post("/proposals/{proposal_id}/human-decision")
def human_decision(
    proposal_id: int,
    body: HumanDecisionRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    decided_by = current_user.get("sub") or current_user.get("id") or "operator"
    try:
        proposal = get_governance_registry().human_decide(
            proposal_id, approved=body.approved, decided_by=str(decided_by), notes=body.notes
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStageTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_proposal(proposal)
