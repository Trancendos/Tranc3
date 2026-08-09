# src/monetisation/bridge.py
# Bridge from TierEnforcer's per-process, in-memory usage counters
# (src/monetisation/billing.py) to workers/rate-limit-service/'s durable,
# shared token-bucket policy engine.
#
# check_and_increment() gates essentially every rate/tier-limited request
# platform-wide, so this bridge is built around one hard rule: the worker
# being unreachable must never add latency risk that blocks a request, and
# must never turn into a request being wrongly rejected. Two pieces:
#
# 1. ensure_tier_policies(): idempotently seeds one named rate-limit-service
#    policy per billing tier (see TIERS in billing.py), translating the
#    existing hourly request-count limit into a token-bucket
#    capacity/refill_rate pair (capacity = hourly_limit, refill_rate =
#    hourly_limit / 3600 tokens/sec — continuous refill, a smoother and
#    harder-to-burst algorithm than the in-process TierEnforcer's own
#    fixed-window hourly counter). Called once at startup; a failure here is
#    non-fatal — check_and_increment_durable() falls back to the in-process
#    enforcer either way if the worker never got its policies seeded.
# 2. check_and_increment_durable(): tries the worker's POST /check first —
#    a short, capped-timeout request-scoped await, not fire-and-forget,
#    since the caller needs an actual allow/deny answer — so the limit is
#    enforced consistently across every backend process, not just this one.
#    * Worker reachable, allowed=True  -> also run the local counter (so
#      get_usage() stays meaningful) and allow.
#    * Worker reachable, allowed=False -> deny (HTTP 429). This is the
#      worker doing its job correctly, not a failure — fail-open only
#      covers the worker being unreachable, not a considered "no".
#    * Worker unreachable/errors/times out -> fall straight through to
#      TierEnforcer.check_and_increment() (the pre-existing, purely local
#      behavior) and treat that as authoritative for this request. Explicit
#      product decision, 2026-08-08: fail-open.
#    Unlimited tiers (req_per_hour == -1, e.g. enterprise) skip the remote
#    call entirely — there's nothing to enforce.
#
# Hardening pass (post-implementation, same 2026-08-08 decision): this is the
# highest-request-volume of the four bridges, so a plain "try then timeout"
# would mean every request pays up to _REQUEST_TIMEOUT_SECONDS of dead time
# during a sustained rate-limit-service outage. A src/mesh/ CircuitBreaker
# closes that gap — after a run of consecutive failures it opens and every
# subsequent call skips the network attempt entirely (straight to the local
# fallback, zero added latency) until its reset timeout elapses, then
# self-probes back to closed. No manual re-enable needed.

from __future__ import annotations

import logging
import os
from typing import Dict

from Dimensional.sanitize import sanitize_for_log

from src.mesh.circuit_breaker import CircuitBreaker
from src.mesh.types import CircuitBreakerConfig
from src.monetisation.billing import TIERS, enforcer

logger = logging.getLogger(__name__)

_RATE_LIMIT_URL = os.environ.get("RATE_LIMIT_SERVICE_URL", "http://rate-limit-service:8026")
_RATE_LIMIT_INTERNAL_SECRET = os.environ.get("RATE_LIMIT_SERVICE_INTERNAL_SECRET", "")
_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("RATE_LIMIT_SERVICE_TIMEOUT_SECONDS", "0.5"))

_POLICY_PREFIX = "billing-"

# Opens after 5 consecutive failures, self-probes back to closed after 15s —
# shorter than the mesh default (30s) since this gates live request traffic
# and should recover fast once the worker is back.
_circuit = CircuitBreaker(
    "rate-limit-service", config=CircuitBreakerConfig(failure_threshold=5, reset_timeout_ms=15_000)
)


def _policy_name(tier: str) -> str:
    return f"{_POLICY_PREFIX}{tier}"


def _headers() -> Dict[str, str]:
    return {"X-Internal-Secret": _RATE_LIMIT_INTERNAL_SECRET} if _RATE_LIMIT_INTERNAL_SECRET else {}


async def ensure_tier_policies() -> None:
    """Idempotently seed one rate-limit-service policy per billing tier.

    Best-effort: any failure here (worker down, network error) is logged and
    swallowed — check_and_increment_durable() still works, it just falls
    back to the in-process enforcer on every call until the worker (and its
    policies) become available.
    """
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            for tier, limits in TIERS.items():
                hourly = limits.get("req_per_hour", 100)
                if hourly is None or hourly == -1:
                    continue  # unlimited tier — no policy needed
                try:
                    response = await client.post(
                        f"{_RATE_LIMIT_URL}/policies",
                        json={
                            "name": _policy_name(tier),
                            "capacity": hourly,
                            "refill_rate": max(hourly / 3600.0, 0.001),
                            "description": f"Trancendos billing tier: {tier}",
                        },
                        headers=_headers(),
                    )
                    # 201 = created, 409 = already exists — both fine.
                    if response.status_code not in (201, 409):
                        response.raise_for_status()
                except Exception as exc:
                    logger.debug(
                        "monetisation: policy seed skipped for tier=%s: %s",
                        tier,
                        sanitize_for_log(exc),
                    )  # codeql[py/cleartext-logging]
    except Exception as exc:
        logger.warning(
            "monetisation: rate-limit-service policy seeding unavailable: %s",
            sanitize_for_log(exc),
        )  # codeql[py/cleartext-logging]


async def check_and_increment_durable(user_id: str, tier: str = "free") -> Dict:
    """Fail-open, durable-first tier/rate-limit check.

    Raises ValueError on a genuine "over limit" decision (same contract as
    TierEnforcer.check_and_increment(), so existing call sites' `except
    ValueError` handling needs no change).
    """
    limits = TIERS.get(tier, TIERS["free"])
    hourly = limits.get("req_per_hour", 100)

    if hourly is not None and hourly != -1 and _circuit.can_execute():
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{_RATE_LIMIT_URL}/check",
                    json={"key": f"user:{user_id}", "policy": _policy_name(tier), "tokens": 1},
                    headers=_headers(),
                )
            if response.status_code == 429:
                # The worker made a considered, reachable decision — honor
                # it. This is not the fail-open path; the worker is up and
                # working correctly.
                _circuit.record_success()
                raise ValueError(f"Hourly rate limit exceeded ({hourly} req/hr for {tier})")
            response.raise_for_status()
            _circuit.record_success()
        except ValueError:
            raise
        except Exception as exc:
            # Worker unreachable/erroring/timed out — fail open, fall
            # through to the local in-process check below. Also counts
            # toward the circuit breaker so a sustained outage stops paying
            # the request-timeout cost on every single call.
            _circuit.record_failure()
            logger.debug(
                "monetisation: durable rate-limit check skipped for user=%s tier=%s: %s",
                sanitize_for_log(user_id),
                tier,
                sanitize_for_log(exc),
            )  # codeql[py/cleartext-logging]

    # Always run the local counter too — this is what get_usage() reads,
    # and it's the sole source of truth whenever the worker was skipped or
    # unreachable above.
    return enforcer.check_and_increment(user_id, tier)
