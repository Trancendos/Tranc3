"""What a request-path gate decides, and why it can be checked.

The gap this fills
------------------
The platform already has a request-path gate. `MagnaCartaMiddleware` is
installed on the app at `api.py:757`, inside `ZeroTrustASGIMiddleware` so it
can read decoded claims, and it evaluates the Magna Carta rules on every
request.

Two things stop it being a control. `MAGNA_CARTA_ENABLED` defaults to
`false` — in `src/compliance/magna_carta.py:16` and again in
`docker-compose.production.yml` as `${MAGNA_CARTA_ENABLED:-false}` — so
`dispatch` returns `call_next(request)` before a single rule runs. And when
it is switched on it is advisory: the outcome is a boolean `compliant`, and
blocking needs a second flag in a config file.

A boolean also cannot express what governance actually needs. "Not
compliant" collapses four different responses into one: refuse it, hold it
for a human, strip the offending part and continue, or continue with less
capability. This module is that missing vocabulary, and the deterministic
resolver over it.

It deliberately does not flip the default. Turning a security control from
advisory to enforcing changes production behaviour and is the owner's
decision, not a side effect of adding the decision model it was missing.

Why deterministic
-----------------
The same context and the same policy version must produce the same outcome,
every time, with no model in the path. A gate whose answer depends on an
LLM's mood cannot be replayed from a trace, cannot be regression-tested, and
cannot be explained to an auditor. Models may classify, score and recommend
*into* the context; they never decide.

Failing closed, and failing safe
--------------------------------
When policy cannot be read, the answer depends on what is at stake. For a
high-risk or prohibited action the gate refuses — an unenforceable control
on a consequential action is worse than an outage, because it looks like it
worked. For minimal and limited risk it degrades instead, because refusing
everything the moment a policy store hiccups teaches operators to disable
the gate, which is the failure it exists to prevent.

An unrecognised risk tier is treated as the *highest*, never the lowest.
That is the whole ballgame: the fail-open version of this module is one that
maps an unknown tier to `minimal` and waves it through.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from src.compliance.ai_governance import RiskTier

__all__ = [
    "Decision",
    "GateContext",
    "GateOutcome",
    "Violation",
    "decide",
    "fails_closed",
]


class Decision(str, Enum):
    """What the gate does about a request."""

    ALLOW = "allow"
    BLOCK = "block"
    HOLD = "hold"  # pause for a named human approver
    REDACT = "redact"  # continue without the offending content
    DEGRADE = "degrade"  # continue with reduced capability


#: Ascending severity. A request carrying several violations takes the
#: strongest response any one of them demands — ordered by how much it
#: withholds from the caller, not alphabetically.
_SEVERITY: tuple[Decision, ...] = (
    Decision.ALLOW,
    Decision.DEGRADE,
    Decision.REDACT,
    Decision.HOLD,
    Decision.BLOCK,
)


def _rank(decision: Decision) -> int:
    return _SEVERITY.index(decision)


#: Tiers where an unenforceable control must refuse rather than proceed.
#: UNACCEPTABLE is Article 5 — prohibited outright — and HIGH is Annex III.
_FAIL_CLOSED_TIERS = frozenset({RiskTier.HIGH, RiskTier.UNACCEPTABLE})


def fails_closed(tier: RiskTier) -> bool:
    """Does an unreadable policy refuse this tier, or degrade it?"""
    return tier in _FAIL_CLOSED_TIERS


@dataclass(frozen=True)
class Violation:
    """One rule that the request did not satisfy."""

    control_id: str
    reason: str
    #: What this rule alone demands. The resolver takes the strongest across
    #: all violations; a rule cannot weaken another rule's response.
    demands: Decision = Decision.BLOCK

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "reason": self.reason,
            "demands": self.demands.value,
        }


@dataclass(frozen=True)
class GateContext:
    """Everything the decision is a function of.

    Frozen, because a gate that can be re-decided after its context was
    mutated is not replayable — and replay from a trace bundle is the only
    way to answer "why was this allowed" six months later.
    """

    trace_id: str
    tenant_id: str
    actor_id: str
    action: str
    risk_tier: RiskTier = RiskTier.MINIMAL
    purpose: str = ""
    policy_version: str = ""
    data_tags: tuple[str, ...] = ()
    agent_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "action": self.action,
            "risk_tier": self.risk_tier.value,
            "purpose": self.purpose,
            "policy_version": self.policy_version,
            "data_tags": list(self.data_tags),
            "agent_id": self.agent_id,
        }


@dataclass(frozen=True)
class GateOutcome:
    """The decision, and enough of its working to audit it."""

    decision: Decision
    context: GateContext
    control_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    policy_available: bool = True

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "control_ids": list(self.control_ids),
            "reasons": list(self.reasons),
            "policy_available": self.policy_available,
            "context": self.context.to_dict(),
        }


def _coerce_tier(tier: Any) -> RiskTier:
    """Resolve a tier, treating anything unrecognised as the highest.

    This is the fail-open the module exists to avoid. A context arriving
    with `risk_tier=None`, an empty string, or a tier name from a newer
    policy version must not be handled as `minimal` — that is precisely the
    request nobody classified, which is the one most likely to need the
    gate.
    """
    if isinstance(tier, RiskTier):
        return tier
    try:
        return RiskTier(str(tier).strip().lower())
    except (ValueError, AttributeError):
        return RiskTier.UNACCEPTABLE


def decide(
    context: GateContext,
    violations: Optional[list[Violation]] = None,
    *,
    policy_available: bool = True,
) -> GateOutcome:
    """Resolve one request to a decision.

    Pure: no clock, no randomness, no I/O, no model. The same arguments give
    the same outcome, which is what makes a trace replayable and a policy
    change regression-testable.
    """
    tier = _coerce_tier(context.risk_tier)
    context = (
        context
        if context.risk_tier is tier
        else GateContext(**{**context.__dict__, "risk_tier": tier})
    )
    found = list(violations or [])

    # Article 5: prohibited outright. No violation is needed to refuse it,
    # and no clean evaluation can excuse it.
    if tier is RiskTier.UNACCEPTABLE:
        return GateOutcome(
            decision=Decision.BLOCK,
            context=context,
            control_ids=tuple(v.control_id for v in found) or ("RISK-TIER-UNACCEPTABLE",),
            reasons=(
                "risk tier is unacceptable — prohibited under EU AI Act Article 5",
                *(v.reason for v in found),
            ),
            policy_available=policy_available,
        )

    if not policy_available:
        if fails_closed(tier):
            return GateOutcome(
                decision=Decision.BLOCK,
                context=context,
                control_ids=("POLICY-UNAVAILABLE",),
                reasons=(
                    f"policy could not be read and risk tier {tier.value} fails closed: "
                    "an unenforceable control on a consequential action is worse than "
                    "an outage, because it looks like it worked",
                ),
                policy_available=False,
            )
        return GateOutcome(
            decision=Decision.DEGRADE,
            context=context,
            control_ids=("POLICY-UNAVAILABLE",),
            reasons=(
                f"policy could not be read; risk tier {tier.value} continues with "
                "reduced capability rather than refusing, so a policy-store outage "
                "does not teach operators to disable the gate",
            ),
            policy_available=False,
        )

    if not found:
        return GateOutcome(decision=Decision.ALLOW, context=context, policy_available=True)

    strongest = max((v.demands for v in found), key=_rank)
    return GateOutcome(
        decision=strongest,
        context=context,
        control_ids=tuple(v.control_id for v in found),
        reasons=tuple(v.reason for v in found),
        policy_available=True,
    )
