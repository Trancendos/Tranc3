"""Calibration for the request-path gate decision model.

The platform already had a request-path gate — `MagnaCartaMiddleware`,
installed at `api.py:757` — and it was off by default and boolean when on.
These tests protect the two things that make a replacement worth having: a
vocabulary richer than compliant/not-compliant, and a resolver whose failure
modes are chosen rather than incidental.
"""

from __future__ import annotations

import pytest

from src.compliance.ai_governance import RiskTier
from src.gates.decision import (
    Decision,
    GateContext,
    Violation,
    decide,
    fails_closed,
)


def _ctx(tier=RiskTier.MINIMAL, **kwargs) -> GateContext:
    base = {
        "trace_id": "trc_1",
        "tenant_id": "acme",
        "actor_id": "user_1",
        "action": "summarise",
        "risk_tier": tier,
    }
    base.update(kwargs)
    return GateContext(**base)


class TestFailingClosedAndFailingSafe:
    def test_an_unreadable_policy_blocks_a_high_risk_action(self):
        """Calibrated: returning ALLOW when policy is missing fails this.

        An unenforceable control on a consequential action is worse than an
        outage, because it looks like it worked.
        """
        outcome = decide(_ctx(RiskTier.HIGH), policy_available=False)
        assert outcome.decision is Decision.BLOCK
        assert outcome.control_ids == ("POLICY-UNAVAILABLE",)

    def test_an_unreadable_policy_degrades_a_minimal_risk_action(self):
        """Calibrated: blocking every tier on a policy outage fails this.

        Refusing everything the moment a policy store hiccups teaches
        operators to switch the gate off, which is the failure it exists to
        prevent. The distinction between the two branches is the point.
        """
        outcome = decide(_ctx(RiskTier.MINIMAL), policy_available=False)
        assert outcome.decision is Decision.DEGRADE

    def test_the_two_branches_disagree(self):
        """The property both tests above depend on, asserted directly."""
        high = decide(_ctx(RiskTier.HIGH), policy_available=False).decision
        low = decide(_ctx(RiskTier.LIMITED), policy_available=False).decision
        assert high is not low

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [
            (RiskTier.UNACCEPTABLE, True),
            (RiskTier.HIGH, True),
            (RiskTier.LIMITED, False),
            (RiskTier.MINIMAL, False),
        ],
    )
    def test_which_tiers_fail_closed(self, tier, expected):
        assert fails_closed(tier) is expected

    def test_a_policy_outage_is_recorded_on_the_outcome(self):
        """Calibrated: hardcoding policy_available=True fails this.

        A decision taken without policy has to be distinguishable later
        from one taken with it, or the trace cannot explain itself.
        """
        assert decide(_ctx(), policy_available=False).policy_available is False


class TestTheUnknownTier:
    @pytest.mark.parametrize("tier", ["", None, "wat", "critical", 7])
    def test_an_unrecognised_tier_is_treated_as_the_highest(self, tier):
        """Calibrated: falling back to MINIMAL fails this.

        This is the fail-open the module exists to avoid. An unrecognised
        tier is the request nobody classified, which is the one most likely
        to need the gate — mapping it to `minimal` waves exactly that
        through.
        """
        assert decide(_ctx(tier)).decision is Decision.BLOCK

    def test_the_coerced_tier_is_recorded_not_the_junk(self):
        """Calibrated: passing the original context through fails this.

        The trace has to show what the gate actually decided against.
        """
        outcome = decide(_ctx("wat"))
        assert outcome.context.risk_tier is RiskTier.UNACCEPTABLE

    @pytest.mark.parametrize("spelling", ["  HIGH  ", "High", "HIGH", "high"])
    def test_a_tier_spelled_differently_still_resolves(self, spelling):
        """Calibrated: comparing the raw string fails this.

        The assertion is on the *coerced tier*, not the decision, and that
        distinction is the calibration. A high-risk action blocks on a
        policy outage either way — as itself, or as an unrecognised tier
        treated as unacceptable — so asserting the decision passes under the
        mutation it names. Only the recorded tier tells the two apart, and
        an operator reading a trace that says `unacceptable` for a request
        classified `HIGH` would be debugging the wrong thing entirely.
        """
        assert decide(_ctx(spelling)).context.risk_tier is RiskTier.HIGH


class TestProhibitedActions:
    def test_an_unacceptable_tier_blocks_with_no_violation_at_all(self):
        """Calibrated: requiring a violation to block fails this.

        Article 5 prohibits the action outright. A clean rule evaluation
        cannot excuse it, so the block must not depend on one.
        """
        outcome = decide(_ctx(RiskTier.UNACCEPTABLE), [])
        assert outcome.decision is Decision.BLOCK
        assert "Article 5" in " ".join(outcome.reasons)

    def test_it_blocks_even_when_the_policy_is_readable(self):
        outcome = decide(_ctx(RiskTier.UNACCEPTABLE), [], policy_available=True)
        assert outcome.decision is Decision.BLOCK


class TestResolvingSeveralViolations:
    def test_the_strongest_demand_wins(self):
        """Calibrated: taking the first or last violation fails this.

        A rule must not be able to weaken another rule's response by being
        evaluated after it.
        """
        weak_then_strong = [
            Violation("C1", "mask the address", Decision.REDACT),
            Violation("C2", "needs a named approver", Decision.HOLD),
        ]
        assert decide(_ctx(), weak_then_strong).decision is Decision.HOLD
        assert decide(_ctx(), list(reversed(weak_then_strong))).decision is Decision.HOLD

    def test_severity_is_ranked_by_what_is_withheld_not_alphabetically(self):
        """Calibrated: comparing the enum values as strings fails this.

        Sorted as text the order is allow, block, degrade, hold, redact — so
        an alphabetical maximum would rank `redact` above `block` and let a
        prohibited action through with its address masked.
        """
        mixed = [
            Violation("C1", "mask the address", Decision.REDACT),
            Violation("C2", "refuse", Decision.BLOCK),
        ]
        assert decide(_ctx(), mixed).decision is Decision.BLOCK

    def test_a_clean_evaluation_allows(self):
        assert decide(_ctx(), []).decision is Decision.ALLOW

    def test_every_control_id_and_reason_reaches_the_outcome(self):
        """Calibrated: reporting only the winning violation fails this.

        An operator fixing a blocked request needs every rule it tripped,
        not the one that happened to be strongest.
        """
        outcome = decide(
            _ctx(),
            [
                Violation("C1", "mask the address", Decision.REDACT),
                Violation("C2", "needs a named approver", Decision.HOLD),
            ],
        )
        assert outcome.control_ids == ("C1", "C2")
        assert len(outcome.reasons) == 2


class TestDeterminism:
    def test_the_same_context_decides_the_same_way_every_time(self):
        """Calibrated: introducing a clock or randomness fails this.

        A gate whose answer varies cannot be replayed from a trace, which is
        the only way to answer "why was this allowed" months later.
        """
        context = _ctx(RiskTier.HIGH, purpose="plm_change", policy_version="2026.09.04")
        violations = [Violation("C1", "unverified source", Decision.HOLD)]
        first = decide(context, violations).to_dict()
        for _ in range(20):
            assert decide(context, violations).to_dict() == first

    def test_the_context_cannot_be_mutated_after_the_fact(self):
        """Calibrated: making GateContext a plain dataclass fails this.

        A decision re-derived from a mutated context is not the decision
        that was taken.
        """
        context = _ctx()
        with pytest.raises(Exception):
            context.risk_tier = RiskTier.HIGH  # type: ignore[misc]

    def test_the_outcome_serialises_everything_an_audit_needs(self):
        payload = decide(
            _ctx(RiskTier.HIGH, policy_version="2026.09.04"),
            [Violation("C1", "unverified source", Decision.HOLD)],
        ).to_dict()
        assert payload["decision"] == "hold"
        assert payload["context"]["policy_version"] == "2026.09.04"
        assert payload["context"]["trace_id"] == "trc_1"
        assert payload["control_ids"] == ["C1"]


class TestTheGateItReplaces:
    def test_the_existing_middleware_is_installed_but_defaults_to_off(self):
        """The measurement this module was written from, asserted.

        `MagnaCartaMiddleware` is on the app, and `MAGNA_CARTA_ENABLED`
        defaults to false in code and in compose, so `dispatch` returns
        before a single rule runs. This test fails the day someone changes
        that default — which is the moment the docstring here stops being
        true and needs rewriting.
        """
        import pathlib

        repo = pathlib.Path(__file__).resolve().parent.parent
        assert "app.add_middleware(MagnaCartaMiddleware)" in (repo / "api.py").read_text()
        magna = (repo / "src/compliance/magna_carta.py").read_text()
        assert 'os.getenv("MAGNA_CARTA_ENABLED", "false")' in magna
