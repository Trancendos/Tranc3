"""Advisory, non-authorising projection of durable Town Hall PLM evidence.

The existing PLM database is the record of work. A PASS record is an operator
assertion, not independent verification of CI, Artifactory or audit provenance.
This module never changes lifecycle state and never grants authority.
"""

from __future__ import annotations

from typing import Any

from src.townhall.decision_bundles import get_bundle


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def summarise_gate_readiness(item: Any, gate: Any) -> dict[str, Any]:
    """Give operators bounded reason codes from one PLM gate snapshot.

    The caller must fetch a consistent deliverable/gate pair. This is advisory:
    it is not a transaction, attestation or permission to call advance().
    """
    stage = _value(item.stage)
    if item.id != gate.deliverable_id or stage != _value(gate.stage):
        raise ValueError("inconsistent PLM snapshot")

    blockers: list[dict[str, str]] = []
    waiver_reviews: list[str] = []
    recorded_evidence: list[dict[str, str]] = []
    for status in gate.criteria:
        criterion = status.criterion
        if not criterion.mandatory:
            continue
        ev = status.evidence
        outcome = _value(ev.outcome) if ev is not None else None
        # Waivers are always surfaced for human review, even if a newer
        # passing record supersedes their practical use.
        if status.waived:
            waiver_reviews.append(criterion.id)

        if ev is not None and outcome == "pass" and status.satisfied:
            recorded_evidence.append(
                {"criterion_id": criterion.id, "evidence_id": ev.id, "outcome": "pass"}
            )
            continue
        if status.waived:
            continue
        if status.satisfied:
            reason = "inconsistent_evidence"
        elif outcome == "fail":
            reason = "failed_evidence"
        elif outcome == "pending":
            reason = "pending_evidence"
        elif ev is None:
            reason = "missing_evidence"
        else:
            reason = "invalid_evidence"
        blockers.append(
            {"criterion_id": criterion.id, "reason": reason, "supplied_by": criterion.supplied_by}
        )

    if not gate.criteria:
        state = "no_current_gate"
    elif blockers:
        state = "blocked"
    elif waiver_reviews:
        state = "waiver_review"
    else:
        state = "recorded_evidence_unverified"

    # The preview bundles are metadata, NOT checks run by the PLM service.
    # In particular, no PRINCE2 score may be converted to an approval here.
    policy_bundle = None
    if stage == "release":
        bundle = get_bundle("release")
        policy_bundle = {
            "version": bundle.version,
            "policy_ids": list(bundle.policy_ids),
            "evaluated": False,
        }
    return {
        "deliverable_id": item.id,
        "stage": stage,
        "kind": _value(item.kind),
        "state": state,
        "blockers": blockers,
        "waiver_reviews": waiver_reviews,
        "recorded_evidence": recorded_evidence,
        "policy_bundle": policy_bundle,
        "independent_evidence_verification": False,
        "preview_only": True,
        "authorization_granted": False,
        "non_atomic_snapshot": True,
    }
