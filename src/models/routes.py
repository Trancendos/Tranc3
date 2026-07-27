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
from src.models.compliance import (
    OpenProvenanceRiskError,
    ProvenanceStatus,
    check_provenance,
    get_clearance_registry,
    platform_wide_risks,
)
from src.models.governance import (
    AdvancementProposal,
    BoardVote,
    DuplicateBoardVoteError,
    InsufficientBenchmarkHistoryError,
    InvalidStageTransitionError,
    NotAGovernanceBoardMemberError,
    ProposalStage,
    get_governance_registry,
)
from src.models.intervention import (
    Intervention,
    InterventionStatus,
    InterventionType,
    InterventionVote,
    NotASovereignTierModelError,
    get_intervention_registry,
)
from src.models.knowledge import library_context_for
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
        "pipeline": p.pipeline.value,
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
    except OpenProvenanceRiskError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize_proposal(proposal)


# ---------------------------------------------------------------------------
# Provenance — MC-013 training-data-provenance gate (src/models/compliance.py)
# ---------------------------------------------------------------------------


class ClearProvenanceRequest(BaseModel):
    notes: str = ""
    status: str = ProvenanceStatus.CLEARED.value


@router.get("/provenance/{ai_name}")
def get_provenance(ai_name: str) -> Dict[str, Any]:
    result = check_provenance(ai_name)
    return {
        "ai_name": ai_name,
        "cleared": result.cleared,
        "risk": (
            None
            if result.risk is None
            else {
                "entity": result.risk.entity,
                "risk": result.risk.risk,
                "status": result.risk.status.value,
                "note": result.risk.note,
                "mc_reference": result.risk.mc_reference,
            }
        ),
    }


@router.get("/provenance")
def get_platform_wide_provenance_risks() -> List[Dict[str, Any]]:
    """Advisory-only MC-013 risks that apply platform-wide rather than to
    one named AI — see src/models/compliance.py's module docstring."""
    return [
        {
            "entity": r.entity,
            "risk": r.risk,
            "status": r.status.value,
            "note": r.note,
            "mc_reference": r.mc_reference,
        }
        for r in platform_wide_risks()
    ]


@router.post("/provenance/{ai_name}/clear")
def clear_provenance(
    ai_name: str,
    body: ClearProvenanceRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        status = ProvenanceStatus(body.status)
    except ValueError as exc:
        valid = ", ".join(s.value for s in ProvenanceStatus)
        raise HTTPException(
            status_code=422, detail=f"Invalid status {body.status!r} — valid values: {valid}"
        ) from exc
    cleared_by = current_user.get("sub") or current_user.get("id") or "operator"
    get_clearance_registry().clear(
        ai_name, cleared_by=str(cleared_by), notes=body.notes, status=status
    )
    return get_provenance(ai_name)


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


class BoardVoteRequest(BaseModel):
    prime_name: str
    approved: bool
    notes: str = ""


def _serialize_board_vote(v: BoardVote) -> Dict[str, Any]:
    return {
        "proposal_id": v.proposal_id,
        "prime_name": v.prime_name,
        "approved": v.approved,
        "notes": v.notes,
        "voted_at": v.voted_at,
    }


@router.post("/proposals/{proposal_id}/board-vote")
def board_vote(
    proposal_id: int,
    body: BoardVoteRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """One Governance Board member's (T2ance Prime's) vote on a Trance-One
    advancement proposal — see governance.py's board_vote() docstring for
    the unanimous-consent rule."""
    _require_admin(current_user)
    try:
        proposal = get_governance_registry().board_vote(
            proposal_id, prime_name=body.prime_name, approved=body.approved, notes=body.notes
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotAGovernanceBoardMemberError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DuplicateBoardVoteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidStageTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_proposal(proposal)


@router.get("/proposals/{proposal_id}/board-votes")
def get_board_votes(proposal_id: int) -> List[Dict[str, Any]]:
    return [
        _serialize_board_vote(v) for v in get_governance_registry().get_board_votes(proposal_id)
    ]


@router.get("/proposals/{proposal_id}/library-context")
def get_library_context(proposal_id: int) -> Dict[str, Any]:
    """Existing Library articles tagged with this proposal's skill domain —
    read-only context for a reviewer, per docs/governance/
    TRANCENDOS-MODELS-MATRIX.md's "learn from The Library" principle."""
    proposal = get_governance_registry().get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"No proposal with id={proposal_id}")
    return {
        "skill_domain": proposal.skill_domain,
        "articles": library_context_for(proposal.skill_domain),
    }


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


# ---------------------------------------------------------------------------
# Governance Board interventions — failover/repair/override authority over
# a malfunctioning Trance-One (Sovereign) AI. See src/models/intervention.py.
# ---------------------------------------------------------------------------


class RaiseInterventionRequest(BaseModel):
    target_model: str
    intervention_type: str
    reason: str
    raised_by: str


class InterventionVoteRequest(BaseModel):
    prime_name: str
    approved: bool
    notes: str = ""


def _serialize_intervention(iv: Intervention) -> Dict[str, Any]:
    return {
        "id": iv.id,
        "target_model": iv.target_model,
        "intervention_type": iv.intervention_type.value,
        "status": iv.status.value,
        "reason": iv.reason,
        "raised_by": iv.raised_by,
        "raised_at": iv.raised_at,
        "resolved_at": iv.resolved_at,
    }


def _serialize_intervention_vote(v: InterventionVote) -> Dict[str, Any]:
    return {
        "intervention_id": v.intervention_id,
        "prime_name": v.prime_name,
        "approved": v.approved,
        "notes": v.notes,
        "voted_at": v.voted_at,
    }


@router.post("/interventions")
def raise_intervention(
    body: RaiseInterventionRequest, current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        intervention_type = InterventionType(body.intervention_type)
    except ValueError as exc:
        valid = ", ".join(t.value for t in InterventionType)
        raise HTTPException(
            status_code=422,
            detail=f"Invalid intervention_type {body.intervention_type!r} — valid values: {valid}",
        ) from exc
    try:
        intervention = get_intervention_registry().raise_intervention(
            body.target_model, intervention_type, body.reason, raised_by=body.raised_by
        )
    except NotAGovernanceBoardMemberError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except NotASovereignTierModelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize_intervention(intervention)


@router.get("/interventions")
def list_interventions(
    status: Optional[str] = None, target_model: Optional[str] = None
) -> List[Dict[str, Any]]:
    status_enum: Optional[InterventionStatus] = None
    if status is not None:
        try:
            status_enum = InterventionStatus(status)
        except ValueError as exc:
            valid = ", ".join(s.value for s in InterventionStatus)
            raise HTTPException(
                status_code=422, detail=f"Invalid status {status!r} — valid values: {valid}"
            ) from exc
    return [
        _serialize_intervention(iv)
        for iv in get_intervention_registry().list_interventions(
            status=status_enum, target_model=target_model
        )
    ]


@router.get("/interventions/{intervention_id}")
def get_intervention(intervention_id: int) -> Dict[str, Any]:
    intervention = get_intervention_registry().get(intervention_id)
    if intervention is None:
        raise HTTPException(status_code=404, detail=f"No intervention with id={intervention_id}")
    return _serialize_intervention(intervention)


@router.post("/interventions/{intervention_id}/vote")
def intervention_vote(
    intervention_id: int,
    body: InterventionVoteRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        intervention = get_intervention_registry().intervention_vote(
            intervention_id, prime_name=body.prime_name, approved=body.approved, notes=body.notes
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotAGovernanceBoardMemberError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DuplicateBoardVoteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidStageTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _serialize_intervention(intervention)


@router.get("/interventions/{intervention_id}/votes")
def get_intervention_votes(intervention_id: int) -> List[Dict[str, Any]]:
    return [
        _serialize_intervention_vote(v)
        for v in get_intervention_registry().get_intervention_votes(intervention_id)
    ]
