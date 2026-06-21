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
            "tranc3-base", "tranc3-creative", "tranc3-analytical",
            "tranc3-empathetic", "tranc3-multilingual",
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


def check_rate_limit(
    user_id: str, tier: "BillingTier", request_count: int
) -> Tuple[bool, Optional[str]]:
    tier_key = tier.value if isinstance(tier, BillingTier) else str(tier)
    limits = TIERS.get(tier_key, TIERS["free"])
    hourly = limits.get("req_per_hour", 100)
    if hourly != -1 and request_count > hourly:
        return False, f"Hourly rate limit exceeded ({request_count} > {hourly} req/hr for {tier_key})"
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
            "remaining_hour": max(0, hourly_limit - record.requests_this_hour) if hourly_limit != -1 else -1,
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
            logger.error(
                "No Stripe price ID for tier '%s' — set STRIPE_%s_PRICE_ID in .env",
                tier, tier.upper()
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
            event = self._stripe.Webhook.construct_event(
                payload, sig_header, self._webhook_secret
            )
            return {"type": event["type"], "data": event["data"]["object"]}
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
            body = _json.dumps({
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
            }).encode()
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
            with urllib.request.urlopen(req, timeout=10) as resp:
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
        "personality_packs": {"description": "One-time personality pack purchases", "currency": "GBP"},
        "white_label_licenses": {"description": "B2B white-label licensing", "currency": "GBP"},
        "affiliate_commissions": {"description": "Referral and affiliate income", "currency": "GBP"},
        "github_sponsors": {"description": "GitHub Sponsors open-source income", "currency": "GBP"},
        "kofi_tips": {"description": "Ko-fi community tips", "currency": "GBP"},
        "marketplace_fees": {"description": "Arcadian Exchange 2.5% transaction fee", "currency": "GBP"},
        "data_insights": {"description": "Anonymised aggregate data reports", "currency": "GBP"},
        "certification_fees": {"description": "Developer certification programme", "currency": "GBP"},
        "ad_revenue": {"description": "Opt-in contextual advertising", "currency": "GBP"},
        "consulting": {"description": "Platform consulting and integration", "currency": "GBP"},
    }

    def __init__(self):
        self._revenue: Dict[str, float] = dict.fromkeys(self.STREAMS, 0.0)
        self._transactions: List[Dict] = []

    def record(self, stream: str, amount_gbp: float, metadata: Optional[Dict] = None):
        if stream not in self._revenue:
            logger.warning("Unknown revenue stream: %s", sanitize_for_log(stream))
            return
        self._revenue[stream] += amount_gbp
        self._transactions.append({
            "stream": stream,
            "amount_gbp": amount_gbp,
            "ts": time.time(),
            "metadata": metadata or {},
        })
        logger.info("Revenue: %s +£%.2f (total: £%.2f)", stream, amount_gbp, self._revenue[stream])

    def marketplace_fee(self, transaction_amount_gbp: float) -> float:
        """Calculate 2.5% Arcadian Exchange marketplace fee."""
        fee = round(transaction_amount_gbp * 0.025, 2)
        self.record("marketplace_fees", fee, {"transaction_amount": transaction_amount_gbp})
        return fee

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
            recs.append("Set up GitHub Sponsors (0% fee) at github.com/sponsors — passive income from OSS community")
        if self._revenue["kofi_tips"] == 0:
            recs.append("Set up Ko-fi (0% on free plan) at ko-fi.com — low-friction one-time supporter income")
        if self._revenue["affiliate_commissions"] == 0:
            recs.append("Join Anthropic / OpenRouter / Groq affiliate programmes — earn per referred API user")
        if self._revenue["ad_revenue"] == 0:
            recs.append("Apply to Carbon Ads (ethical, dev-focused ads — $30-150 CPM) at carbonads.com")
        if self._revenue["certification_fees"] == 0:
            recs.append("Launch Trancendos Developer Certification — £49/exam, 0-cost to deliver digitally")
        if self._revenue["marketplace_fees"] < 100:
            recs.append("Promote Arcadian Exchange — 2.5% fee on every transaction compounds quickly")
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
        "DE": 0.19, "FR": 0.20, "IT": 0.22, "ES": 0.21, "NL": 0.21,
        "BE": 0.21, "AT": 0.20, "PL": 0.23, "SE": 0.25, "DK": 0.25,
        "FI": 0.24, "IE": 0.23, "PT": 0.23, "RO": 0.19, "HU": 0.27,
        "CZ": 0.21, "SK": 0.20, "BG": 0.20, "HR": 0.25, "LT": 0.21,
        "LV": 0.21, "EE": 0.22, "SI": 0.22, "GR": 0.24, "LU": 0.17,
        "MT": 0.18, "CY": 0.19,
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
            vat_rate = self.UK_VAT_RATE if self._annual_revenue_gbp >= self.UK_VAT_THRESHOLD_GBP else 0.0
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
            import xml.etree.ElementTree as ET
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
            with urllib.request.urlopen(req, timeout=5) as resp:
                tree = ET.fromstring(resp.read())
                valid_el = tree.find(".//{urn:ec.europa.eu:taxud:vies:services:checkVat:types}valid")
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
            "uk_vat_threshold_remaining_gbp": max(0, round(self.UK_VAT_THRESHOLD_GBP - self._annual_revenue_gbp, 2)),
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
