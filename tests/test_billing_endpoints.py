"""Tests for POST /billing/portal and GET /billing/status.

Portal: regression + security cover. The handler once called
`stripe_manager.enabled` (no such attribute) and treated a `str | None` return
as a dict, both of which 500'd; a crash-fix then un-masked a BOLA — it accepted
a client-supplied `user_id` and passed it straight to Stripe as the customer id,
so any unauthenticated caller could mint a portal URL for an arbitrary customer.
The endpoint is now bound to the authenticated user and returns 501 until the
Stripe-customer-id linkage lands. These tests pin that closed behaviour.

Status: previously KeyError: 'name' -> 500; `zero_cost_mode` also counted the
`*_price_configured` catalogue flags as if they were live providers.
Driven directly (no app boot).
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from src.monetisation import billing
from src.monetisation.billing import TIERS
from src.monetisation.router import billing_portal, billing_status


def test_portal_is_gated_501_pending_customer_linkage():
    # Bound to the authenticated caller; no client `user_id` is accepted. Until
    # stripe_customer_id persistence exists it must refuse (501), never mint a
    # session for an arbitrary/guessed customer id.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing_portal(user={"sub": "user-123", "username": "alice"}))
    assert exc.value.status_code == 501


def test_portal_does_not_accept_client_customer_id():
    # The signature must not expose a caller-supplied customer/user id parameter
    # (that was the BOLA). Only `return_url` and the injected `user` remain.
    import inspect

    params = set(inspect.signature(billing_portal).parameters)
    assert "user_id" not in params
    assert "customer_id" not in params
    assert params <= {"return_url", "user"}


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
