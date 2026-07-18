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
    plan_from_event,
    provision_from_event,
    tier_for_price_id,
)


class FakeUserManager:
    """Records tier updates by id / username without touching a DB."""

    def __init__(self):
        self.by_id: dict[str, str] = {}
        self.by_name: dict[str, str] = {}
        self.customer_by_id: dict[str, str] = {}

    def update_tier_by_id(self, user_id: str, tier: str) -> bool:
        # emulate "unknown user" for a sentinel id so the username fallback is exercised
        if user_id == "no-such-id":
            return False
        self.by_id[user_id] = tier
        return True

    def update_tier(self, username: str, tier: str) -> bool:
        self.by_name[username] = tier
        return True

    def set_stripe_customer_id(self, user_id: str, customer_id: str) -> bool:
        if not customer_id:
            return False
        self.customer_by_id[user_id] = customer_id
        return True


def _checkout_event(
    user_id="u-123", tier="pro", event_id="evt_1", payment_status="paid", customer="cus_ABC"
):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_1",
                "customer": customer,
                "payment_status": payment_status,
                "metadata": {"user_id": user_id, "tier": tier},
            }
        },
    }


# ---------------------------------------------------------------------------
# plan_from_event (pure parsing)
# ---------------------------------------------------------------------------


def test_checkout_completed_yields_grant_plan():
    plan = plan_from_event(_checkout_event(tier="business", event_id="evt_9"))
    assert plan["action"] == "grant"
    assert plan["user_id"] == "u-123"
    assert plan["tier"] == "business"
    assert plan["event"] == "checkout.session.completed"
    assert plan["event_id"] == "evt_9"
    assert plan["is_payment"] is True


def test_checkout_free_or_unknown_tier_is_ignored():
    assert plan_from_event(_checkout_event(tier="free")) is None
    assert plan_from_event(_checkout_event(tier="bogus")) is None


def test_checkout_unpaid_is_not_granted():
    # An async payment method can complete the session while still unpaid.
    assert plan_from_event(_checkout_event(payment_status="unpaid")) is None


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
    # Every non-paying status (incl. the payment-never-succeeded ones) downgrades.
    for status in ("canceled", "unpaid", "incomplete", "incomplete_expired"):
        evt = {
            "type": "customer.subscription.updated",
            "data": {"object": {"status": status, "metadata": {"user_id": "u-9"}}},
        }
        plan = plan_from_event(evt)
        assert plan["action"] == "downgrade" and plan["tier"] == "free", status


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
    # A subscription state change is not a payment — must not book revenue.
    assert plan["is_payment"] is False


def test_subscription_paused_downgrades():
    # A paused subscription (e.g. trial paused for no payment method) must not
    # retain a paid tier.
    evt = {
        "type": "customer.subscription.updated",
        "data": {"object": {"status": "paused", "metadata": {"user_id": "u-p"}}},
    }
    plan = plan_from_event(evt)
    assert plan["action"] == "downgrade" and plan["tier"] == "free"


def test_invoice_paid_books_renewal_revenue(monkeypatch):
    # The documented recurring-renewal event; identity from subscription_details.
    monkeypatch.setitem(TIERS["pro"], "stripe_price_id", "price_PRO_renew")
    evt = {
        "id": "evt_inv_1",
        "type": "invoice.paid",
        "data": {
            "object": {
                "subscription_details": {"metadata": {"user_id": "u-renew", "tier": "pro"}},
                "lines": {"data": [{"price": {"id": "price_PRO_renew"}}]},
            }
        },
    }
    plan = plan_from_event(evt)
    assert plan["action"] == "grant"
    assert plan["user_id"] == "u-renew"
    assert plan["tier"] == "pro"
    assert plan["is_payment"] is True
    assert plan["event_id"] == "evt_inv_1"


def test_invoice_paid_without_identity_is_ignored():
    assert plan_from_event({"type": "invoice.paid", "data": {"object": {}}}) is None


def test_truly_unrelated_event_is_ignored():
    assert plan_from_event({"type": "charge.refunded", "data": {"object": {}}}) is None


def test_tier_for_price_id(monkeypatch):
    monkeypatch.setitem(TIERS["business"], "stripe_price_id", "price_BIZ_1")
    assert tier_for_price_id("price_BIZ_1") == "business"
    assert tier_for_price_id("price_unknown") is None
    assert tier_for_price_id(None) is None


def test_checkout_plan_captures_stripe_customer_id():
    plan = plan_from_event(_checkout_event(customer="cus_XYZ"))
    assert plan["stripe_customer_id"] == "cus_XYZ"


def test_plan_ignores_non_string_customer():
    # Un-expanded events send the customer id as a string; an object would be a
    # bug to persist. Guard against storing a dict.
    evt = _checkout_event()
    evt["data"]["object"]["customer"] = {"id": "cus_obj"}
    plan = plan_from_event(evt)
    assert plan["stripe_customer_id"] is None


# ---------------------------------------------------------------------------
# apply_provision / provision_from_event (side effects, injected manager)
# ---------------------------------------------------------------------------


def test_apply_provision_persists_by_id_and_books_revenue():
    fum = FakeUserManager()
    before = billing.revenue_tracker.summary().get("total_gbp", 0.0)
    result = provision_from_event(
        fum, _checkout_event(user_id="u-77", tier="pro", event_id="evt_persist")
    )
    assert result["handled"] is True
    assert result["action"] == "grant"
    assert result["tier"] == "pro"
    assert result["user_persisted"] is True
    assert result["revenue_booked"] is True
    assert fum.by_id["u-77"] == "pro"
    # recurring revenue booked for the pro price
    after = billing.revenue_tracker.summary().get("total_gbp", 0.0)
    assert after == before + TIERS["pro"]["price_gbp"]


def test_apply_provision_persists_stripe_customer_id():
    fum = FakeUserManager()
    result = provision_from_event(
        fum, _checkout_event(user_id="u-cust", tier="pro", customer="cus_LINK")
    )
    assert result["customer_persisted"] is True
    assert fum.customer_by_id["u-cust"] == "cus_LINK"


def test_apply_provision_without_customer_id_does_not_persist_link():
    fum = FakeUserManager()
    result = provision_from_event(
        fum, _checkout_event(user_id="u-nocust", tier="pro", customer=None)
    )
    assert result["customer_persisted"] is False
    assert "u-nocust" not in fum.customer_by_id


def test_end_to_end_checkout_links_customer_via_real_fallback_manager():
    mgr = DBUserManager(None)
    created = mgr.create_user("carol", "Str0ng-Pass!23")
    uid = created["user_id"]

    provision_from_event(mgr, _checkout_event(user_id=uid, tier="pro", customer="cus_CAROL"))
    # The portal's server-side resolution path now returns the linked customer.
    assert mgr.get_stripe_customer_id(uid) == "cus_CAROL"


def test_revenue_booked_once_per_event_id():
    """Stripe delivers at least once; re-processing the same event must not
    double-book revenue (charliecreates/Sourcery idempotency requirement)."""
    fum = FakeUserManager()
    evt = _checkout_event(user_id="u-dup", tier="business", event_id="evt_dupe_1")
    before = billing.revenue_tracker.summary().get("total_gbp", 0.0)

    first = provision_from_event(fum, evt)
    assert fum.by_id["u-dup"] == "business"  # tier set on first delivery
    second = provision_from_event(fum, evt)  # duplicate delivery / retry
    third = provision_from_event(fum, evt)  # e.g. via the other webhook route

    assert first["revenue_booked"] is True
    assert second["revenue_booked"] is False
    assert third["revenue_booked"] is False
    # tier state converges (idempotent) — unchanged after the duplicate deliveries
    assert fum.by_id["u-dup"] == "business"
    after = billing.revenue_tracker.summary().get("total_gbp", 0.0)
    # booked exactly once despite three deliveries
    assert after == before + TIERS["business"]["price_gbp"]


def test_subscription_updated_grant_books_no_revenue(monkeypatch):
    """An active subscription.updated provisions the tier but is not a payment,
    so it must never book revenue (renewals arrive as invoice.payment_succeeded)."""
    monkeypatch.setitem(TIERS["pro"], "stripe_price_id", "price_PRO_x")
    fum = FakeUserManager()
    evt = {
        "id": "evt_sub_upd",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "status": "active",
                "metadata": {"user_id": "u-sub"},
                "items": {"data": [{"price": {"id": "price_PRO_x"}}]},
            }
        },
    }
    before = billing.revenue_tracker.summary().get("total_gbp", 0.0)
    result = provision_from_event(fum, evt)
    assert result["action"] == "grant" and result["tier"] == "pro"
    assert result["revenue_booked"] is False
    assert fum.by_id["u-sub"] == "pro"  # tier still provisioned
    after = billing.revenue_tracker.summary().get("total_gbp", 0.0)
    assert after == before  # no revenue


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
