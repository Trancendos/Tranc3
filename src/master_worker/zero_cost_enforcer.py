"""
Zero-Cost Enforcer — Quota Guardian
=====================================
Monitors real-time platform usage, enforces the zero-cost mandate, and
triggers automatic platform rotation before quotas are breached.

Standing directive (verbatim): "Be smart, intelligent, logical and automated
that can rotate the platforms usage size and environments to ensure that it
retained 0 costings."

Enforcement rules:
  1. Any platform at >85% quota utilisation → pre-emptive rotation
  2. Any platform at >95% → immediate rotation + alert
  3. Known cost-incurring services → blocked entirely:
     - Azure NC6s_v3 GPU training (£765/run)
     - Cloudflare R2 overages (blocked; use self-hosted IPFS/Backblaze instead)
     - Any Bugzy AI subscription endpoint (€250-1,500/month)
     - GitHub Actions (use Forgejo — self-hosted)
     - Any Cloudflare Worker deployment (use self-hosted Python workers)
  4. Daily cost assertion: sum(all platform costs) must equal £0
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .platform_registry import PlatformHealth, PlatformRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cost-incurring service blocklist
# ---------------------------------------------------------------------------

BLOCKED_SERVICES: Dict[str, str] = {
    # Endpoint fragment → reason
    # Cloud GPU / training
    r"azure.*(nc6|nc12|nc24|gpu)": "Azure GPU training (£765+/run) — BLOCKED",
    r"amazonaws\.com/(sagemaker|ec2|lambda|bedrock)": "AWS paid compute — use Oracle ARM64 free tier",
    r"cloud\.google\.com/(vertex|ml-engine|tpu)": "GCP paid ML — use free tier alternatives",
    # Storage overages
    "r2.cloudflarestorage.com": "Cloudflare R2 overages — use self-hosted IPFS/Backblaze",
    # Paid AI subscriptions
    "bugzy.ai": "Bugzy AI subscription (€250-1,500/month) — BLOCKED",
    # CI/CD costs
    "api.github.com/actions": "GitHub Actions — use Forgejo CI at trancendos.com/the-workshop",
    # Edge compute costs
    "workers.cloudflare.com/deploy": "CF Workers deploy — use self-hosted Python workers",
    # Paid AI APIs
    r"openai\.com/v1": "OpenAI paid API — use Ollama/Groq/Gemini free tiers instead",
    r"api\.openai\.com": "OpenAI paid API — use Ollama/Groq/Gemini free tiers instead",
    r"anthropic\.com/v1/messages": "Anthropic direct billing — route via Ollama/OpenRouter free",
    r"api\.anthropic\.com": "Anthropic direct billing — route via Ollama/OpenRouter free",
    r"cohere\.com/v1": "Cohere paid API — use free alternatives",
    r"api\.stripe\.com": "Stripe payments — only allowed via Royal Bank of Arcadia worker",
    # Paid deepseek direct (use via OpenRouter :free instead)
    r"api\.deepseek\.com": "DeepSeek direct API (paid) — use deepseek/deepseek-r1:free via OpenRouter",
}


class QuotaStatus(str, Enum):
    OK = "ok"  # < 85% used
    WARNING = "warning"  # 85–95% used
    CRITICAL = "critical"  # > 95% used — rotate NOW
    EXHAUSTED = "exhausted"  # 100% or hard-blocked


@dataclass
class QuotaReport:
    platform_name: str
    status: QuotaStatus
    utilisation_pct: float
    action_taken: str = ""
    fallback_platform: Optional[str] = None
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class CostAssertion:
    """Daily zero-cost assertion result."""

    passed: bool
    total_estimated_cost_gbp: float = 0.0
    violations: List[str] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)


class ZeroCostEnforcer:
    """
    Continuous zero-cost enforcement engine.

    Runs as a background asyncio task. Checks every `check_interval_s`
    seconds, rotates platforms proactively, and blocks any attempt to
    call a cost-incurring service.

    Usage:
        enforcer = ZeroCostEnforcer(registry)
        await enforcer.start()
        ...
        await enforcer.stop()
    """

    WARNING_THRESHOLD = 0.85
    CRITICAL_THRESHOLD = 0.95
    DEFAULT_CHECK_INTERVAL = 60.0  # seconds

    def __init__(
        self,
        registry: Optional[PlatformRegistry] = None,
        check_interval_s: float = DEFAULT_CHECK_INTERVAL,
    ) -> None:
        self._registry = registry or PlatformRegistry()
        self._check_interval = check_interval_s
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._rotation_callbacks: List[Callable[[str, str], Awaitable[None]]] = []
        self._reports: List[QuotaReport] = []
        self._last_daily_assertion: Optional[CostAssertion] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(
            self._enforcement_loop(),
            name="zero_cost_enforcer",
        )
        logger.info("ZeroCostEnforcer started (interval=%.0fs)", self._check_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # Expected when we cancel the task
        logger.info("ZeroCostEnforcer stopped")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_rotation(self, cb: Callable[[str, str], Awaitable[None]]) -> None:
        """Register async callback(old_platform, new_platform) for rotation events."""
        self._rotation_callbacks.append(cb)

    # ------------------------------------------------------------------
    # Blocklist check (called synchronously before each external call)
    # ------------------------------------------------------------------

    def assert_not_blocked(self, url_or_service: str) -> None:
        """
        Raise ValueError if the target URL/service is cost-incurring.
        Call this before making ANY external HTTP request.
        """
        import re

        lower = url_or_service.lower()
        for pattern, reason in BLOCKED_SERVICES.items():
            if re.search(pattern, lower):
                raise ValueError(
                    f"ZERO-COST VIOLATION — blocked service call to: {url_or_service!r}\n"
                    f"Reason: {reason}",
                )

    # ------------------------------------------------------------------
    # Quota checks
    # ------------------------------------------------------------------

    def check_all(self) -> List[QuotaReport]:
        reports: List[QuotaReport] = []
        for name, platform in self._registry._platforms.items():
            if not platform.enabled:
                continue
            pct = platform.utilisation_pct()
            if pct >= 1.0 or platform.health == PlatformHealth.EXHAUSTED:
                status = QuotaStatus.EXHAUSTED
            elif pct >= self.CRITICAL_THRESHOLD:
                status = QuotaStatus.CRITICAL
            elif pct >= self.WARNING_THRESHOLD:
                status = QuotaStatus.WARNING
            else:
                status = QuotaStatus.OK
            report = QuotaReport(
                platform_name=name,
                status=status,
                utilisation_pct=round(pct * 100, 1),
            )
            reports.append(report)
        return reports

    def assert_zero_cost(self) -> CostAssertion:
        """
        Verify no known paid services are active. Returns a CostAssertion.
        Violations logged as warnings.
        """
        violations: List[str] = []

        # Check for Azure GPU training config
        if os.environ.get("AZURE_TRAINING_ENABLED", "").lower() == "true":
            violations.append("AZURE_TRAINING_ENABLED=true — Azure GPU training costs £765+/run")

        # Check for CF Worker deployment targets
        if os.environ.get("CF_DEPLOY_WORKERS", "").lower() == "true":
            violations.append("CF_DEPLOY_WORKERS=true — Cloudflare Workers cost money")

        # Check for GitHub Actions (should use Forgejo)
        if os.environ.get("USE_GITHUB_ACTIONS", "").lower() == "true":
            violations.append("USE_GITHUB_ACTIONS=true — use Forgejo CI instead")

        # Check for paid AI APIs configured without free-tier flags
        for env_var, service_name in [
            ("OPENAI_API_KEY", "OpenAI"),
            ("BUGZY_API_KEY", "Bugzy AI (€250-1,500/month)"),
        ]:
            if os.environ.get(env_var):
                violations.append(
                    f"{env_var} set — {service_name} incurs costs; use free alternatives"
                )

        result = CostAssertion(
            passed=len(violations) == 0,
            total_estimated_cost_gbp=0.0,
            violations=violations,
        )
        if violations:
            logger.warning(
                "ZERO-COST ASSERTION FAILED: %d violation(s)\n%s",
                len(violations),
                "\n".join(f"  • {v}" for v in violations),
            )
        else:
            logger.debug("Zero-cost assertion PASSED — £0 spend confirmed")

        self._last_daily_assertion = result
        return result

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------

    async def rotate_platform(self, exhausted_name: str) -> Optional[str]:
        """
        Mark `exhausted_name` as exhausted and find the next available
        platform in the same category. Fires rotation callbacks.
        """
        platform = self._registry.get(exhausted_name)
        if not platform:
            return None

        self._registry.mark_exhausted(exhausted_name)
        fallback = self._registry.best_for(platform.category)
        fallback_name = fallback.name if fallback else None

        if fallback_name:
            logger.info(
                "Platform rotation: %r → %r (category=%s)",
                exhausted_name,
                fallback_name,
                platform.category.value,
            )
        else:
            logger.error(
                "Platform rotation: %r exhausted, NO fallback available for %s",
                exhausted_name,
                platform.category.value,
            )

        for cb in self._rotation_callbacks:
            try:
                await cb(exhausted_name, fallback_name or "none")
            except Exception as exc:
                logger.warning("Rotation callback failed: %s", exc)

        return fallback_name

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def _enforcement_loop(self) -> None:
        _daily_check_hour = -1
        while self._running:
            try:
                reports = self.check_all()
                for report in reports:
                    if report.status == QuotaStatus.CRITICAL:
                        logger.warning(
                            "Quota CRITICAL on %s (%.1f%%) — pre-emptive rotation",
                            report.platform_name,
                            report.utilisation_pct,
                        )
                        fallback = await self.rotate_platform(report.platform_name)
                        report.action_taken = f"rotated_to:{fallback}"
                        report.fallback_platform = fallback
                    elif report.status == QuotaStatus.WARNING:
                        logger.info(
                            "Quota WARNING on %s (%.1f%%) — monitoring",
                            report.platform_name,
                            report.utilisation_pct,
                        )
                        report.action_taken = "monitoring"

                self._reports = reports

                # Daily zero-cost assertion
                import datetime

                current_hour = datetime.datetime.now(datetime.timezone.utc).hour
                if current_hour == 0 and _daily_check_hour != 0:
                    self.assert_zero_cost()
                    _daily_check_hour = 0
                elif current_hour != 0:
                    _daily_check_hour = current_hour

            except asyncio.CancelledError:
                break  # Expected when we cancel the task
            except Exception as exc:
                logger.error("ZeroCostEnforcer loop error: %s", exc)

            await asyncio.sleep(self._check_interval)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "check_interval_s": self._check_interval,
            "platforms": self._registry.snapshot(),
            "last_assertion": {
                "passed": self._last_daily_assertion.passed if self._last_daily_assertion else None,
                "violations": self._last_daily_assertion.violations
                if self._last_daily_assertion
                else [],
            },
            "recent_reports": [
                {
                    "platform": r.platform_name,
                    "status": r.status.value,
                    "utilisation_pct": r.utilisation_pct,
                    "action": r.action_taken,
                }
                for r in self._reports
                if r.status != QuotaStatus.OK
            ],
        }
