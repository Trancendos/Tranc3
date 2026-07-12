"""Tests for webhook-driven subscription provisioning (src/monetisation/billing.py).

These cover the revenue loop that was previously missing: a verified Stripe event
must actually grant/downgrade the customer's tier. All tests run without Stripe,
a database, or network — provisioning is a pure function plus an injected user
manager.
"""

from __future__ import annotations

from src.auth.db_user_manager import DBUserManager
from src.monetisation import billing
from src.monetisation.billing import (
    TIERS,
    apply_provision,
    enforcer,
    plan_from_event,
    provision_from_event,
    tier_for_price_id,
)


class FakeUserManager:
    """Records tier updates by id / username without touching a DB."""

    def __init__(self):
        self.by_id: dict[str, str] = {}
        self.by_name: dict[str, str] = {}

    def update_tier_by_id(self, user_id: str, tier: str) -> bool:
        # emulate "unknown user" for a sentinel id so the username fallback is exercised
        if user_id == "no-such-id":
            return False
        self.by_id[user_id] = tier
        return True

    def update_tier(self, username: str, tier: str) -> bool:
        self.by_name[username] = tier
        return True


def _checkout_event(user_id="u-123", tier="pro"):
    return {
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_1", "metadata": {"user_id": user_id, "tier": tier}}},
    }


# ---------------------------------------------------------------------------
# plan_from_event (pure parsing)
# ---------------------------------------------------------------------------


def test_checkout_completed_yields_grant_plan():
    plan = plan_from_event(_checkout_event(tier="business"))
    assert plan == {
        "action": "grant",
        "user_id": "u-123",
        "tier": "business",
        "event": "checkout.session.completed",
    }


def test_checkout_free_or_unknown_tier_is_ignored():
    assert plan_from_event(_checkout_event(tier="free")) is None
    assert plan_from_event(_checkout_event(tier="bogus")) is None


def test_checkout_without_user_id_is_ignored():
    evt = {"type": "checkout.session.completed", "data": {"object": {"metadata": {"tier": "pro"}}}}
    assert plan_from_event(evt) is None


def test_subscription_deleted_yields_downgrade():
    evt = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"user_id": "u-9", "tier": "pro"}}},
    }
    plan = plan_from_event(evt)
    assert plan["action"] == "downgrade"
    assert plan["tier"] == "free"
    assert plan["user_id"] == "u-9"


def test_subscription_updated_inactive_status_downgrades():
    evt = {
        "type": "customer.subscription.updated",
        "data": {"object": {"status": "canceled", "metadata": {"user_id": "u-9"}}},
    }
    plan = plan_from_event(evt)
    assert plan["action"] == "downgrade" and plan["tier"] == "free"


def test_subscription_updated_active_maps_price_to_tier(monkeypatch):
    # Give 'pro' a concrete price id and assert the event maps to it.
    monkeypatch.setitem(TIERS["pro"], "stripe_price_id", "price_PRO_123")
    evt = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "status": "active",
                "metadata": {"user_id": "u-9"},
                "items": {"data": [{"price": {"id": "price_PRO_123"}}]},
            }
        },
    }
    plan = plan_from_event(evt)
    assert plan["action"] == "grant" and plan["tier"] == "pro"


def test_unrelated_event_is_ignored():
    assert plan_from_event({"type": "invoice.paid", "data": {"object": {}}}) is None


def test_tier_for_price_id(monkeypatch):
    monkeypatch.setitem(TIERS["business"], "stripe_price_id", "price_BIZ_1")
    assert tier_for_price_id("price_BIZ_1") == "business"
    assert tier_for_price_id("price_unknown") is None
    assert tier_for_price_id(None) is None


# ---------------------------------------------------------------------------
# apply_provision / provision_from_event (side effects, injected manager)
# ---------------------------------------------------------------------------


def test_apply_provision_persists_by_id_and_books_revenue():
    fum = FakeUserManager()
    before = billing.revenue_tracker.summary().get("total_gbp", 0.0)
    result = provision_from_event(fum, _checkout_event(user_id="u-77", tier="pro"))
    assert result["handled"] is True
    assert result["action"] == "grant"
    assert result["tier"] == "pro"
    assert result["user_persisted"] is True
    assert fum.by_id["u-77"] == "pro"
    # recurring revenue booked for the pro price
    after = billing.revenue_tracker.summary().get("total_gbp", 0.0)
    assert after >= before + TIERS["pro"]["price_gbp"]


def test_apply_provision_falls_back_to_username_when_id_unknown():
    fum = FakeUserManager()
    plan = {"action": "grant", "user_id": "no-such-id", "tier": "pro", "event": "x"}
    result = apply_provision(fum, plan)
    assert result["user_persisted"] is True
    assert fum.by_name["no-such-id"] == "pro"  # username fallback used


def test_apply_provision_downgrade_does_not_book_revenue():
    fum = FakeUserManager()
    before = billing.revenue_tracker.summary().get("total_gbp", 0.0)
    plan = {"action": "downgrade", "user_id": "u-1", "tier": "free", "event": "x"}
    result = apply_provision(fum, plan)
    assert result["action"] == "downgrade"
    assert fum.by_id["u-1"] == "free"
    after = billing.revenue_tracker.summary().get("total_gbp", 0.0)
    assert after == before  # no revenue on downgrade


def test_apply_provision_no_plan_is_noop():
    assert apply_provision(FakeUserManager(), None) == {"handled": False}


def test_apply_provision_survives_none_manager():
    # Router degrades to a None manager if api isn't importable; must not raise.
    result = apply_provision(None, {"action": "grant", "user_id": "u", "tier": "pro", "event": "x"})
    assert result["handled"] is True
    assert result["user_persisted"] is False


def test_enforcer_cache_reflects_new_tier_for_tracked_user():
    # A user already being rate-limited should see the new tier immediately.
    enforcer.check_and_increment("u-live", tier="free")
    apply_provision(
        FakeUserManager(),
        {"action": "grant", "user_id": "u-live", "tier": "business", "event": "x"},
    )
    assert enforcer.get_usage("u-live")["tier"] == "business"


# ---------------------------------------------------------------------------
# DBUserManager.update_tier_by_id (fallback store)
# ---------------------------------------------------------------------------


def test_update_tier_by_id_on_fallback_store():
    mgr = DBUserManager(None)  # fallback (no DB)
    created = mgr.create_user("alice", "Str0ng-Pass!23")
    uid = created["user_id"]

    assert mgr.update_tier_by_id(uid, "business") is True
    assert mgr.get_user("alice")["tier"] == "business"
    # unknown id → no update
    assert mgr.update_tier_by_id("does-not-exist", "pro") is False


def test_end_to_end_checkout_grants_via_real_fallback_manager():
    mgr = DBUserManager(None)
    created = mgr.create_user("bob", "Str0ng-Pass!23")
    uid = created["user_id"]
    assert mgr.get_user("bob")["tier"] == "free"

    result = provision_from_event(mgr, _checkout_event(user_id=uid, tier="pro"))
    assert result["user_persisted"] is True
    assert mgr.get_user("bob")["tier"] == "pro"


# revenue_tracker.summary() shape guard used above
def test_revenue_summary_has_total_monthly():
    assert "total_gbp" in billing.revenue_tracker.summary()
