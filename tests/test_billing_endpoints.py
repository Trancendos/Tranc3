"""Tests for POST /billing/portal and GET /billing/status.

Portal: regression + security cover. The handler once called
`stripe_manager.enabled` (no such attribute) and treated a `str | None` return
as a dict, both of which 500'd; a crash-fix then un-masked a BOLA — it accepted
a client-supplied `user_id` and passed it straight to Stripe as the customer id,
so any unauthenticated caller could mint a portal URL for an arbitrary customer.
The endpoint is now bound to the authenticated user and resolves that user's
Stripe customer id **server-side** from the persisted link. These tests pin the
closed behaviour: no client id in the signature, 503 when Stripe is off, 409 when
the caller has no customer on file, 502 on session-creation failure, and a URL on
success.

Status: previously KeyError: 'name' -> 500; `zero_cost_mode` also counted the
`*_price_configured` catalogue flags as if they were live providers.
Driven directly (no app boot).
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from src.monetisation import billing
from src.monetisation import router as billing_router_mod
from src.monetisation.billing import TIERS
from src.monetisation.router import billing_portal, billing_status


class _FakeStripe:
    def __init__(self, is_enabled: bool, portal_url):
        self.is_enabled = is_enabled
        self._portal_url = portal_url
        self.seen_customer_id = None

    def create_portal_session(self, customer_id: str, return_url: str):
        self.seen_customer_id = customer_id
        return self._portal_url


class _FakeManager:
    def __init__(self, mapping: dict):
        self._mapping = mapping

    def get_stripe_customer_id(self, identifier):
        return self._mapping.get(identifier)


def _patch_portal(monkeypatch, *, stripe, customer_map):
    monkeypatch.setattr(billing, "stripe_manager", stripe)
    monkeypatch.setattr(
        billing_router_mod, "_current_user_manager", lambda: _FakeManager(customer_map)
    )


def test_portal_does_not_accept_client_customer_id():
    # The signature must not expose a caller-supplied customer/user id parameter
    # (that was the BOLA). Only `return_url` and the injected `user` remain.
    import inspect

    params = set(inspect.signature(billing_portal).parameters)
    assert "user_id" not in params
    assert "customer_id" not in params
    assert params <= {"return_url", "user"}


def test_portal_503_when_stripe_disabled(monkeypatch):
    _patch_portal(monkeypatch, stripe=_FakeStripe(False, None), customer_map={})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing_portal(user={"sub": "u-1", "username": "alice"}))
    assert exc.value.status_code == 503


def test_portal_409_when_no_customer_on_file(monkeypatch):
    # Authenticated but never subscribed → 409, and Stripe is never asked to mint
    # a session for a guessed id.
    stripe = _FakeStripe(True, "https://billing.stripe.com/x")
    _patch_portal(monkeypatch, stripe=stripe, customer_map={})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing_portal(user={"sub": "u-1", "username": "alice"}))
    assert exc.value.status_code == 409
    assert stripe.seen_customer_id is None


def test_portal_502_when_session_creation_fails(monkeypatch):
    stripe = _FakeStripe(True, None)  # enabled, but Stripe returns None
    _patch_portal(monkeypatch, stripe=stripe, customer_map={"u-1": "cus_1"})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing_portal(user={"sub": "u-1", "username": "alice"}))
    assert exc.value.status_code == 502


def test_portal_returns_url_and_uses_server_resolved_customer(monkeypatch):
    url = "https://billing.stripe.com/session/xyz"
    stripe = _FakeStripe(True, url)
    _patch_portal(monkeypatch, stripe=stripe, customer_map={"u-1": "cus_SERVER"})
    result = asyncio.run(billing_portal(user={"sub": "u-1", "username": "alice"}))
    assert result == {"portal_url": url}
    # The customer id came from our store, keyed by the token subject — never the
    # request.
    assert stripe.seen_customer_id == "cus_SERVER"


def test_portal_falls_back_to_username_for_legacy_tokens(monkeypatch):
    url = "https://billing.stripe.com/session/legacy"
    stripe = _FakeStripe(True, url)
    # No `sub` match; resolve by username instead.
    _patch_portal(monkeypatch, stripe=stripe, customer_map={"alice": "cus_LEGACY"})
    result = asyncio.run(billing_portal(user={"username": "alice"}))
    assert result == {"portal_url": url}
    assert stripe.seen_customer_id == "cus_LEGACY"


# --- GET /billing/status (previously KeyError: 'name' -> 500) -----------------


def test_status_does_not_crash_and_maps_real_tier_keys():
    out = asyncio.run(billing_status())
    assert set(out) == {"providers", "tiers", "zero_cost_mode"}
    # every tier is represented with the corrected key mapping
    assert set(out["tiers"]) == set(TIERS)
    for tier_key, info in out["tiers"].items():
        assert info["name"] == tier_key.title()
        # requests_per_hour is sourced from the real `req_per_hour` key (not None)
        assert info["requests_per_hour"] == TIERS[tier_key].get("req_per_hour")
        assert info["price_gbp"] == TIERS[tier_key].get("price_gbp")
        assert "stripe_price_configured" in info


def _patch_provider_status(monkeypatch, status: dict):
    """Force provider_status() to a known value so the test is independent of
    ambient STRIPE_* / LEMON_* env vars."""

    class _FakeRouter:
        def provider_status(self):
            return status

    monkeypatch.setattr(billing, "billing_router", _FakeRouter())


def test_status_reports_zero_cost_mode_when_no_provider(monkeypatch):
    _patch_provider_status(
        monkeypatch,
        {
            "stripe": False,
            "stripe_pro_price_configured": False,
            "stripe_business_price_configured": False,
            "lemon_squeezy": False,
        },
    )
    out = asyncio.run(billing_status())
    assert out["zero_cost_mode"] is True


def test_status_price_configured_alone_is_not_a_live_provider(monkeypatch):
    # Regression: a configured price ID must NOT flip zero_cost_mode off while
    # every real provider is disabled (the old `any(dict.values())` bug did).
    _patch_provider_status(
        monkeypatch,
        {
            "stripe": False,
            "stripe_pro_price_configured": True,
            "stripe_business_price_configured": True,
            "lemon_squeezy": False,
        },
    )
    out = asyncio.run(billing_status())
    assert out["zero_cost_mode"] is True


def test_status_live_stripe_disables_zero_cost_mode(monkeypatch):
    _patch_provider_status(
        monkeypatch,
        {
            "stripe": True,
            "stripe_pro_price_configured": False,
            "stripe_business_price_configured": False,
            "lemon_squeezy": False,
        },
    )
    out = asyncio.run(billing_status())
    assert out["zero_cost_mode"] is False
