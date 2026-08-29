# tests/test_exchange.py
# Tests for src/exchange/ — the Arcadian Exchange's opportunity book:
# what the estate could sell, what it is worth, and what the gate refuses.

from __future__ import annotations

from dataclasses import replace

import pytest

from src.exchange.engine import Candidate, OpportunityEngine
from src.exchange.governance import (
    ESCALATION_VALUE_THRESHOLD,
    MIN_AGGREGATION_COHORT,
    Decision,
    rule,
)
from src.exchange.sources import (
    SELLABLE_RESOURCES,
    Constraint,
    by_seat,
    constrained_resources,
    get_resource,
    validate_catalogue,
)
from src.exchange.valuation import BASIS_CONFIDENCE, Basis, value


@pytest.fixture
def engine(tmp_path):
    eng = OpportunityEngine(tmp_path / "exchange_test.db")
    yield eng
    eng.close()


class TestCatalogue:
    def test_catalogue_is_internally_consistent(self):
        assert validate_catalogue() == []

    def test_every_external_seat_owns_something_to_sell(self):
        # A revenue seat with an empty portfolio is a title with no job. The
        # Chief Revenue Officer is the exception by design -- Clarence Porter
        # ranks what the other four raise rather than owning a resource.
        for seat in (
            "ann-porter-external",
            "george-porter-external",
            "edward-porter-external",
            "james-porter-external",
        ):
            assert by_seat(seat), seat
        assert by_seat("clarence-porter-external") == []

    def test_every_constrained_resource_explains_itself(self):
        for resource in SELLABLE_RESOURCES:
            if resource.constraint is not Constraint.NONE:
                assert resource.constraint_note, resource.resource_id

    def test_validator_catches_a_location_that_no_longer_exists(self):
        # Calibration: the validator must actually fail on rot, not just
        # return [] on the happy path.
        import src.exchange.sources as sources

        original = sources.SELLABLE_RESOURCES
        try:
            sources.SELLABLE_RESOURCES = original + (
                replace(original[0], resource_id="ghost", location="Atlantis"),
            )
            problems = validate_catalogue()
            assert any("Atlantis" in p for p in problems)
        finally:
            sources.SELLABLE_RESOURCES = original

    def test_validator_catches_an_unbookable_revenue_stream(self):
        import src.exchange.sources as sources

        original = sources.SELLABLE_RESOURCES
        try:
            sources.SELLABLE_RESOURCES = original + (
                replace(original[0], resource_id="ghost", revenue_stream="not_a_stream"),
            )
            problems = validate_catalogue()
            assert any("not_a_stream" in p for p in problems)
        finally:
            sources.SELLABLE_RESOURCES = original


class TestValuationRefusesToInventRevenue:
    """The constraint that matters most here: no made-up numbers."""

    def test_no_price_signal_yields_zero_and_says_so(self):
        v = value("three-d-assets", units=500)
        assert v.basis is Basis.NONE
        assert v.gross == 0.0
        assert v.confidence == 0.0
        assert v.priceable is False
        assert "no rate card" in v.rationale

    def test_a_price_with_no_basis_is_still_unpriced(self):
        # Supplying a number without saying where it came from must not turn
        # into a valuation -- that is exactly how a guess becomes a figure
        # somebody later quotes as measured.
        v = value("three-d-assets", units=10, unit_price=99.0, basis=Basis.NONE)
        assert v.priceable is False
        assert v.gross == 0.0

    def test_cost_to_serve_shows_as_a_loss_when_unpriced(self):
        v = value("three-d-assets", units=10, cost_to_serve=250.0)
        assert v.net == -250.0

    def test_every_valuation_carries_a_rationale(self):
        for v in (
            value("metered-api", units=10),
            value("metered-api", units=10, unit_price=2.0, basis=Basis.RATE_CARD),
        ):
            assert v.rationale.strip()

    def test_negative_inputs_are_rejected(self):
        with pytest.raises(ValueError):
            value("metered-api", units=-1, unit_price=2.0, basis=Basis.RATE_CARD)


class TestValuationConfidence:
    def test_stronger_basis_earns_more_confidence(self):
        confidences = [
            value("metered-api", units=1, unit_price=100.0, basis=b).confidence
            for b in (Basis.REALISED, Basis.RATE_CARD, Basis.COMPARABLE)
        ]
        assert confidences == sorted(confidences, reverse=True)

    def test_risk_adjustment_can_reorder_a_ranking(self):
        # The reason ranking sorts on risk_adjusted rather than net: a large
        # number on a weak basis should not beat a smaller measured one.
        weak = value("compliance-profiles", units=1, unit_price=1000.0, basis=Basis.COMPARABLE)
        strong = value("metered-api", units=1, unit_price=500.0, basis=Basis.REALISED)
        assert weak.net > strong.net
        assert strong.risk_adjusted > weak.risk_adjusted

    def test_realisation_ratio_scales_confidence_down(self):
        full = value("metered-api", units=1, unit_price=100.0, basis=Basis.RATE_CARD)
        half = value(
            "metered-api", units=1, unit_price=100.0, basis=Basis.RATE_CARD, realisation_ratio=0.5
        )
        assert half.confidence == pytest.approx(full.confidence * 0.5)

    def test_a_ratio_above_one_does_not_inflate_confidence(self):
        # A source under-promising is good news about that source, not a
        # reason to believe an estimate more than its basis warrants.
        v = value(
            "metered-api", units=1, unit_price=100.0, basis=Basis.RATE_CARD, realisation_ratio=3.0
        )
        assert v.confidence == pytest.approx(BASIS_CONFIDENCE[Basis.RATE_CARD])


class TestEligibilityGate:
    """The gate blocks; it does not annotate."""

    def test_unconstrained_and_small_is_clear(self):
        r = rule(get_resource("generated-imagery"), estimated_value=100.0)
        assert r.decision is Decision.CLEAR
        assert r.blocks is False

    def test_large_value_escalates_to_the_revenue_officer(self):
        r = rule(
            get_resource("generated-imagery"),
            estimated_value=ESCALATION_VALUE_THRESHOLD,
        )
        assert r.decision is Decision.ESCALATE
        assert r.sign_off == "clarence-porter-external"

    def test_licensed_material_is_refused_unless_proven_own_work(self):
        assert (
            rule(get_resource("knowledge-products"), estimated_value=10.0).decision
            is Decision.REFUSED
        )

    def test_licensed_material_still_escalates_when_claimed_as_own_work(self):
        r = rule(
            get_resource("knowledge-products"),
            estimated_value=10.0,
            content_is_own_work=True,
        )
        assert r.decision is Decision.ESCALATE
        assert r.sign_off == "edward-porter-external"

    def test_personal_data_without_a_stated_cohort_is_refused(self):
        # Silence is not evidence that the aggregate is non-identifying.
        assert (
            rule(get_resource("usage-aggregates"), estimated_value=10.0).decision
            is Decision.REFUSED
        )

    def test_cohort_below_the_floor_is_refused(self):
        r = rule(
            get_resource("usage-aggregates"),
            estimated_value=10.0,
            aggregation_cohort=MIN_AGGREGATION_COHORT - 1,
        )
        assert r.decision is Decision.REFUSED

    def test_cohort_at_the_floor_escalates_to_a_person(self):
        r = rule(
            get_resource("usage-aggregates"),
            estimated_value=10.0,
            aggregation_cohort=MIN_AGGREGATION_COHORT,
        )
        assert r.decision is Decision.ESCALATE
        assert r.sign_off == "human"

    def test_regulated_always_escalates_to_a_person(self):
        # However small the number. Executing a trade is not a size question.
        for amount in (1.0, ESCALATION_VALUE_THRESHOLD * 100):
            r = rule(get_resource("treasury-position"), estimated_value=amount)
            assert r.decision is Decision.ESCALATE
            assert r.sign_off == "human"

    def test_client_derived_needs_the_client_to_have_said_yes(self):
        resource = get_resource("consolidation-engagement")
        assert rule(resource, estimated_value=10.0).decision is Decision.REFUSED
        assert (
            rule(resource, estimated_value=10.0, counterparty_authorisation=True).decision
            is Decision.CLEAR
        )

    def test_every_ruling_gives_a_reason(self):
        for resource in SELLABLE_RESOURCES:
            assert rule(resource, estimated_value=10.0).reason.strip(), resource.resource_id


class TestOpportunityBook:
    def test_refused_opportunities_never_reach_the_ranking(self):
        book = OpportunityEngineBookHelper.build(
            [
                Candidate("generated-imagery", units=10, unit_price=5.0, basis=Basis.RATE_CARD),
                Candidate("knowledge-products", units=10, unit_price=50.0, basis=Basis.RATE_CARD),
                Candidate("usage-aggregates", units=1, unit_price=900.0, basis=Basis.COMPARABLE),
            ]
        )
        ranked_ids = {o["resource_id"] for o in book["ranked"]}
        refused_ids = {o["resource_id"] for o in book["refused"]}
        assert refused_ids == {"knowledge-products", "usage-aggregates"}
        assert ranked_ids.isdisjoint(refused_ids)

    def test_escalated_opportunities_are_not_counted_as_pursuable(self):
        book = OpportunityEngineBookHelper.build(
            [Candidate("treasury-position", units=1, unit_price=800.0, basis=Basis.REALISED)]
        )
        assert book["ranked"] == []
        assert book["pursuable_value"] == 0.0
        assert len(book["escalated"]) == 1

    def test_unpriced_candidates_are_reported_separately(self):
        book = OpportunityEngineBookHelper.build([Candidate("three-d-assets", units=50)])
        assert [o["resource_id"] for o in book["unpriced"]] == ["three-d-assets"]
        assert book["ranked"] == []

    def test_ranking_is_by_risk_adjusted_value(self):
        book = OpportunityEngineBookHelper.build(
            [
                Candidate("compliance-profiles", units=1, unit_price=900.0, basis=Basis.COMPARABLE),
                Candidate("metered-api", units=1, unit_price=600.0, basis=Basis.REALISED),
            ]
        )
        # Weaker basis, larger number -- must rank second.
        assert [o["resource_id"] for o in book["ranked"]] == [
            "metered-api",
            "compliance-profiles",
        ]

    def test_an_unknown_resource_is_an_error_not_a_silent_skip(self, engine):
        with pytest.raises(ValueError, match="not a resource in the catalogue"):
            engine.evaluate(Candidate("nothing-we-have", units=1))


class TestAdaptation:
    def test_no_history_neither_penalises_nor_flatters(self, engine):
        assert engine.realisation_ratio("metered-api") == 1.0

    def test_a_source_that_over_promises_loses_confidence(self, engine):
        before = engine.evaluate(
            Candidate("metered-api", units=100, unit_price=2.0, basis=Basis.REALISED)
        )
        for _ in range(3):
            engine.record_outcome("metered-api", estimated=1000.0, realised=400.0)
        after = engine.evaluate(
            Candidate("metered-api", units=100, unit_price=2.0, basis=Basis.REALISED)
        )
        assert engine.realisation_ratio("metered-api") == pytest.approx(0.4)
        assert after.valuation.confidence < before.valuation.confidence
        # The estimate itself is unchanged -- only belief in it moved.
        assert after.valuation.net == before.valuation.net

    def test_adaptation_is_scoped_to_the_source_that_earned_it(self, engine):
        engine.record_outcome("metered-api", estimated=1000.0, realised=100.0)
        assert engine.realisation_ratio("metered-api") == pytest.approx(0.1)
        assert engine.realisation_ratio("generated-imagery") == 1.0

    def test_outcomes_reject_an_unknown_resource(self, engine):
        with pytest.raises(ValueError):
            engine.record_outcome("nothing-we-have", estimated=1.0, realised=1.0)

    def test_outcomes_reject_negative_amounts(self, engine):
        with pytest.raises(ValueError):
            engine.record_outcome("metered-api", estimated=-1.0, realised=1.0)

    def test_recording_an_outcome_does_not_book_income(self, engine):
        # There is one ledger, and it is PassiveRevenueEngine's. This engine
        # only calibrates; duplicating the ledger would give "what did we earn"
        # two answers.
        from src.monetisation.billing import PassiveRevenueEngine

        tracker = PassiveRevenueEngine()
        before = dict(tracker.streams)
        engine.record_outcome("metered-api", estimated=100.0, realised=100.0)
        assert dict(tracker.streams) == before


class TestPersistence:
    def test_a_book_snapshot_survives_a_reopen(self, tmp_path):
        path = tmp_path / "snap.db"
        eng = OpportunityEngine(path)
        book = eng.build_book(
            [Candidate("metered-api", units=10, unit_price=3.0, basis=Basis.REALISED)]
        )
        snapshot_id = eng.snapshot_book(book)
        eng.record_outcome("metered-api", estimated=30.0, realised=15.0)
        eng.close()

        reopened = OpportunityEngine(path)
        try:
            assert snapshot_id > 0
            assert reopened.realisation_ratio("metered-api") == pytest.approx(0.5)
        finally:
            reopened.close()

    def test_inventory_lists_every_resource_with_its_current_ratio(self, engine):
        inv = engine.inventory()
        assert inv["total"] == len(SELLABLE_RESOURCES)
        assert all("realisation_ratio" in r for r in inv["resources"])

    def test_constrained_grouping_covers_every_constrained_resource(self):
        grouped = constrained_resources()
        flat = {r.resource_id for rs in grouped.values() for r in rs}
        expected = {
            r.resource_id for r in SELLABLE_RESOURCES if r.constraint is not Constraint.NONE
        }
        assert flat == expected


class OpportunityEngineBookHelper:
    """Builds a book against a throwaway on-disk engine.

    A helper rather than a fixture because several book tests want a fresh,
    history-free engine and none of them need to hold onto it afterwards.
    """

    @staticmethod
    def build(candidates):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            eng = OpportunityEngine(Path(tmp) / "book.db")
            try:
                return eng.build_book(candidates)
            finally:
                eng.close()


class TestRoutes:
    """The engine is wired, not merely written.

    An estate that has repeatedly produced controls which run and never hold
    should not accept "the module exists" as evidence that anything is
    reachable. These go through the mounted app.
    """

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from api import app

        return TestClient(app)

    @pytest.fixture
    def admin_client(self):
        from fastapi.testclient import TestClient

        from api import app
        from auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: {
            "username": "test-admin",
            "role": "admin",
        }
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    @pytest.fixture
    def user_client(self):
        from fastapi.testclient import TestClient

        from api import app
        from auth import get_current_user

        app.dependency_overrides[get_current_user] = lambda: {
            "username": "test-user",
            "role": "user",
        }
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_the_router_is_mounted(self):
        from api import app

        paths = {r.path for r in app.routes if getattr(r, "path", "").startswith("/exchange")}
        assert "/exchange/inventory" in paths
        assert "/exchange/book" in paths

    def test_inventory_is_readable_without_a_token(self, client):
        response = client.get("/exchange/inventory")
        assert response.status_code == 200
        assert response.json()["total"] == len(SELLABLE_RESOURCES)

    def test_constraints_are_readable_without_a_token(self, client):
        response = client.get("/exchange/constraints")
        assert response.status_code == 200
        assert set(response.json()) <= {c.value for c in Constraint}

    def test_an_unknown_seat_is_a_404(self, client):
        assert client.get("/exchange/seats/nobody-external").status_code == 404

    def test_building_a_book_needs_a_token(self, client):
        response = client.post(
            "/exchange/book",
            json=[
                {"resource_id": "metered-api", "units": 10, "unit_price": 2.0, "basis": "realised"}
            ],
        )
        assert response.status_code == 401

    def test_building_a_book_needs_admin_not_merely_a_login(self, user_client):
        response = user_client.post(
            "/exchange/book",
            json=[
                {"resource_id": "metered-api", "units": 10, "unit_price": 2.0, "basis": "realised"}
            ],
        )
        assert response.status_code == 403

    def test_an_admin_gets_a_ranked_book(self, admin_client):
        response = admin_client.post(
            "/exchange/book",
            json=[
                {
                    "resource_id": "metered-api",
                    "units": 100,
                    "unit_price": 2.0,
                    "basis": "realised",
                },
                {
                    "resource_id": "knowledge-products",
                    "units": 5,
                    "unit_price": 100.0,
                    "basis": "rate_card",
                },
            ],
        )
        assert response.status_code == 200
        book = response.json()
        assert [o["resource_id"] for o in book["ranked"]] == ["metered-api"]
        assert [o["resource_id"] for o in book["refused"]] == ["knowledge-products"]
        assert book["snapshot_id"] > 0

    def test_an_empty_proposal_is_a_400(self, admin_client):
        assert admin_client.post("/exchange/book", json=[]).status_code == 400

    def test_negative_units_are_rejected_by_the_schema(self, admin_client):
        response = admin_client.post(
            "/exchange/book",
            json=[
                {"resource_id": "metered-api", "units": -5, "unit_price": 2.0, "basis": "realised"}
            ],
        )
        assert response.status_code == 422
