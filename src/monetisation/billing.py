# src/monetisation/billing.py
# TRANC3 Billing, Tier Enforcement & Stripe Integration

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Tuple

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BILLING TIER ENUM
# ---------------------------------------------------------------------------


class BillingTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


def check_rate_limit(
    user_id: str,
    tier: "BillingTier",
    request_count: int,
) -> Tuple[bool, Optional[str]]:
    """
    Check whether request_count exceeds the hourly rate limit for the given tier.
    Returns (allowed: bool, error_message: str | None).
    """
    tier_key = tier.value if isinstance(tier, BillingTier) else str(tier)
    limits = TIERS.get(tier_key, TIERS["free"])
    hourly = limits.get("req_per_hour", 100)

    if hourly != -1 and request_count > hourly:
        return (
            False,
            f"Hourly rate limit exceeded ({request_count} > {hourly} req/hr for {tier_key} tier)",
        )
    return True, None


# ---------------------------------------------------------------------------
# TIER DEFINITIONS
# ---------------------------------------------------------------------------
TIERS: Dict[str, Dict] = {
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
        "stripe_price_id": os.getenv("STRIPE_PRO_PRICE_ID", "price_pro_placeholder"),
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
        "stripe_price_id": os.getenv("STRIPE_BUSINESS_PRICE_ID", "price_business_placeholder"),
    },
    "enterprise": {
        "price_gbp": None,  # Custom
        "req_per_hour": -1,  # Unlimited
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
    },
}


@dataclass
class UsageRecord:
    user_id: str
    tier: str
    requests_this_hour: int = 0
    requests_today: int = 0
    tokens_this_month: int = 0
    hour_window_start: datetime = None
    day_window_start: datetime = None

    def __post_init__(self):
        now = datetime.utcnow()
        if self.hour_window_start is None:
            self.hour_window_start = now.replace(minute=0, second=0, microsecond=0)
        if self.day_window_start is None:
            self.day_window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)


class TierEnforcer:
    """
    Enforce rate limits and feature access per tier.
    Uses in-memory tracking (swap for Redis in production).
    """

    def __init__(self):
        self._usage: Dict[str, UsageRecord] = {}

    def _get_or_create(self, user_id: str, tier: str) -> UsageRecord:
        if user_id not in self._usage:
            self._usage[user_id] = UsageRecord(user_id=user_id, tier=tier)
        return self._usage[user_id]

    def _reset_windows_if_needed(self, record: UsageRecord):
        now = datetime.utcnow()
        if now - record.hour_window_start >= timedelta(hours=1):
            record.requests_this_hour = 0
            record.hour_window_start = now.replace(minute=0, second=0, microsecond=0)
        if now - record.day_window_start >= timedelta(days=1):
            record.requests_today = 0
            record.day_window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def check_and_increment(self, user_id: str, tier: str = "free") -> Dict:
        """Check limits and increment counters. Raises ValueError if exceeded."""
        limits = TIERS.get(tier, TIERS["free"])
        record = self._get_or_create(user_id, tier)
        self._reset_windows_if_needed(record)

        hourly_limit = limits["req_per_hour"]
        daily_limit = limits["req_per_day"]

        if hourly_limit != -1 and record.requests_this_hour >= hourly_limit:
            raise ValueError(f"Hourly rate limit exceeded ({hourly_limit} req/hr for {tier} tier)")

        if daily_limit != -1 and record.requests_today >= daily_limit:
            raise ValueError(f"Daily rate limit exceeded ({daily_limit} req/day for {tier} tier)")

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
        limits = TIERS.get(tier, TIERS["free"])
        return bool(limits.get(feature, False))

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


class StripeManager:
    """
    Stripe integration for subscription management.
    Requires STRIPE_SECRET_KEY env var.
    """

    def __init__(self):
        self._stripe_key = os.getenv("STRIPE_SECRET_KEY")
        self._enabled = bool(self._stripe_key)
        if self._enabled:
            try:
                import stripe

                stripe.api_key = self._stripe_key
                self._stripe = stripe
                logger.info("Stripe integration enabled")
            except ImportError:
                logger.warning("stripe package not installed")
                self._enabled = False
        else:
            logger.info("Stripe not configured — running in free-only mode")

    def create_checkout_session(
        self,
        user_id: str,
        tier: str,
        success_url: str,
        cancel_url: str,
    ) -> Optional[str]:
        """Create a Stripe checkout session. Returns checkout URL."""
        if not self._enabled:
            return None
        price_id = TIERS.get(tier, {}).get("stripe_price_id")
        if not price_id:
            return None
        try:
            session = self._stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={"user_id": user_id, "tier": tier},
            )
            return session.url
        except Exception as e:
            logger.error("Stripe checkout error: %s", sanitize_for_log(e))
            return None

    def get_subscription_tier(self, stripe_customer_id: str) -> str:
        """Look up active subscription tier for a customer."""
        if not self._enabled:
            return "free"
        try:
            subs = self._stripe.Subscription.list(
                customer=stripe_customer_id,
                status="active",
                limit=1,
            )
            if not subs.data:
                return "free"
            price_id = subs.data[0]["items"]["data"][0]["price"]["id"]
            for tier, config in TIERS.items():
                if config.get("stripe_price_id") == price_id:
                    return tier
            return "free"
        except Exception as e:
            logger.error("Stripe lookup error: %s", sanitize_for_log(e))
            return "free"

    def cancel_subscription(self, stripe_subscription_id: str) -> bool:
        if not self._enabled:
            return False
        try:
            self._stripe.Subscription.cancel(stripe_subscription_id)
            return True
        except Exception as e:
            logger.error("Stripe cancel error: %s", sanitize_for_log(e))
            return False


class PassiveRevenueTracker:
    """
    Track and report on passive revenue streams.
    """

    STREAMS = [
        "api_subscriptions",
        "personality_packs",
        "language_packs",
        "affiliate_commissions",
        "marketplace_revenue",
        "data_insights",
        "certification_fees",
        "white_label_licenses",
    ]

    def __init__(self):
        self._revenue: Dict[str, float] = dict.fromkeys(self.STREAMS, 0.0)

    def record(self, stream: str, amount_gbp: float):
        if stream in self._revenue:
            self._revenue[stream] += amount_gbp
            logger.info(
                "Revenue recorded: %s +£%s",
                sanitize_for_log(stream),
                sanitize_for_log(f"{amount_gbp:.2f}"),
            )

    def summary(self) -> Dict:
        total = sum(self._revenue.values())
        return {
            "streams": self._revenue,
            "total_gbp": round(total, 2),
            "monthly_run_rate": round(total, 2),
        }


# Singletons
enforcer = TierEnforcer()
stripe_manager = StripeManager()
revenue_tracker = PassiveRevenueTracker()
