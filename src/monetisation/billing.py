"""
src/monetisation/billing.py — Trancendos Billing, Tier Enforcement & Multi-Provider Payments.

Payment provider chain (0-cost to integrate, % per transaction only):
  1. Stripe        — primary (free to use, 1.4% + 20p EU cards / 2.9% + 30¢ US)
  2. Lemon Squeezy — fallback SaaS billing (5% + 50¢ per transaction)
  3. Paddle        — fallback merchant-of-record (5% + 50¢)
  4. Ko-fi         — tip/supporter income (0% on free plan)
  5. GitHub Sponsors — open-source passive income (0% fee)

All providers gracefully degrade — system operates in free-only mode
when no payment provider is configured.

Stripe price IDs MUST be real IDs from your Stripe Dashboard:
  Dashboard → Products → Add Product → Add Price → copy price_xxx ID
  Set via env vars: STRIPE_PRO_PRICE_ID, STRIPE_BUSINESS_PRICE_ID
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Billing Tiers
# ---------------------------------------------------------------------------


class BillingTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


def _price_id(env_var: str, expected_prefix: str = "price_") -> Optional[str]:
    """Read a Stripe price ID from env; return None if missing or still a placeholder."""
    val = os.getenv(env_var, "")
    if not val or "placeholder" in val.lower() or not val.startswith(expected_prefix):
        return None
    return val


TIERS: Dict[str, Dict[str, Any]] = {
    "free": {
        "price_gbp": 0,
        "req_per_hour": 100,
        "req_per_day": 500,
        "personalities": ["tranc3-base"],
        "languages": ["en"],
        "quantum": False,
        "consciousness": False,
        "websocket": False,
        "support": "community",
        "stripe_price_id": None,
        "lemon_variant_id": None,
    },
    "pro": {
        "price_gbp": 29,
        "req_per_hour": 1_000,
        "req_per_day": 10_000,
        "personalities": [
            "tranc3-base",
            "tranc3-creative",
            "tranc3-analytical",
            "tranc3-empathetic",
            "tranc3-multilingual",
        ],
        "languages": "all",
        "quantum": True,
        "consciousness": True,
        "websocket": True,
        "support": "email",
        # Real IDs from Stripe/LemonSqueezy dashboard — None if not yet configured
        "stripe_price_id": _price_id("STRIPE_PRO_PRICE_ID"),
        "lemon_variant_id": os.getenv("LEMON_PRO_VARIANT_ID"),
        "paddle_price_id": os.getenv("PADDLE_PRO_PRICE_ID"),
    },
    "business": {
        "price_gbp": 149,
        "req_per_hour": 10_000,
        "req_per_day": 100_000,
        "personalities": "all",
        "languages": "all",
        "quantum": True,
        "consciousness": True,
        "websocket": True,
        "white_label": True,
        "support": "priority",
        "stripe_price_id": _price_id("STRIPE_BUSINESS_PRICE_ID"),
        "lemon_variant_id": os.getenv("LEMON_BUSINESS_VARIANT_ID"),
        "paddle_price_id": os.getenv("PADDLE_BUSINESS_PRICE_ID"),
    },
    "enterprise": {
        "price_gbp": None,
        "req_per_hour": -1,
        "req_per_day": -1,
        "personalities": "all",
        "languages": "all",
        "quantum": True,
        "consciousness": True,
        "websocket": True,
        "white_label": True,
        "on_premise": True,
        "sla": "99.9%",
        "support": "dedicated",
        "stripe_price_id": None,
        "lemon_variant_id": None,
    },
}

# Allowlist mapping for safe log output — values are string literals, not user input.
_SAFE_TIER_LABELS: Dict[str, str] = {k: k for k in TIERS}


def check_rate_limit(
    user_id: str, tier: "BillingTier", request_count: int
) -> Tuple[bool, Optional[str]]:
    tier_key = tier.value if isinstance(tier, BillingTier) else str(tier)
    limits = TIERS.get(tier_key, TIERS["free"])
    hourly = limits.get("req_per_hour", 100)
    if hourly != -1 and request_count > hourly:
        return (
            False,
            f"Hourly rate limit exceeded ({request_count} > {hourly} req/hr for {tier_key})",
        )
    return True, None


# ---------------------------------------------------------------------------
# Usage Tracking
# ---------------------------------------------------------------------------


@dataclass
class UsageRecord:
    user_id: str
    tier: str
    requests_this_hour: int = 0
    requests_today: int = 0
    tokens_this_month: int = 0
    hour_window_start: Optional[datetime] = None
    day_window_start: Optional[datetime] = None

    def __post_init__(self):
        now = datetime.utcnow()
        if self.hour_window_start is None:
            self.hour_window_start = now.replace(minute=0, second=0, microsecond=0)
        if self.day_window_start is None:
            self.day_window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)


class TierEnforcer:
    """Enforce rate limits and feature access per tier."""

    def __init__(self):
        self._usage: Dict[str, UsageRecord] = {}

    def _get_or_create(self, user_id: str, tier: str) -> UsageRecord:
        if user_id not in self._usage:
            self._usage[user_id] = UsageRecord(user_id=user_id, tier=tier)
        return self._usage[user_id]

    def _reset_windows_if_needed(self, record: UsageRecord):
        now = datetime.utcnow()
        if record.hour_window_start and now - record.hour_window_start >= timedelta(hours=1):
            record.requests_this_hour = 0
            record.hour_window_start = now.replace(minute=0, second=0, microsecond=0)
        if record.day_window_start and now - record.day_window_start >= timedelta(days=1):
            record.requests_today = 0
            record.day_window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def check_and_increment(self, user_id: str, tier: str = "free") -> Dict:
        limits = TIERS.get(tier, TIERS["free"])
        record = self._get_or_create(user_id, tier)
        self._reset_windows_if_needed(record)

        hourly_limit = limits["req_per_hour"]
        daily_limit = limits["req_per_day"]

        if hourly_limit != -1 and record.requests_this_hour >= hourly_limit:
            raise ValueError(f"Hourly rate limit exceeded ({hourly_limit} req/hr for {tier})")
        if daily_limit != -1 and record.requests_today >= daily_limit:
            raise ValueError(f"Daily rate limit exceeded ({daily_limit} req/day for {tier})")

        record.requests_this_hour += 1
        record.requests_today += 1

        return {
            "allowed": True,
            "tier": tier,
            "requests_this_hour": record.requests_this_hour,
            "hourly_limit": hourly_limit,
            "remaining_hour": max(0, hourly_limit - record.requests_this_hour)
            if hourly_limit != -1
            else -1,
        }

    def can_use_feature(self, tier: str, feature: str) -> bool:
        return bool(TIERS.get(tier, TIERS["free"]).get(feature, False))

    def get_usage(self, user_id: str) -> Optional[Dict]:
        record = self._usage.get(user_id)
        if not record:
            return None
        return {
            "user_id": record.user_id,
            "tier": record.tier,
            "requests_this_hour": record.requests_this_hour,
            "requests_today": record.requests_today,
            "tokens_this_month": record.tokens_this_month,
        }


# ---------------------------------------------------------------------------
# Stripe Manager
# ---------------------------------------------------------------------------


class StripeManager:
    """Stripe subscription management. Requires real price IDs from Stripe Dashboard."""

    def __init__(self):
        self._key = os.getenv("STRIPE_SECRET_KEY", "")
        self._webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self._enabled = bool(self._key and not self._key.startswith("sk_test_placeholder"))
        self._stripe = None
        if self._enabled:
            try:
                import stripe

                stripe.api_key = self._key
                self._stripe = stripe
                logger.info("Stripe integration enabled")
            except ImportError:
                logger.warning("stripe package not installed — pip install stripe")
                self._enabled = False
        else:
            logger.info("Stripe not configured — running in free-only mode")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def create_checkout_session(
        self, user_id: str, tier: str, success_url: str, cancel_url: str
    ) -> Optional[str]:
        if not self._enabled:
            return None
        price_id = TIERS.get(tier, {}).get("stripe_price_id")
        if not price_id:
            # _SAFE_TIER_LABELS values are string literals; .get() result is never user-input.
            tier_label = _SAFE_TIER_LABELS.get(tier, "unknown")
            logger.error(
                "No Stripe price ID for tier '%s' — set STRIPE_%s_PRICE_ID in .env",
                tier_label,
                tier_label.upper(),
            )
            return None
        try:
            session = self._stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"user_id": user_id, "tier": tier},
                # Copy the identity onto the Subscription too, so later
                # customer.subscription.* events (renewals, cancellations) can be
                # mapped back to the user for tier provisioning/downgrade.
                subscription_data={"metadata": {"user_id": user_id, "tier": tier}},
                tax_id_collection={"enabled": True},
                automatic_tax={"enabled": True},
            )
            return session.url
        except Exception as exc:
            logger.error("Stripe checkout error: %s", sanitize_for_log(exc))
            return None

    def handle_webhook(self, payload: bytes, sig_header: str) -> Optional[Dict]:
        if not self._enabled or not self._webhook_secret:
            return None
        try:
            event = self._stripe.Webhook.construct_event(payload, sig_header, self._webhook_secret)
            # Include the event id so downstream provisioning can dedupe against
            # Stripe's at-least-once delivery (dropping it defeats record_once).
            return {
                "id": event.get("id"),
                "type": event["type"],
                "data": event["data"]["object"],
            }
        except Exception as exc:
            logger.error("Stripe webhook error: %s", sanitize_for_log(exc))
            return None

    def get_subscription_tier(self, stripe_customer_id: str) -> str:
        if not self._enabled:
            return "free"
        try:
            subs = self._stripe.Subscription.list(
                customer=stripe_customer_id, status="active", limit=1
            )
            if not subs.data:
                return "free"
            price_id = subs.data[0]["items"]["data"][0]["price"]["id"]
            for tier, cfg in TIERS.items():
                if cfg.get("stripe_price_id") == price_id:
                    return tier
            return "free"
        except Exception as exc:
            logger.error("Stripe lookup error: %s", sanitize_for_log(exc))
            return "free"

    def cancel_subscription(self, stripe_subscription_id: str) -> bool:
        if not self._enabled:
            return False
        try:
            self._stripe.Subscription.cancel(stripe_subscription_id)
            return True
        except Exception as exc:
            logger.error("Stripe cancel error: %s", sanitize_for_log(exc))
            return False

    def create_portal_session(self, customer_id: str, return_url: str) -> Optional[str]:
        """Stripe billing portal — lets customers manage their own subscription."""
        if not self._enabled:
            return None
        try:
            session = self._stripe.billing_portal.Session.create(
                customer=customer_id, return_url=return_url
            )
            return session.url
        except Exception as exc:
            logger.error("Stripe portal error: %s", sanitize_for_log(exc))
            return None


# ---------------------------------------------------------------------------
# Lemon Squeezy Manager (fallback billing provider)
# ---------------------------------------------------------------------------


class LemonSqueezyManager:
    """
    Lemon Squeezy — 0-cost integration (5% + 50¢ per transaction).
    Better for digital goods, SaaS, lifetime deals.
    https://www.lemonsqueezy.com — free to sign up.
    """

    BASE_URL = "https://api.lemonsqueezy.com/v1"

    def __init__(self):
        self._key = os.getenv("LEMON_SQUEEZY_API_KEY", "")
        self._store_id = os.getenv("LEMON_SQUEEZY_STORE_ID", "")
        self._enabled = bool(self._key and self._store_id)
        if self._enabled:
            logger.info("Lemon Squeezy integration enabled")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def create_checkout(self, tier: str, user_email: str, custom_data: Dict) -> Optional[str]:
        if not self._enabled:
            return None
        variant_id = TIERS.get(tier, {}).get("lemon_variant_id")
        if not variant_id:
            return None
        try:
            import json as _json
            import urllib.request

            body = _json.dumps(
                {
                    "data": {
                        "type": "checkouts",
                        "attributes": {
                            "checkout_data": {
                                "email": user_email,
                                "custom": custom_data,
                            }
                        },
                        "relationships": {
                            "store": {"data": {"type": "stores", "id": self._store_id}},
                            "variant": {"data": {"type": "variants", "id": variant_id}},
                        },
                    }
                }
            ).encode()
            req = urllib.request.Request(
                f"{self.BASE_URL}/checkouts",
                data=body,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Content-Type": "application/vnd.api+json",
                    "Accept": "application/vnd.api+json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 — BASE_URL is hardcoded https://api.lemonsqueezy.com
                data = _json.loads(resp.read())
                return data["data"]["attributes"].get("url")
        except Exception as exc:
            logger.error("LemonSqueezy checkout error: %s", sanitize_for_log(exc))
            return None


# ---------------------------------------------------------------------------
# Billing Router — tries providers in order
# ---------------------------------------------------------------------------


class BillingRouter:
    """
    Multi-provider billing fallback chain.
    Tries Stripe → Lemon Squeezy → Paddle (future) → returns None if all unavailable.
    """

    def __init__(self):
        self.stripe = StripeManager()
        self.lemon = LemonSqueezyManager()

    def create_checkout(
        self,
        user_id: str,
        tier: str,
        user_email: str = "",
        success_url: str = "https://trancendos.com/billing/success",
        cancel_url: str = "https://trancendos.com/billing/cancel",
    ) -> Dict[str, Any]:
        # Stripe first
        if self.stripe.is_enabled:
            url = self.stripe.create_checkout_session(user_id, tier, success_url, cancel_url)
            if url:
                return {"provider": "stripe", "checkout_url": url, "tier": tier}

        # Lemon Squeezy fallback
        if self.lemon.is_enabled:
            url = self.lemon.create_checkout(tier, user_email, {"user_id": user_id})
            if url:
                return {"provider": "lemon_squeezy", "checkout_url": url, "tier": tier}

        return {
            "provider": "none",
            "checkout_url": None,
            "tier": tier,
            "message": "No payment provider configured. Set STRIPE_SECRET_KEY or LEMON_SQUEEZY_API_KEY.",
            "setup_guide": "https://docs.trancendos.com/billing/setup",
        }

    def provider_status(self) -> Dict[str, bool]:
        return {
            "stripe": self.stripe.is_enabled,
            "stripe_pro_price_configured": bool(TIERS["pro"].get("stripe_price_id")),
            "stripe_business_price_configured": bool(TIERS["business"].get("stripe_price_id")),
            "lemon_squeezy": self.lemon.is_enabled,
        }


# ---------------------------------------------------------------------------
# Passive Revenue Engine
# ---------------------------------------------------------------------------


class PassiveRevenueEngine:
    """
    Multi-stream passive revenue tracking and strategy engine.

    Revenue streams (all 0-cost to set up):
      1. SaaS subscriptions      — Stripe/Lemon recurring billing
      2. API usage metering      — pay-per-request above free tier
      3. Personality packs       — one-time purchases (Lemon Squeezy)
      4. White-label licenses    — B2B licensing fees
      5. Affiliate commissions   — referral links (Ko-fi, Gumroad affiliates)
      6. GitHub Sponsors         — open-source supporter income
      7. Ko-fi tips              — community supporter income
      8. Marketplace revenue     — Arcadian Exchange transaction fees (2.5%)
      9. Data insights reports   — anonymised aggregate trend reports
     10. Certification fees      — Trancendos developer certification
     11. NFT/Digital assets      — future: tokenised platform assets
     12. Ad revenue              — opt-in contextual ads (Carbon Ads — free signup)
    """

    STREAMS = {
        "saas_subscriptions": {"description": "Recurring monthly subscriptions", "currency": "GBP"},
        "api_metering": {"description": "Pay-per-request above free tier", "currency": "GBP"},
        "personality_packs": {
            "description": "One-time personality pack purchases",
            "currency": "GBP",
        },
        "white_label_licenses": {"description": "B2B white-label licensing", "currency": "GBP"},
        "affiliate_commissions": {
            "description": "Referral and affiliate income",
            "currency": "GBP",
        },
        "github_sponsors": {"description": "GitHub Sponsors open-source income", "currency": "GBP"},
        "kofi_tips": {"description": "Ko-fi community tips", "currency": "GBP"},
        "marketplace_fees": {
            "description": "Arcadian Exchange 2.5% transaction fee",
            "currency": "GBP",
        },
        "data_insights": {"description": "Anonymised aggregate data reports", "currency": "GBP"},
        "certification_fees": {
            "description": "Developer certification programme",
            "currency": "GBP",
        },
        "ad_revenue": {"description": "Opt-in contextual advertising", "currency": "GBP"},
        "consulting": {"description": "Platform consulting and integration", "currency": "GBP"},
    }

    # Cap on remembered event ids for idempotent booking (bounded memory).
    _MAX_BOOKED_IDS = 10_000

    def __init__(self):
        self._revenue: Dict[str, float] = dict.fromkeys(self.STREAMS, 0.0)
        self._transactions: List[Dict] = []
        # Insertion-ordered set of Stripe event ids already booked, for dedupe.
        self._booked_event_ids: Dict[str, None] = {}

    def record_once(
        self,
        event_id: Optional[str],
        stream: str,
        amount_gbp: float,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Book revenue at most once per Stripe event id. Returns True if it was
        booked, False if this event id was already seen (a duplicate/retry). With
        no event id we cannot dedupe, so we fall back to booking unconditionally."""
        if event_id:
            if event_id in self._booked_event_ids:
                return False
            self._booked_event_ids[event_id] = None
            if len(self._booked_event_ids) > self._MAX_BOOKED_IDS:
                # Evict the oldest remembered id (dict preserves insertion order).
                self._booked_event_ids.pop(next(iter(self._booked_event_ids)))
        self.record(stream, amount_gbp, metadata)
        return True

    def record(self, stream: str, amount_gbp: float, metadata: Optional[Dict] = None):
        if stream not in self._revenue:
            logger.warning("Unknown revenue stream: %s", sanitize_for_log(stream))
            return
        self._revenue[stream] += amount_gbp
        self._transactions.append(
            {
                "stream": stream,
                "amount_gbp": amount_gbp,
                "ts": time.time(),
                "metadata": metadata or {},
            }
        )
        logger.info("Revenue: %s +£%.2f (total: £%.2f)", stream, amount_gbp, self._revenue[stream])

    def marketplace_fee(self, transaction_amount_gbp: float) -> float:
        """Calculate AND record the 2.5% Arcadian Exchange marketplace fee."""
        fee = round(transaction_amount_gbp * 0.025, 2)
        self.record("marketplace_fees", fee, {"transaction_amount": transaction_amount_gbp})
        return fee

    @property
    def streams(self) -> Dict[str, float]:
        """Cumulative revenue per stream (GBP). Returns a **defensive copy** — a
        plain, JSON-serialisable dict — so callers can read (and even mutate) it
        without touching the engine's ledger, and so nobody depends on the private
        `_revenue` attribute (whose absence previously crashed the /billing/revenue
        endpoints). To change recorded revenue, use record()/record_once()."""
        return dict(self._revenue)

    def summary(self) -> Dict:
        total = sum(self._revenue.values())
        active = {k: v for k, v in self._revenue.items() if v > 0}
        return {
            "streams": self._revenue,
            "active_streams": active,
            "total_gbp": round(total, 2),
            "transaction_count": len(self._transactions),
            "top_stream": max(self._revenue, key=lambda k: self._revenue[k]) if total > 0 else None,
        }

    def growth_recommendations(self) -> List[str]:
        """Return actionable zero-cost revenue growth recommendations."""
        recs = []
        if self._revenue["github_sponsors"] == 0:
            recs.append(
                "Set up GitHub Sponsors (0% fee) at github.com/sponsors — passive income from OSS community"
            )
        if self._revenue["kofi_tips"] == 0:
            recs.append(
                "Set up Ko-fi (0% on free plan) at ko-fi.com — low-friction one-time supporter income"
            )
        if self._revenue["affiliate_commissions"] == 0:
            recs.append(
                "Join Anthropic / OpenRouter / Groq affiliate programmes — earn per referred API user"
            )
        if self._revenue["ad_revenue"] == 0:
            recs.append(
                "Apply to Carbon Ads (ethical, dev-focused ads — $30-150 CPM) at carbonads.com"
            )
        if self._revenue["certification_fees"] == 0:
            recs.append(
                "Launch Trancendos Developer Certification — £49/exam, 0-cost to deliver digitally"
            )
        if self._revenue["marketplace_fees"] < 100:
            recs.append(
                "Promote Arcadian Exchange — 2.5% fee on every transaction compounds quickly"
            )
        return recs


# ---------------------------------------------------------------------------
# Tax Monitor
# ---------------------------------------------------------------------------


class TaxMonitor:
    """
    Zero-cost tax compliance monitoring for UK/EU SaaS.

    VAT rules:
      - UK VAT: 20% on digital services to UK consumers (threshold: £85,000/yr)
      - EU VAT OSS: varies by country (15-27%); register via One Stop Shop
      - US: no federal VAT; state sales tax varies — Stripe Tax handles this
      - Free tools: VIES API (EU VAT validation), HMRC Making Tax Digital API

    Stripe Tax (enabled above in checkout) handles collection automatically
    once real price IDs are configured. This monitor tracks obligations.
    """

    UK_VAT_THRESHOLD_GBP = 85_000
    UK_VAT_RATE = 0.20
    EU_DEFAULT_VAT_RATE = 0.20  # varies; use Stripe Tax for per-country rates

    EU_VAT_RATES = {
        "DE": 0.19,
        "FR": 0.20,
        "IT": 0.22,
        "ES": 0.21,
        "NL": 0.21,
        "BE": 0.21,
        "AT": 0.20,
        "PL": 0.23,
        "SE": 0.25,
        "DK": 0.25,
        "FI": 0.24,
        "IE": 0.23,
        "PT": 0.23,
        "RO": 0.19,
        "HU": 0.27,
        "CZ": 0.21,
        "SK": 0.20,
        "BG": 0.20,
        "HR": 0.25,
        "LT": 0.21,
        "LV": 0.21,
        "EE": 0.22,
        "SI": 0.22,
        "GR": 0.24,
        "LU": 0.17,
        "MT": 0.18,
        "CY": 0.19,
    }

    def __init__(self):
        self._annual_revenue_gbp: float = 0.0
        self._vat_collected: Dict[str, float] = {}
        self._transactions: List[Dict] = []

    def record_sale(
        self,
        amount_gbp: float,
        country_code: str = "GB",
        vat_number: Optional[str] = None,
    ) -> Dict:
        """Record a sale and calculate VAT obligations."""
        self._annual_revenue_gbp += amount_gbp

        # B2B sales with valid VAT number — reverse charge (no VAT to collect)
        if vat_number and country_code != "GB":
            vat_amount = 0.0
            vat_treatment = "reverse_charge"
        elif country_code == "GB":
            vat_rate = (
                self.UK_VAT_RATE if self._annual_revenue_gbp >= self.UK_VAT_THRESHOLD_GBP else 0.0
            )
            vat_amount = round(amount_gbp * vat_rate, 2)
            vat_treatment = "uk_vat" if vat_rate > 0 else "below_threshold"
        elif country_code in self.EU_VAT_RATES:
            rate = self.EU_VAT_RATES[country_code]
            vat_amount = round(amount_gbp * rate, 2)
            vat_treatment = f"eu_oss_{country_code}"
        else:
            vat_amount = 0.0
            vat_treatment = "no_vat_jurisdiction"

        self._vat_collected[country_code] = self._vat_collected.get(country_code, 0.0) + vat_amount
        record = {
            "amount_gbp": amount_gbp,
            "country": country_code,
            "vat_amount_gbp": vat_amount,
            "vat_treatment": vat_treatment,
            "ts": time.time(),
        }
        self._transactions.append(record)
        return record

    def validate_eu_vat_number(self, vat_number: str, country_code: str) -> bool:
        """Validate EU VAT number via VIES API (free, no key required)."""
        try:
            import urllib.request

            import defusedxml.ElementTree as ET  # nosec B405 — defusedxml prevents XXE

            soap = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"'
                ' xmlns:urn="urn:ec.europa.eu:taxud:vies:services:checkVat:types">'
                "<soapenv:Body><urn:checkVat>"
                f"<urn:countryCode>{country_code}</urn:countryCode>"
                f"<urn:vatNumber>{vat_number.replace(country_code, '')}</urn:vatNumber>"
                "</urn:checkVat></soapenv:Body></soapenv:Envelope>"
            ).encode()
            req = urllib.request.Request(
                "https://ec.europa.eu/taxation_customs/vies/services/checkVatService",
                data=soap,
                headers={"Content-Type": "text/xml"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310 — URL is hardcoded https://ec.europa.eu
                tree = ET.fromstring(resp.read())
                valid_el = tree.find(
                    ".//{urn:ec.europa.eu:taxud:vies:services:checkVat:types}valid"
                )
                return valid_el is not None and valid_el.text == "true"
        except Exception:
            return False  # fail open — Stripe Tax handles validation in production

    def obligations_summary(self) -> Dict:
        total_vat = sum(self._vat_collected.values())
        uk_threshold_reached = self._annual_revenue_gbp >= self.UK_VAT_THRESHOLD_GBP
        return {
            "annual_revenue_gbp": round(self._annual_revenue_gbp, 2),
            "uk_vat_registration_required": uk_threshold_reached,
            "uk_vat_threshold_gbp": self.UK_VAT_THRESHOLD_GBP,
            "uk_vat_threshold_remaining_gbp": max(
                0, round(self.UK_VAT_THRESHOLD_GBP - self._annual_revenue_gbp, 2)
            ),
            "vat_collected_by_country": {k: round(v, 2) for k, v in self._vat_collected.items()},
            "total_vat_collected_gbp": round(total_vat, 2),
            "eu_oss_required": any(c != "GB" for c in self._vat_collected),
            "stripe_tax_enabled": bool(os.getenv("STRIPE_SECRET_KEY")),
            "compliance_note": (
                "Stripe Tax (enabled in checkout) handles VAT collection automatically. "
                "File quarterly VAT returns via HMRC Making Tax Digital."
            ),
        }

    def tax_benefit_summary(self) -> Dict:
        """UK tax benefits and allowances applicable to a SaaS business."""
        return {
            "rd_tax_credit": {
                "description": "HMRC R&D Tax Credit — SME scheme: 86% enhancement + 10% credit",
                "eligible_activities": [
                    "AI model development (Luminous, aeonmind)",
                    "Quantum computing research (Think Tank)",
                    "Novel infrastructure design (Dimensional, gas/genetics/liquid)",
                    "Security research (Cryptex)",
                ],
                "claim_method": "CT600 Corporation Tax return — free to self-file",
                "typical_benefit": "33p per £1 of qualifying R&D spend for loss-making SMEs",
            },
            "annual_investment_allowance": {
                "description": "100% first-year deduction on qualifying capital expenditure",
                "limit_gbp": 1_000_000,
                "applicable_to": "Server hardware, development tools, software licences",
            },
            "patent_box": {
                "description": "10% Corporation Tax rate on profits from patented inventions",
                "applicable_to": "Any novel algorithms, AI methods that can be patented",
            },
            "trading_allowance": {
                "description": "£1,000/year tax-free trading income (sole trader / pre-incorporation)",
                "amount_gbp": 1_000,
            },
            "vat_flat_rate_scheme": {
                "description": "Pay fixed % of turnover instead of tracking every purchase",
                "it_sector_rate": "14.5% of VAT-inclusive turnover",
                "benefit": "Simpler accounting; may retain difference on purchases",
            },
            "startup_relief": {
                "description": "SEIS: 50% income tax relief on investments up to £200k",
                "description_eis": "EIS: 30% income tax relief on investments up to £5M",
                "benefit": "Attract investors at 0 extra cost to the company",
            },
        }


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

enforcer = TierEnforcer()
stripe_manager = StripeManager()
billing_router = BillingRouter()
revenue_tracker = PassiveRevenueEngine()
tax_monitor = TaxMonitor()


# ---------------------------------------------------------------------------
# Webhook-driven subscription provisioning
# ---------------------------------------------------------------------------
# Validating a Stripe webhook signature is necessary but NOT sufficient: a paid
# checkout only actually grants the customer their plan once the platform records
# the new tier. The functions below turn a verified Stripe event into a concrete
# provisioning action (grant/downgrade) and apply it to the persistent user store
# (+ the live rate-limit cache and revenue ledger). Kept free of any api.py import
# so it stays unit-testable: the caller injects the user manager.


def tier_for_price_id(price_id: Optional[str]) -> Optional[str]:
    """Reverse-map a configured Stripe price ID back to its tier key, or None."""
    if not price_id:
        return None
    for tier, cfg in TIERS.items():
        if cfg.get("stripe_price_id") and cfg["stripe_price_id"] == price_id:
            return tier
    return None


def _subscription_price_id(sub_obj: Dict[str, Any]) -> Optional[str]:
    """Pull the (first) active price ID out of a Stripe Subscription object."""
    try:
        items = (sub_obj.get("items") or {}).get("data") or []
        if items:
            return (items[0].get("price") or {}).get("id")
    except Exception:  # malformed/partial event payload
        return None
    return None


# Subscription statuses that mean the customer does NOT have a paid entitlement.
# `incomplete` / `incomplete_expired` mean the initial payment never succeeded;
# `paused` means billing is suspended (e.g. a trial paused for lack of a payment
# method). None of these may grant a paid tier even though the subscription still
# carries items/price IDs.
_INACTIVE_SUB_STATUSES = {
    "canceled",
    "unpaid",
    "incomplete",
    "incomplete_expired",
    "paused",
}


def plan_from_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Turn a verified Stripe event dict into a provisioning plan, or None if the
    event isn't one we act on / lacks the identity needed to act safely.

    Plan shape: {"action": "grant"|"downgrade", "user_id": str, "tier": str,
                 "event": <type>, "event_id": <id>, "is_payment": bool}. Pure — no
    side effects, no I/O. `is_payment` marks the events that represent an actual
    successful charge (so only those book revenue), and `event_id` lets the caller
    dedupe against Stripe's at-least-once delivery.
    """
    etype = event.get("type", "")
    event_id = event.get("id")
    obj = (event.get("data") or {}).get("object") or {}
    md = obj.get("metadata") or {}
    user_id = md.get("user_id")
    # The Stripe customer id (cus_...) rides on every actionable object
    # (checkout session, subscription, invoice). Capture it so provisioning can
    # persist the durable user->customer link the billing portal resolves from.
    customer_id = obj.get("customer") if isinstance(obj.get("customer"), str) else None

    def _grant(tier: str, *, is_payment: bool) -> Dict[str, Any]:
        return {
            "action": "grant",
            "user_id": user_id,
            "tier": tier,
            "event": etype,
            "event_id": event_id,
            "is_payment": is_payment,
            "stripe_customer_id": customer_id,
        }

    def _downgrade() -> Dict[str, Any]:
        return {
            "action": "downgrade",
            "user_id": user_id,
            "tier": "free",
            "event": etype,
            "event_id": event_id,
            "is_payment": False,
            "stripe_customer_id": customer_id,
        }

    if etype == "checkout.session.completed":
        tier = md.get("tier")
        # Only a paid session grants (async payment methods can complete a session
        # while still "unpaid"); "no_payment_required" is a 100%-off coupon → grant.
        paid = obj.get("payment_status", "paid") != "unpaid"
        if user_id and tier in TIERS and tier != "free" and paid:
            return _grant(tier, is_payment=True)
        return None

    if etype == "customer.subscription.updated":
        if not user_id:
            return None
        if obj.get("status") in _INACTIVE_SUB_STATUSES:
            return _downgrade()
        # Prefer the tier implied by the current price; fall back to metadata.
        tier = tier_for_price_id(_subscription_price_id(obj))
        if tier is None and md.get("tier") in TIERS:
            tier = md["tier"]
        if tier and tier != "free":
            # A subscription state change is NOT a payment — provision the tier but
            # never book revenue here (renewals arrive as invoice.payment_succeeded).
            return _grant(tier, is_payment=False)
        return None

    if etype == "customer.subscription.deleted":
        if user_id:
            return _downgrade()
        return None

    if etype == "invoice.paid":
        # Recurring renewal payment — the documented Stripe renewal event. Identity
        # lives on the subscription (copied to the invoice as subscription_details.
        # metadata); tier from the line item price, falling back to that metadata.
        inv_md = (obj.get("subscription_details") or {}).get("metadata") or md
        inv_user = inv_md.get("user_id")
        lines = (obj.get("lines") or {}).get("data") or []
        price_id = (lines[0].get("price") or {}).get("id") if lines else None
        tier = tier_for_price_id(price_id)
        if tier is None and inv_md.get("tier") in TIERS:
            tier = inv_md["tier"]
        if inv_user and tier and tier != "free":
            return {
                "action": "grant",
                "user_id": inv_user,
                "tier": tier,
                "event": etype,
                "event_id": event_id,
                "is_payment": True,
                "stripe_customer_id": customer_id,
            }
        return None

    return None


def apply_provision(user_manager: Any, plan: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply a provisioning plan: persist the user's new tier (by id, then by
    username as a fallback), reflect it in the live rate-limit cache, and record
    recurring revenue on an upgrade. Idempotent — re-applying the same plan just
    re-sets the same tier. `user_manager` is injected so this stays testable.
    """
    if not plan:
        return {"handled": False}

    user_id = plan["user_id"]
    tier = plan["tier"]
    persisted = False
    try:
        if hasattr(user_manager, "update_tier_by_id"):
            persisted = bool(user_manager.update_tier_by_id(user_id, tier))
        if not persisted and hasattr(user_manager, "update_tier"):
            # metadata may have carried a username rather than an id
            persisted = bool(user_manager.update_tier(user_id, tier))
    except Exception as exc:  # never let provisioning raise into the webhook
        logger.error("provision: tier persist failed: %s", sanitize_for_log(exc))

    if not persisted:
        # The webhook still 200s (so Stripe doesn't retry a validly-parsed event),
        # but this needs an operator's eye — the customer paid but we couldn't
        # record their tier against any known user.
        logger.warning(
            "provision: tier NOT persisted user=%s tier=%s event=%s",
            sanitize_for_log(user_id),
            sanitize_for_log(tier),
            sanitize_for_log(plan.get("event")),
        )

    # Persist the durable user -> Stripe customer link (best-effort, never fatal to
    # the webhook). This is what lets POST /billing/portal resolve the caller's
    # customer id server-side instead of trusting a client-supplied value.
    customer_persisted = False
    stripe_customer_id = plan.get("stripe_customer_id")
    if stripe_customer_id and hasattr(user_manager, "set_stripe_customer_id"):
        try:
            customer_persisted = bool(
                user_manager.set_stripe_customer_id(user_id, stripe_customer_id)
            )
        except Exception as exc:  # never let this raise into the webhook
            logger.error("provision: stripe_customer_id persist failed: %s", sanitize_for_log(exc))

    # Note: we deliberately do NOT poke the TierEnforcer usage cache here — rate
    # limiting resolves the tier from the value the caller passes to
    # check_and_increment (sourced from the authenticated user, i.e. the store we
    # just updated), so the persisted tier already governs the user's next request.

    # Book revenue ONLY for a genuine payment event, and only once per Stripe
    # event id — Stripe delivers at least once and both webhook routes share this
    # singleton, so dedupe here prevents double-counting on retries/duplicates.
    revenue_booked = False
    if plan.get("is_payment") and plan["action"] == "grant":
        price = TIERS.get(tier, {}).get("price_gbp") or 0
        if price:
            revenue_booked = revenue_tracker.record_once(
                plan.get("event_id"),
                "saas_subscriptions",
                float(price),
                {"user_id": user_id, "tier": tier, "event": plan.get("event")},
            )

    return {
        "handled": True,
        "action": plan["action"],
        "tier": tier,
        "user_persisted": persisted,
        "revenue_booked": revenue_booked,
        "customer_persisted": customer_persisted,
    }


def provision_from_event(user_manager: Any, event: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience: parse a verified Stripe event and apply the resulting plan."""
    return apply_provision(user_manager, plan_from_event(event))
