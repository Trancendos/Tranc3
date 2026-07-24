# tests/test_relations.py
# Tests for src/relations/registry.py — the AI-to-AI Relationship Matrix,
# Activity Feed, and Location Brochure.

from __future__ import annotations

import pytest

from src.entities.platform import PLATFORM_ENTITIES
from src.relations.registry import (
    SCORE_MAX,
    SCORE_MIN,
    RelationsRegistry,
    permission_tier,
)


@pytest.fixture
def registry(tmp_path):
    db_path = tmp_path / "relations_registry_test.db"
    reg = RelationsRegistry(db_path=db_path)
    yield reg
    reg.close()


class TestPermissionTier:
    def test_trusted_at_60(self):
        assert permission_tier(60.0) == "trusted"
        assert permission_tier(100.0) == "trusted"

    def test_friendly_between_20_and_60(self):
        assert permission_tier(20.0) == "friendly"
        assert permission_tier(59.9) == "friendly"

    def test_neutral_between_negative_20_and_20(self):
        assert permission_tier(0.0) == "neutral"
        assert permission_tier(-19.9) == "neutral"

    def test_restricted_between_negative_60_and_negative_20(self):
        # Tiers use inclusive lower bounds, so -20.0 itself belongs to
        # "neutral" (its own tier's threshold) — restricted is (-60, -20).
        assert permission_tier(-20.1) == "restricted"
        assert permission_tier(-59.9) == "restricted"

    def test_blocked_below_negative_60(self):
        # -60.0 itself belongs to "restricted" (inclusive lower bound);
        # only scores strictly below -60 are "blocked".
        assert permission_tier(-60.1) == "blocked"
        assert permission_tier(-100.0) == "blocked"

    def test_tier_boundaries_are_inclusive_on_their_own_threshold(self):
        assert permission_tier(-20.0) == "neutral"
        assert permission_tier(-60.0) == "restricted"


class TestBaselineSeeding:
    def test_same_pillar_pair_has_positive_baseline(self, registry):
        # Royal Bank of Arcadia and Arcadian Exchange are both
        # Commercial / Financial.
        rel = registry.get_relationship("Dorris Fontaine", "Clarence Porter")
        assert rel.baseline == 25.0
        assert rel.score == 25.0
        assert rel.interactions_count == 0

    def test_same_pillar_pair_resolves_via_non_primary_co_lead(self, registry):
        # Ann Porter is Arcadian Exchange's Lead AI too (co-lead, not
        # primary) — she must resolve to the same Location/pillar as
        # Clarence Porter, not silently fall back to a neutral baseline.
        rel = registry.get_relationship("Dorris Fontaine", "Ann Porter")
        assert rel.baseline == 25.0

    def test_different_pillar_pair_has_neutral_baseline(self, registry):
        # Dorris Fontaine (Commercial/Financial) vs. Larry Lowhammer (DevOps).
        rel = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        assert rel.baseline == 0.0
        assert rel.score == 0.0

    def test_unknown_identity_falls_back_to_neutral_baseline(self, registry):
        rel = registry.get_relationship("Dorris Fontaine", "Some Unknown Bot")
        assert rel.baseline == 0.0


class TestRecordEventAndNudges:
    def test_positive_interaction_raises_score(self, registry):
        before = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        registry.record_event(
            actor_ai="Dorris Fontaine",
            event_type="ai_interaction",
            target_ai="Larry Lowhammer",
            sentiment="positive",
            summary="Collaborated on a deploy budget review.",
        )
        after = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        assert after.score > before.score
        assert after.interactions_count == 1

    def test_negative_interaction_lowers_score(self, registry):
        before = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        registry.record_event(
            actor_ai="Dorris Fontaine",
            event_type="ai_interaction",
            target_ai="Larry Lowhammer",
            sentiment="negative",
            summary="Disagreement over pipeline spend.",
        )
        after = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        assert after.score < before.score

    def test_neutral_interaction_does_not_nudge_score(self, registry):
        before = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        registry.record_event(
            actor_ai="Dorris Fontaine",
            event_type="ai_interaction",
            target_ai="Larry Lowhammer",
            sentiment="neutral",
            summary="Routine status check-in.",
        )
        after = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        assert after.score == before.score
        # a neutral interaction is still recorded in the feed even though it
        # doesn't nudge the relationship score
        assert len(registry.get_feed(ai="Dorris Fontaine")) == 1

    def test_location_tag_event_does_not_require_target_ai(self, registry):
        event = registry.record_event(
            actor_ai="Dorris Fontaine",
            event_type="location_tag",
            location="Royal Bank of Arcadia",
            sentiment="neutral",
            summary="Checked into Royal Bank of Arcadia.",
        )
        assert event.target_ai is None
        assert event.location == "Royal Bank of Arcadia"

    def test_action_event_does_not_affect_relationship_matrix(self, registry):
        registry.record_event(
            actor_ai="Renik",
            event_type="action",
            location="Royal Bank of Arcadia",
            sentiment="negative",
            summary="Flagged and blocked a suspicious transaction.",
        )
        # actions are location-scoped, not AI-to-AI — no relationship row
        # should have been created by this alone.
        rel = registry.get_relationship("Renik", "Dorris Fontaine")
        assert rel.interactions_count == 0

    def test_invalid_sentiment_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.record_event(
                actor_ai="Dorris Fontaine",
                event_type="ai_interaction",
                sentiment="furious",
                summary="invalid",
            )

    def test_score_clamped_at_max(self, registry):
        for _ in range(50):
            registry.record_event(
                actor_ai="Dorris Fontaine",
                event_type="ai_interaction",
                target_ai="Larry Lowhammer",
                sentiment="positive",
                summary="Another good interaction.",
            )
        rel = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        assert rel.score <= SCORE_MAX

    def test_score_clamped_at_min(self, registry):
        for _ in range(50):
            registry.record_event(
                actor_ai="Dorris Fontaine",
                event_type="ai_interaction",
                target_ai="Larry Lowhammer",
                sentiment="negative",
                summary="Another bad interaction.",
            )
        rel = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        assert rel.score >= SCORE_MIN

    def test_redemption_after_being_pushed_negative(self, registry):
        """Even a fully negative score can recover — no permanent lock."""
        for _ in range(50):
            registry.record_event(
                actor_ai="Dorris Fontaine",
                event_type="ai_interaction",
                target_ai="Larry Lowhammer",
                sentiment="negative",
                summary="Bad interaction.",
            )
        blocked = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        assert blocked.tier == "blocked"

        for _ in range(10):
            registry.record_event(
                actor_ai="Dorris Fontaine",
                event_type="ai_interaction",
                target_ai="Larry Lowhammer",
                sentiment="positive",
                summary="Making amends.",
            )
        recovering = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        assert recovering.score > blocked.score


class TestRelationshipOrderIndependence:
    def test_score_is_the_same_regardless_of_argument_order(self, registry):
        registry.record_event(
            actor_ai="Dorris Fontaine",
            event_type="ai_interaction",
            target_ai="Larry Lowhammer",
            sentiment="positive",
            summary="Interaction.",
        )
        a_b = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        b_a = registry.get_relationship("Larry Lowhammer", "Dorris Fontaine")
        # Not exactly equal: each call independently applies time-based decay
        # against `time.time()`, so a few nanoseconds between the two calls
        # produce a sub-float-precision difference in the decayed score.
        assert a_b.score == pytest.approx(b_a.score)
        assert a_b.tier == b_a.tier


class TestListRelationships:
    def test_returns_one_entry_per_other_lead_ai(self, registry):
        # Includes every recognized name, not just each Location's primary
        # lead_ai — co-leads (Sam King, The Orb of Orisis, the four
        # non-primary Porters, ...) are recognized Lead AIs too.
        others = set()
        for e in PLATFORM_ENTITIES.values():
            others.add(e.lead_ai)
            others.update(e.lead_ais)
        others.discard("Dorris Fontaine")
        rels = registry.list_relationships("Dorris Fontaine")
        assert {r.ai_b if r.ai_a == "Dorris Fontaine" else r.ai_a for r in rels} == others

    def test_sorted_descending_by_score(self, registry):
        rels = registry.list_relationships("Dorris Fontaine")
        scores = [r.score for r in rels]
        assert scores == sorted(scores, reverse=True)


class TestActivityFeed:
    def test_negative_limit_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.get_feed(limit=-1)

    def test_zero_limit_rejected(self, registry):
        with pytest.raises(ValueError):
            registry.get_feed(limit=0)

    def test_non_serializable_details_raises_before_any_mutation(self, registry):
        before = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        with pytest.raises(TypeError):
            registry.record_event(
                actor_ai="Dorris Fontaine",
                event_type="ai_interaction",
                target_ai="Larry Lowhammer",
                sentiment="positive",
                summary="bad details",
                details={"not_serializable": {1, 2, 3}},
            )
        # Neither the relationship nudge nor the activity row should have
        # been applied — the failure must happen before either mutation.
        after = registry.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        assert after.score == before.score
        assert after.interactions_count == before.interactions_count
        assert len(registry.get_feed()) == 0

    def test_feed_filters_by_ai(self, registry):
        registry.record_event(actor_ai="Dorris Fontaine", event_type="system", summary="a")
        registry.record_event(actor_ai="Larry Lowhammer", event_type="system", summary="b")
        feed = registry.get_feed(ai="Dorris Fontaine")
        assert len(feed) == 1
        assert feed[0].actor_ai == "Dorris Fontaine"

    def test_feed_filters_by_location(self, registry):
        registry.record_event(
            actor_ai="Dorris Fontaine",
            event_type="location_tag",
            location="Royal Bank of Arcadia",
            summary="a",
        )
        registry.record_event(
            actor_ai="Larry Lowhammer",
            event_type="location_tag",
            location="The Workshop",
            summary="b",
        )
        feed = registry.get_feed(location="Royal Bank of Arcadia")
        assert len(feed) == 1
        assert feed[0].location == "Royal Bank of Arcadia"

    def test_feed_newest_first(self, registry):
        registry.record_event(actor_ai="Dorris Fontaine", event_type="system", summary="first")
        registry.record_event(actor_ai="Dorris Fontaine", event_type="system", summary="second")
        feed = registry.get_feed(ai="Dorris Fontaine")
        assert feed[0].summary == "second"
        assert feed[1].summary == "first"

    def test_feed_respects_limit(self, registry):
        for i in range(5):
            registry.record_event(actor_ai="Dorris Fontaine", event_type="system", summary=str(i))
        feed = registry.get_feed(ai="Dorris Fontaine", limit=2)
        assert len(feed) == 2

    def test_target_ai_also_matches_ai_filter(self, registry):
        registry.record_event(
            actor_ai="Dorris Fontaine",
            event_type="ai_interaction",
            target_ai="Larry Lowhammer",
            sentiment="neutral",
            summary="chat",
        )
        feed = registry.get_feed(ai="Larry Lowhammer")
        assert len(feed) == 1


class TestLocationBrochure:
    def test_unknown_location_raises(self, registry):
        with pytest.raises(KeyError):
            registry.get_location_brochure("Nonexistent Place")

    def test_brochure_reflects_recorded_events(self, registry):
        registry.record_event(
            actor_ai="Dorris Fontaine",
            event_type="location_tag",
            location="Royal Bank of Arcadia",
            sentiment="positive",
            summary="Visited.",
        )
        registry.record_event(
            actor_ai="Renik",
            event_type="action",
            location="Royal Bank of Arcadia",
            sentiment="negative",
            summary="Blocked a suspicious transaction.",
        )
        brochure = registry.get_location_brochure("Royal Bank of Arcadia")
        assert brochure.location == "Royal Bank of Arcadia"
        assert brochure.current_resident == "Dorris Fontaine"
        assert brochure.total_events == 2
        assert brochure.unique_visitors == 2
        assert brochure.sentiment_counts["positive"] == 1
        assert brochure.sentiment_counts["negative"] == 1
        assert brochure.job_description == "Chief Financial Officer"
        assert "Royal Bank of Arcadia" in brochure.flavor_text

    def test_brochure_with_no_events_still_returns(self, registry):
        brochure = registry.get_location_brochure("The Workshop")
        assert brochure.total_events == 0
        assert brochure.unique_visitors == 0
        assert brochure.sentiment_counts == {"positive": 0, "neutral": 0, "negative": 0}


class TestInsights:
    def test_busiest_location_insight(self, registry):
        for i in range(3):
            registry.record_event(
                actor_ai="Dorris Fontaine",
                event_type="location_tag",
                location="Royal Bank of Arcadia",
                summary=f"visit {i}",
            )
        insights = registry.get_insights()
        kinds = [i.kind for i in insights]
        assert "busiest_location" in kinds

    def test_negative_activity_spike_insight(self, registry):
        for i in range(3):
            registry.record_event(
                actor_ai="Renik",
                event_type="action",
                location="Cryptex",
                sentiment="negative",
                summary=f"incident {i}",
            )
        insights = registry.get_insights()
        kinds = [i.kind for i in insights]
        assert "negative_activity_spike" in kinds

    def test_most_improved_relationship_insight(self, registry):
        registry.record_event(
            actor_ai="Dorris Fontaine",
            event_type="ai_interaction",
            target_ai="Larry Lowhammer",
            sentiment="positive",
            summary="Good chat.",
        )
        insights = registry.get_insights()
        kinds = [i.kind for i in insights]
        assert "most_improved_relationship" in kinds

    def test_insights_respect_limit(self, registry):
        for i in range(3):
            registry.record_event(
                actor_ai="Renik",
                event_type="action",
                location="Cryptex",
                sentiment="negative",
                summary=f"incident {i}",
            )
        insights = registry.get_insights(limit=1)
        assert len(insights) == 1

    def test_ai_at_risk_insight(self, registry):
        """An AI that has soured into the restricted/blocked tier with >= 3
        other Lead AIs should surface an `ai_at_risk` insight. Exercises the
        batch relationship scan added to get_insights."""
        # All three targets are distinct Lead AIs on Pillars different from
        # Royal Bank of Arcadia's, so each pair starts at baseline 0. Ten
        # negative interactions per pair drop the score well below the -20
        # restricted threshold even at the lowest negativity multiplier.
        targets = ["Larry Lowhammer", "Renik", "Zimik"]
        for target in targets:
            for i in range(10):
                registry.record_event(
                    actor_ai="Dorris Fontaine",
                    event_type="ai_interaction",
                    target_ai=target,
                    sentiment="negative",
                    summary=f"friction with {target} {i}",
                )
            # Confirm the setup actually pushed the pair into restricted/blocked
            # (independent of the exact per-quirk multiplier).
            rel = registry.get_relationship("Dorris Fontaine", target)
            assert rel.tier in ("restricted", "blocked")

        insights = registry.get_insights(limit=50)
        at_risk = [i for i in insights if i.kind == "ai_at_risk"]
        assert at_risk, "expected an ai_at_risk insight"
        flagged_ais = {i.data["ai"] for i in at_risk}
        assert "Dorris Fontaine" in flagged_ais
        dorris = next(i for i in at_risk if i.data["ai"] == "Dorris Fontaine")
        assert dorris.data["restricted_or_blocked_count"] >= 3


class TestReconnectPersistence:
    def test_relationship_survives_reconnect(self, tmp_path):
        db_path = tmp_path / "reopen_relations.db"
        reg1 = RelationsRegistry(db_path=db_path)
        reg1.record_event(
            actor_ai="Dorris Fontaine",
            event_type="ai_interaction",
            target_ai="Larry Lowhammer",
            sentiment="positive",
            summary="chat",
        )
        reg1.close()

        reg2 = RelationsRegistry(db_path=db_path)
        rel = reg2.get_relationship("Dorris Fontaine", "Larry Lowhammer")
        assert rel.interactions_count == 1
        assert len(reg2.get_feed()) == 1
        reg2.close()
