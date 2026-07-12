"""Tests for POST /billing/portal.

Regression cover for two runtime bugs: the handler called `stripe_manager.enabled`
(no such attribute — it's `is_enabled`), and treated `create_portal_session`'s
`Optional[str]` return as a dict (`"error" in result`), both of which 500'd.
Driven directly (no app boot).
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from src.monetisation import billing
from src.monetisation.billing import TIERS
from src.monetisation.router import billing_portal, billing_status


class _FakeStripe:
    def __init__(self, is_enabled: bool, portal_url):
        self.is_enabled = is_enabled
        self._portal_url = portal_url

    def create_portal_session(self, customer_id: str, return_url: str):
        return self._portal_url


def test_portal_returns_503_when_stripe_disabled(monkeypatch):
    monkeypatch.setattr(billing, "stripe_manager", _FakeStripe(False, None))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing_portal(user_id="cus_1"))
    assert exc.value.status_code == 503


def test_portal_returns_502_when_session_creation_fails(monkeypatch):
    # Enabled, but Stripe call returns None (create_portal_session failure).
    monkeypatch.setattr(billing, "stripe_manager", _FakeStripe(True, None))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(billing_portal(user_id="cus_1"))
    assert exc.value.status_code == 502


def test_portal_returns_url_on_success(monkeypatch):
    url = "https://billing.stripe.com/session/xyz"
    monkeypatch.setattr(billing, "stripe_manager", _FakeStripe(True, url))
    result = asyncio.run(billing_portal(user_id="cus_1"))
    assert result == {"portal_url": url}


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


def test_status_reports_zero_cost_mode_when_no_provider():
    # No Stripe/Lemon configured in tests → zero-cost mode true.
    out = asyncio.run(billing_status())
    assert out["zero_cost_mode"] is True
