"""Runtime security checks and free-tier provider health monitoring."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# CVE-2025-69872: diskcache allows arbitrary code execution when cache dir is
# world-writable and the process runs as root. Hard-stop if both conditions hold.
def check_diskcache_cve_2025_69872() -> None:
    """Abort if running as root — diskcache CVE-2025-69872 mitigation."""
    if hasattr(os, "getuid") and os.getuid() == 0:
        logger.critical(
            "CVE-2025-69872: diskcache is unsafe when running as root. "
            "Restart the service as a non-privileged user."
        )
        sys.exit(1)


FREE_PROVIDERS: list[dict] = [
    {"name": "ollama", "url": "http://localhost:11434/api/tags", "daily_limit": None},
    {
        "name": "huggingface",
        "url": "https://api-inference.huggingface.co/status",
        "daily_limit": 30_000,
    },
    {"name": "openrouter", "url": "https://openrouter.ai/api/v1/models", "daily_limit": 50},
    {"name": "together_free", "url": "https://api.together.xyz/v1/models", "daily_limit": 60},
    {"name": "groq_free", "url": "https://api.groq.com/openai/v1/models", "daily_limit": 14_400},
    {"name": "mistral_free", "url": "https://api.mistral.ai/v1/models", "daily_limit": 1_000},
    {"name": "cohere_trial", "url": "https://api.cohere.ai/v1/check-api-key", "daily_limit": 100},
    {
        "name": "cf_ai_workers",
        "url": "https://api.cloudflare.com/client/v4/accounts/me",
        "daily_limit": 10_000,
    },
]

_USAGE_FILE = Path(os.getenv("PROVIDER_USAGE_FILE", "/data/tranc3_provider_usage.json"))
_USAGE_THRESHOLD = 0.80  # hard stop at 80 %


@dataclass
class ProviderStatus:
    """Snapshot of a single free-tier provider."""

    name: str
    healthy: bool
    usage_count: int = 0
    daily_limit: Optional[int] = None
    usage_pct: float = 0.0
    throttled: bool = False


@dataclass
class ProviderHealthReport:
    """Aggregated health across all free-tier providers."""

    timestamp: float = field(default_factory=time.time)
    providers: list[ProviderStatus] = field(default_factory=list)
    active_provider: Optional[str] = None


def _load_usage() -> dict[str, int]:
    """Return persisted per-provider usage counters, resetting if day has rolled over."""
    try:
        if _USAGE_FILE.exists():
            data = json.loads(_USAGE_FILE.read_text())
            stored_day = data.get("_day")
            today = time.strftime("%Y-%m-%d")
            if stored_day == today:
                return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception:  # noqa: BLE001 — missing/corrupt usage file, start fresh
        pass
    return {}


def _save_usage(usage: dict[str, int]) -> None:
    try:
        payload = dict(usage)
        payload["_day"] = time.strftime("%Y-%m-%d")
        _USAGE_FILE.write_text(json.dumps(payload))
    except Exception:  # noqa: BLE001 — write failure is non-fatal
        pass


def _probe_provider(url: str, timeout: float = 2.0) -> bool:
    """Return True if provider endpoint responds (2xx or auth challenge means alive)."""
    import urllib.error
    import urllib.request

    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            logger.warning("_probe_provider: rejecting non-http(s) URL scheme: %s", parsed.scheme)
            return False
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "tranc3-health-check/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — scheme validated above
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        # 401/403 means the service is alive but requires auth — treat as healthy.
        return exc.code in (401, 403)
    except Exception:
        return False


def get_provider_health() -> ProviderHealthReport:
    """Probe all free-tier providers, respect 80 % usage threshold, return report."""
    usage = _load_usage()
    report = ProviderHealthReport()

    for provider in FREE_PROVIDERS:
        name = provider["name"]
        daily_limit: Optional[int] = provider["daily_limit"]
        count = usage.get(name, 0)

        if daily_limit is not None:
            pct = count / daily_limit
            throttled = pct >= _USAGE_THRESHOLD
        else:
            pct = 0.0
            throttled = False

        healthy = (not throttled) and _probe_provider(provider["url"])

        status = ProviderStatus(
            name=name,
            healthy=healthy,
            usage_count=count,
            daily_limit=daily_limit,
            usage_pct=round(pct, 4),
            throttled=throttled,
        )
        report.providers.append(status)

        if healthy and report.active_provider is None:
            report.active_provider = name

    return report


def rotate_provider(report: ProviderHealthReport) -> Optional[str]:
    """Return the next healthy provider name, or None if all are exhausted."""
    for status in report.providers:
        if status.healthy:
            return status.name
    logger.warning("All free-tier providers are unavailable or over threshold.")
    return None


def increment_usage(provider_name: str) -> None:
    """Record one request against the named provider's daily counter."""
    usage = _load_usage()
    usage[provider_name] = usage.get(provider_name, 0) + 1
    _save_usage(usage)


def check_non_root() -> bool:
    """CVE-2025-69872 mitigation: assert process is not running as root (UID 0)."""
    uid = os.getuid() if hasattr(os, "getuid") else -1
    if uid == 0:
        logger.critical(
            "SECURITY: Process running as root (UID 0). "
            "CVE-2025-69872 (diskcache local DoS) is exploitable. "
            "Restart as non-root user (e.g. tranc3:tranc3)."
        )
        return False
    return True


def run_startup_checks() -> None:
    """Run all startup security checks. Logs warnings; never raises."""
    non_root = check_non_root()
    if not non_root:
        logger.warning("Security degraded: running as root violates zero-trust policy")

    report = get_provider_health()
    active = report.active_provider or "offline-stub"
    healthy_count = sum(1 for p in report.providers if p.healthy)
    logger.info(
        "Provider health: %d/%d healthy, active=%s",
        healthy_count,
        len(report.providers),
        active,
    )
    if healthy_count == 0:
        logger.warning("All AI providers degraded — falling back to offline stub")
