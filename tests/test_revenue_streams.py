"""Tests for the revenue-stream accessor + /billing/revenue endpoints.

Regression cover for a live crash: the endpoints referenced `tracker.streams`,
which PassiveRevenueEngine never exposed, so GET /billing/revenue/summary and
POST /billing/revenue/marketplace-fee both 500'd. Driven without booting the app
(the router handlers are called directly).
"""

from __future__ import annotations

import asyncio

from src.monetisation import billing
from src.monetisation.billing import PassiveRevenueEngine
from src.monetisation.router import (
    MarketplaceFeeRequest,
    record_marketplace_fee,
    revenue_summary,
)


def test_streams_property_is_readonly_float_view():
    e = PassiveRevenueEngine()
    assert isinstance(e.streams, dict)
    assert all(isinstance(v, float) for v in e.streams.values())
    # returns a copy — mutating it must not corrupt the engine's ledger
    e.streams["marketplace_fees"] = 999.0
    assert e.streams["marketplace_fees"] == 0.0


def test_marketplace_fee_records_once_at_2_5_percent():
    e = PassiveRevenueEngine()
    fee = e.marketplace_fee(200.0)
    assert fee == 5.0  # 2.5% of 200
    assert e.streams["marketplace_fees"] == 5.0
    # a second transaction accumulates (it is not deduped — each sale is real)
    e.marketplace_fee(100.0)
    assert e.streams["marketplace_fees"] == 7.5


def test_marketplace_fee_endpoint_returns_fee_and_books_once():
    before = billing.revenue_tracker.streams["marketplace_fees"]
    result = asyncio.run(
        record_marketplace_fee(MarketplaceFeeRequest(transaction_amount=400.0, description="sale"))
    )
    assert result["platform_fee"] == 10.0  # 2.5% of 400
    assert result["fee_rate"] == "2.5%"
    after = billing.revenue_tracker.streams["marketplace_fees"]
    # booked exactly once (no double-count from the old streams[...] write)
    assert after == before + 10.0
    assert result["marketplace_fees_total"] == round(after, 4)


def test_revenue_summary_endpoint_does_not_crash():
    # Previously raised AttributeError on tracker.streams.
    out = asyncio.run(revenue_summary())
    assert "summary" in out
    assert "growth_recommendations" in out
    assert isinstance(out["streams"], dict)
    assert "marketplace_fees" in out["streams"]
