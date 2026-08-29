"""Tests for the Arcadian Exchange's adaptive layer.

Three modules, one question each:

    domains.py    who may reclassify a resource, and what may never be earned
    expertise.py  how a seat earns a domain it did not start with, and loses it
    treasury.py   what happens to a gain, and what a shortfall bars

Every test here states a rule the Exchange is supposed to hold and fails if
that rule is removed. The rules that matter most are the refusals — a seat
must not be able to widen its own remit, clear its own loss, or reach the
treasury by being good at something else.
"""

from __future__ import annotations

import pytest

from src.exchange.domains import (
    CAPITAL_AT_RISK,
    RESOURCE_DOMAINS,
    TAXONOMY_OWNER,
    Domain,
    TaxonomyRegistry,
    adjacent_to,
    domain_of,
)
from src.exchange.expertise import (
    EXPANSION_THRESHOLD,
    MIN_OUTCOMES_TO_EXPAND,
    PRIMARY_DOMAINS,
    ExpertiseRegistry,
)
from src.exchange.treasury import Allocation, Treasury


@pytest.fixture
def taxonomy(tmp_path):
    reg = TaxonomyRegistry(db_path=tmp_path / "tax.db")
    yield reg
    reg.close()


@pytest.fixture
def expertise(tmp_path):
    reg = ExpertiseRegistry(db_path=tmp_path / "exp.db")
    yield reg
    reg.close()


@pytest.fixture
def treasury(tmp_path):
    t = Treasury(db_path=tmp_path / "tre.db")
    yield t
    t.close()


class TestTheTaxonomyHasOneOwner:
    """Dorris controls the taxonomy. A seat that could reclassify its own
    resource could move it out of a constrained domain and price it freely."""

    def test_the_owner_may_reclassify(self, taxonomy):
        resource = next(iter(RESOURCE_DOMAINS))
        taxonomy.reclassify(
            resource,
            Domain.KNOWLEDGE,
            changed_by=TAXONOMY_OWNER,
            reason="test reclassification",
        )
        assert taxonomy.effective_domain(resource) is Domain.KNOWLEDGE

    def test_a_seat_may_not_reclassify_its_own_resource(self, taxonomy):
        resource = next(iter(RESOURCE_DOMAINS))
        with pytest.raises(PermissionError):
            taxonomy.reclassify(
                resource,
                Domain.TREASURY,
                changed_by="ann-porter-external",
                reason="would be self-serving",
            )

    def test_every_reclassification_is_recorded(self, taxonomy):
        resource = next(iter(RESOURCE_DOMAINS))
        taxonomy.reclassify(resource, Domain.KNOWLEDGE, changed_by=TAXONOMY_OWNER, reason="first")
        history = taxonomy.history()
        assert len(history) == 1
        assert history[0].reason == "first"
        assert history[0].changed_by == TAXONOMY_OWNER

    def test_a_reclassification_needs_a_stated_reason(self, taxonomy):
        resource = next(iter(RESOURCE_DOMAINS))
        with pytest.raises(ValueError):
            taxonomy.reclassify(resource, Domain.KNOWLEDGE, changed_by=TAXONOMY_OWNER, reason="   ")


class TestTheCatalogueIsFullyClassified:
    def test_every_resource_has_a_domain(self):
        from src.exchange.sources import SELLABLE_RESOURCES

        for resource in SELLABLE_RESOURCES:
            assert domain_of(resource.resource_id) is not None, resource.resource_id


class TestTreasuryIsUnreachableByEarning:
    """Trading the platform's own capital is not a skill a seat can earn by
    being good at selling storage. It is isolated in the adjacency graph, so
    no amount of adjacent competence reaches it."""

    def test_treasury_is_marked_capital_at_risk(self):
        assert Domain.TREASURY in CAPITAL_AT_RISK

    def test_treasury_is_adjacent_to_nothing(self):
        assert adjacent_to(Domain.TREASURY) == ()

    def test_no_domain_is_adjacent_to_treasury(self):
        # Adjacency has to be isolating in both directions, or a seat expands
        # INTO treasury from a neighbour that lists it.
        for domain in Domain:
            assert Domain.TREASURY not in adjacent_to(domain), domain

    def test_the_capital_at_risk_skip_holds_even_if_adjacency_changes(self, expertise, monkeypatch):
        """The second defence, tested on its own.

        Treasury is unreachable two independent ways: it is isolated in the
        adjacency map, and review() refuses to grant anything in
        CAPITAL_AT_RISK. Calibration showed the first defence was masking the
        second — deleting the CAPITAL_AT_RISK check broke nothing, because no
        adjacency reached it anyway. This forces an edge into the map so the
        skip is the only thing left standing.
        """
        import src.exchange.expertise as expertise_module

        seat = "ann-porter-external"
        primary = PRIMARY_DOMAINS[seat]
        monkeypatch.setattr(
            expertise_module,
            "adjacent_to",
            lambda d: (Domain.TREASURY,) if d is primary else adjacent_to(d),
        )
        for _ in range(MIN_OUTCOMES_TO_EXPAND + 6):
            expertise.record_outcome(seat, primary, estimated=100.0, realised=100.0)

        assert expertise.review(seat) == []
        assert not expertise.horizon(seat).covers(Domain.TREASURY)

    def test_a_near_perfect_record_still_does_not_grant_treasury(self, expertise):
        seat = "george-porter-external"
        for _ in range(30):
            expertise.record_outcome(seat, Domain.TREASURY, estimated=100.0, realised=100.0)
        expertise.review(seat)
        assert not expertise.horizon(seat).covers(Domain.TREASURY)


class TestASeatStartsConfinedToItsPrimary:
    def test_each_seat_begins_with_only_its_primary_domain(self, expertise):
        for seat, primary in PRIMARY_DOMAINS.items():
            horizon = expertise.horizon(seat)
            assert horizon.covers(primary)
            assert horizon.expanded_into == ()

    def test_a_seat_does_not_cover_a_domain_it_has_not_earned(self, expertise):
        seat = "ann-porter-external"
        unearned = next(d for d in Domain if d is not PRIMARY_DOMAINS[seat])
        assert not expertise.horizon(seat).covers(unearned)


class TestHorizonsAreEarnedAndLost:
    """Expansion has to be evidenced, and contraction has to actually hold —
    a narrowing that the next review immediately reverses is not a control."""

    @staticmethod
    def _feed(reg, seat, domain, *, ratio: float, n: int):
        """Book n outcomes that realise `ratio` of what was estimated."""
        for _ in range(n):
            reg.record_outcome(seat, domain, estimated=100.0, realised=100.0 * ratio)

    def _earn(self, reg, seat):
        """Prove the seat's PRIMARY market, which is what grants an adjacent one.

        Expansion is driven by the record in a domain the seat already holds,
        not by a record in the domain it wants — a seat cannot bootstrap into
        a market by claiming outcomes there before it is allowed to trade it.
        """
        primary = PRIMARY_DOMAINS[seat]
        target = next(d for d in adjacent_to(primary) if d not in CAPITAL_AT_RISK)
        self._feed(reg, seat, primary, ratio=1.0, n=MIN_OUTCOMES_TO_EXPAND + 4)
        reg.review(seat)
        return target

    def test_too_few_outcomes_do_not_expand_a_horizon(self, expertise):
        seat = "ann-porter-external"
        primary = PRIMARY_DOMAINS[seat]
        target = next(d for d in adjacent_to(primary) if d not in CAPITAL_AT_RISK)
        self._feed(expertise, seat, primary, ratio=1.0, n=MIN_OUTCOMES_TO_EXPAND - 1)
        expertise.review(seat)
        assert not expertise.horizon(seat).covers(target)

    def test_a_sustained_record_expands_the_horizon(self, expertise):
        seat = "ann-porter-external"
        target = self._earn(expertise, seat)
        assert expertise.horizon(seat).covers(target)
        # The evidence lives in the primary — that is what vouched for the move.
        ratio, count = expertise.accuracy(seat, PRIMARY_DOMAINS[seat])
        assert count >= MIN_OUTCOMES_TO_EXPAND
        assert ratio >= EXPANSION_THRESHOLD

    def test_a_poor_record_contracts_the_horizon(self, expertise):
        seat = "ann-porter-external"
        target = self._earn(expertise, seat)
        self._feed(expertise, seat, target, ratio=0.2, n=30)
        expertise.review(seat)
        assert not expertise.horizon(seat).covers(target)

    def test_a_contraction_is_not_reversed_by_the_next_review(self, expertise):
        # The bug this test exists for: review() narrowed out of a domain and
        # then re-widened straight back into it in the same pass, because a
        # neighbouring domain's record still vouched for the seat. A control
        # that undoes itself one call later is not a control.
        seat = "ann-porter-external"
        target = self._earn(expertise, seat)
        self._feed(expertise, seat, target, ratio=0.2, n=30)
        expertise.review(seat)
        assert not expertise.horizon(seat).covers(target)

        assert expertise.review(seat) == []
        assert not expertise.horizon(seat).covers(target)

    def test_a_seat_can_earn_a_lost_domain_back_on_its_own_record(self, expertise):
        seat = "ann-porter-external"
        target = self._earn(expertise, seat)
        self._feed(expertise, seat, target, ratio=0.2, n=30)
        expertise.review(seat)
        assert not expertise.horizon(seat).covers(target)

        # Recovery must come from the seat's record in THAT domain, not from
        # a neighbour's.
        self._feed(expertise, seat, target, ratio=1.0, n=60)
        expertise.review(seat)
        assert expertise.horizon(seat).covers(target)

    def test_every_horizon_change_is_recorded_with_evidence(self, expertise):
        seat = "ann-porter-external"
        self._earn(expertise, seat)
        changes = expertise.changes(seat)
        assert changes
        assert all(c.evidence for c in changes)


class TestGainsSplitAndShortfallsFundNothing:
    def test_a_gain_splits_by_the_reinvestment_rate(self, treasury):
        settlement = treasury.settle(
            resource_id="storage-surplus",
            domain=Domain.CAPACITY,
            estimated=1000.0,
            realised=1000.0,
            allocation=Allocation.INFRASTRUCTURE,
        )
        assert not settlement.is_loss
        assert settlement.reinvested == pytest.approx(1000.0 * treasury.reinvestment_rate)
        assert settlement.retained == pytest.approx(1000.0 - settlement.reinvested)

    def test_a_shortfall_funds_nothing(self, treasury):
        # A negative realisation must not produce a negative "reinvestment"
        # that reads as funding on the position report.
        settlement = treasury.settle(
            resource_id="storage-surplus",
            domain=Domain.CAPACITY,
            estimated=1000.0,
            realised=400.0,
            allocation=Allocation.INFRASTRUCTURE,
        )
        assert settlement.is_loss
        assert settlement.reinvested == 0.0

    def test_a_shortfall_registers_an_open_loss(self, treasury):
        treasury.settle(
            resource_id="storage-surplus",
            domain=Domain.CAPACITY,
            estimated=1000.0,
            realised=400.0,
            allocation=Allocation.INFRASTRUCTURE,
        )
        losses = treasury.open_losses(Domain.CAPACITY)
        assert len(losses) == 1
        assert losses[0].is_open


class TestTheBarIsTheControlNotTheRegister:
    """A loss register that records without stopping anything is the same
    defect shape as a CI gate that runs without its checks."""

    def _lose(self, treasury):
        treasury.settle(
            resource_id="storage-surplus",
            domain=Domain.CAPACITY,
            estimated=1000.0,
            realised=400.0,
            allocation=Allocation.INFRASTRUCTURE,
        )

    def test_an_unreviewed_loss_bars_its_domain(self, treasury):
        assert not treasury.is_barred(Domain.CAPACITY)
        self._lose(treasury)
        assert treasury.is_barred(Domain.CAPACITY)

    def test_a_loss_bars_only_its_own_domain(self, treasury):
        self._lose(treasury)
        assert not treasury.is_barred(Domain.CREATIVE_ASSETS)

    def test_the_owners_measure_lifts_the_bar(self, treasury):
        self._lose(treasury)
        loss = treasury.open_losses(Domain.CAPACITY)[0]
        treasury.record_measure(
            loss.loss_id,
            measure="Cap spare-capacity commitments at 60% of headroom",
            recorded_by=TAXONOMY_OWNER,
        )
        assert not treasury.is_barred(Domain.CAPACITY)

    def test_a_seat_may_not_clear_its_own_loss(self, treasury):
        self._lose(treasury)
        loss = treasury.open_losses(Domain.CAPACITY)[0]
        with pytest.raises(PermissionError):
            treasury.record_measure(
                loss.loss_id,
                measure="nothing to see here",
                recorded_by="ann-porter-external",
            )
        assert treasury.is_barred(Domain.CAPACITY)

    def test_an_empty_measure_is_refused(self, treasury):
        self._lose(treasury)
        loss = treasury.open_losses(Domain.CAPACITY)[0]
        with pytest.raises(ValueError):
            treasury.record_measure(loss.loss_id, measure="   ", recorded_by=TAXONOMY_OWNER)
        assert treasury.is_barred(Domain.CAPACITY)


class TestThePositionReportsWhatHappened:
    def test_position_accounts_for_gains_losses_and_bars(self, treasury):
        treasury.settle(
            resource_id="storage-surplus",
            domain=Domain.CAPACITY,
            estimated=1000.0,
            realised=1000.0,
            allocation=Allocation.INFRASTRUCTURE,
        )
        treasury.settle(
            resource_id="generated-imagery",
            domain=Domain.CREATIVE_ASSETS,
            estimated=500.0,
            realised=200.0,
            allocation=Allocation.CAPABILITY,
        )
        position = treasury.position()
        assert position["settlements"] == 2
        assert position["realised_total"] == pytest.approx(1200.0)
        assert position["open_losses"] == 1
        assert Domain.CREATIVE_ASSETS.value in position["barred_domains"]
        assert Domain.CAPACITY.value not in position["barred_domains"]
