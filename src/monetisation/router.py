"""
src/monetisation/router.py — Billing, Revenue & Tax REST endpoints.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("src.monetisation.router")

router = APIRouter(prefix="/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    user_id: str
    tier: str  # "pro" | "business"
    user_email: Optional[str] = None
    success_url: str = "https://trancendos.com/billing/success"
    cancel_url: str = "https://trancendos.com/billing/cancel"


class MarketplaceFeeRequest(BaseModel):
    transaction_amount: float = Field(..., gt=0)
    description: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _billing():
    from src.monetisation.billing import billing_router as br

    return br


def _revenue():
    from src.monetisation.billing import revenue_tracker

    return revenue_tracker


def _tax():
    from src.monetisation.billing import tax_monitor

    return tax_monitor


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status")
async def billing_status():
    """Provider availability and tier configuration."""
    from src.monetisation.billing import TIERS

    provider_status = _billing().provider_status()
    tiers_info = {
        tier_key: {
            "name": cfg["name"],
            "price_monthly": cfg.get("price_monthly"),
            "price_gbp": cfg.get("price_gbp"),
            "requests_per_hour": cfg.get("requests_per_hour"),
            "stripe_price_configured": cfg.get("stripe_price_id") is not None,
        }
        for tier_key, cfg in TIERS.items()
    }
    return {
        "providers": provider_status,
        "tiers": tiers_info,
        "zero_cost_mode": not any(provider_status.values()),
    }


@router.post("/checkout")
async def create_checkout(req: CheckoutRequest):
    """
    Create a checkout session for a billing tier.
    Provider chain: Stripe → Lemon Squeezy → setup guide.
    """
    result = _billing().create_checkout(
        user_id=req.user_id,
        tier=req.tier,
        user_email=req.user_email,
        success_url=req.success_url,
        cancel_url=req.cancel_url,
    )
    if result.get("error"):
        raise HTTPException(status_code=503, detail=result)
    return result


@router.post("/portal")
async def billing_portal(user_id: str, return_url: str = "https://trancendos.com/account"):
    """Open Stripe billing portal for a customer."""
    from src.monetisation.billing import stripe_manager

    if not stripe_manager.enabled:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    result = stripe_manager.create_portal_session(
        customer_id=user_id,
        return_url=return_url,
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


def _current_user_manager():
    """Fetch the live DBUserManager the app swaps in at startup, without a
    module-load-time import of api.py (which imports this router)."""
    try:
        import api

        return getattr(api, "db_user_manager", None)
    except Exception:  # api not importable (e.g. router used in isolation)
        return None


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request, stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """Handle Stripe webhook events and provision the customer's tier.

    NB: this platform exposes a second webhook route at `/billing/webhook`
    (defined in api.py) with identical provisioning — configure only ONE of them
    in the Stripe dashboard to avoid double-processing an event.
    """
    from src.monetisation.billing import provision_from_event, stripe_manager

    body = await request.body()
    # Pass the RAW bytes: Stripe's signature verification is over the exact bytes,
    # and a decode/re-encode round-trip can change them and fail verification.
    result = stripe_manager.handle_webhook(
        payload=body,
        sig_header=stripe_signature or "",
    )
    # handle_webhook returns None on an invalid signature or when Stripe isn't
    # configured (it never returns an "error" key), so guard on falsiness.
    if not result:
        raise HTTPException(status_code=400, detail="Invalid or unconfigured Stripe webhook")

    # Reshape the flattened {type, data:object} into an event and provision.
    event = {"type": result.get("type", ""), "data": {"object": result.get("data") or {}}}
    provisioned = provision_from_event(_current_user_manager(), event)
    return {"received": True, "type": result.get("type"), "provisioned": provisioned}


@router.get("/revenue/summary")
async def revenue_summary():
    """12-stream passive revenue summary with growth recommendations."""
    tracker = _revenue()
    return {
        "summary": tracker.summary(),
        "growth_recommendations": tracker.growth_recommendations(),
        "streams": tracker.streams,
    }


@router.post("/revenue/marketplace-fee")
async def record_marketplace_fee(req: MarketplaceFeeRequest):
    """Record a marketplace transaction and return the 2.5% platform fee."""
    tracker = _revenue()
    fee = tracker.marketplace_fee(req.transaction_amount)
    tracker.streams["marketplace_fees"]["monthly_estimate"] = (
        tracker.streams["marketplace_fees"].get("monthly_estimate", 0.0) + fee
    )
    return {
        "transaction_amount": req.transaction_amount,
        "platform_fee": round(fee, 4),
        "fee_rate": "2.5%",
        "description": req.description,
    }


@router.get("/tax/summary")
async def tax_summary():
    """UK & EU VAT obligations + applicable tax benefits."""
    monitor = _tax()
    return {
        "obligations": monitor.obligations_summary(),
        "benefits": monitor.tax_benefit_summary(),
    }


@router.post("/tax/record-sale")
async def record_sale(
    amount: float,
    country_code: str = "GB",
    vat_number: Optional[str] = None,
):
    """Record a sale for VAT tracking."""
    monitor = _tax()
    monitor.record_sale(
        amount=amount,
        country_code=country_code.upper(),
        vat_number=vat_number,
    )
    return {
        "recorded": True,
        "amount": amount,
        "country": country_code.upper(),
        "reverse_charge": bool(vat_number),
        "threshold_status": monitor.obligations_summary().get("uk_vat", {}),
    }


@router.post("/tax/validate-vat")
async def validate_vat(vat_number: str):
    """Validate EU VAT number via free VIES API."""
    monitor = _tax()
    valid = monitor.validate_eu_vat_number(vat_number)
    return {"vat_number": vat_number, "valid": valid, "source": "VIES (EU Commission — free)"}
