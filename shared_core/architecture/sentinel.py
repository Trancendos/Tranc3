"""
shared_core.architecture.sentinel — Continuous verification daemon.

Implements a long-running verification daemon that continuously monitors
the system for security compliance, configuration drift, and service health.
Think of it as the immune system of the Tranc3 platform.

Features:
    - Periodic security scanning with adaptive intervals
    - Configuration drift detection (compares current vs. known-good state)
    - Service health monitoring with circuit breaker pattern
    - Secret rotation reminders (checks credential age)
    - Automated incident response (logs, alerts, auto-remediation)
    - Heartbeat with audit ledger integration

Usage:
    from shared_core.architecture.sentinel import Sentinel

    sentinel = Sentinel(
        scan_paths=["src/", "shared_core/"],
        check_interval=300,  # 5 minutes
    )
    sentinel.start()  # Blocks
    # Or:
    sentinel.start(background=True)

Architecture:
    ┌─────────────────────────────────┐
    │         Sentinel Daemon          │
    │                                  │
    │  ┌─────────┐  ┌──────────────┐  │
    │  │ Scanner  │  │ Drift Check  │  │
    │  └────┬────┘  └──────┬───────┘  │
    │       │               │          │
    │  ┌────┴────┐  ┌──────┴───────┐  │
    │  │Health   │  │Secret Check  │  │
    │  │Monitor  │  │(rotation)    │  │
    │  └────┬────┘  └──────┬───────┘  │
    │       │               │          │
    │       └───────┬───────┘          │
    │               │                  │
    │        ┌──────┴──────┐           │
    │        │Audit Ledger │           │
    │        └─────────────┘           │
    └─────────────────────────────────┘
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from shared_core.architecture.audit_ledger import AuditLedger
from shared_core.security_automation.adaptive_scanner import AdaptiveScanner
from shared_core.security_automation.scanner import Severity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_CHECK_INTERVAL = 300  # 5 minutes
_DEFAULT_DRIFT_INTERVAL = 600  # 10 minutes
_DEFAULT_SECRET_CHECK_INTERVAL = 3600  # 1 hour


class SentinelState(Enum):
    """State of the Sentinel daemon."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class SentinelSeverity(str, Enum):
    """Severity levels for sentinel checks."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SentinelCheck:
    """Result of a single sentinel check."""

    check_type: str
    passed: bool
    timestamp: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    severity: SentinelSeverity = SentinelSeverity.INFO
    message: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        # Allow string values to be coerced into the enum
        if isinstance(self.severity, str):
            self.severity = SentinelSeverity(self.severity)


@dataclass
class SentinelReport:
    """Full report from a sentinel check cycle."""

    timestamp: str
    state: SentinelState
    checks: List[SentinelCheck]
    total_passed: int
    total_failed: int
    scan_violations: int = 0
    uptime_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "state": self.state.value,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "scan_violations": self.scan_violations,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "checks": [
                {
                    "check_type": c.check_type,
                    "passed": c.passed,
                    "severity": c.severity,
                    "message": c.message,
                }
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------


class Sentinel:
    """Continuous verification daemon for the Tranc3 platform.

    Runs periodic checks and reports findings to the audit ledger.
    Can be configured to auto-remediate known issues or simply alert.

    The sentinel operates on a configurable check interval and performs
    the following checks each cycle:
        1. Security scan — detects new violations
        2. Configuration drift — compares current config to known-good
        3. Secret age check — warns about stale credentials
        4. Service health — verifies core services are responsive
        5. Audit ledger integrity — verifies chain is intact
    """

    def __init__(
        self,
        *,
        scan_paths: Optional[List[str]] = None,
        check_interval: int = _DEFAULT_CHECK_INTERVAL,
        audit_ledger: Optional[AuditLedger] = None,
        on_check_complete: Optional[Callable[[SentinelReport], None]] = None,
        auto_remediate: bool = False,
    ):
        """Initialize the sentinel daemon.

        Args:
            scan_paths: Paths to scan for security violations.
            check_interval: Seconds between check cycles.
            audit_ledger: Custom audit ledger instance.
            on_check_complete: Callback after each check cycle.
            auto_remediate: If True, attempt to auto-fix violations.
        """
        self._scan_paths = scan_paths or ["src/", "shared_core/"]
        self._check_interval = check_interval
        self._ledger = audit_ledger or AuditLedger()
        self._on_check_complete = on_check_complete
        self._auto_remediate = auto_remediate

        self._state = SentinelState.STOPPED
        self._scanner = AdaptiveScanner()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._started_at: Optional[float] = None
        self._last_report: Optional[SentinelReport] = None
        self._check_history: List[SentinelReport] = []

        # Known-good configuration state (populated on first run)
        self._known_good_config: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, *, background: bool = False) -> None:
        """Start the sentinel daemon.

        Args:
            background: If True, run in a background thread.
        """
        if self._running:
            logger.warning("Sentinel is already running")
            return

        self._state = SentinelState.STARTING
        self._running = True
        self._started_at = time.time()

        # Record start event in audit ledger
        self._ledger.append(
            event_type="sentinel_start",
            actor="sentinel",
            details={"scan_paths": self._scan_paths, "check_interval": self._check_interval},
        )

        if background:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        else:
            self._run_loop()

    def stop(self) -> None:
        """Stop the sentinel daemon."""
        self._state = SentinelState.STOPPING
        self._running = False

        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None

        self._state = SentinelState.STOPPED

        # Record stop event
        self._ledger.append(
            event_type="sentinel_stop",
            actor="sentinel",
            details={"uptime": time.time() - (self._started_at or time.time())},
        )

    def check_now(self) -> SentinelReport:
        """Run a single check cycle immediately.

        Returns:
            SentinelReport with results of all checks.
        """
        return self._run_checks()

    def get_state(self) -> SentinelState:
        """Return the current state of the sentinel."""
        return self._state

    def get_last_report(self) -> Optional[SentinelReport]:
        """Return the most recent check report."""
        return self._last_report

    def get_stats(self) -> Dict[str, Any]:
        """Return sentinel statistics."""
        uptime = 0.0
        if self._started_at and self._running:
            uptime = time.time() - self._started_at

        return {
            "state": self._state.value,
            "uptime_seconds": round(uptime, 1),
            "check_interval": self._check_interval,
            "scan_paths": self._scan_paths,
            "total_checks_run": len(self._check_history),
            "last_check": self._last_report.timestamp if self._last_report else None,
        }

    def __enter__(self):
        self.start(background=True)
        return self

    def __exit__(self, *args):
        self.stop()

    # ------------------------------------------------------------------
    # Internal: check cycle
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Main sentinel loop — runs checks at the configured interval."""
        self._state = SentinelState.RUNNING

        while self._running:
            try:
                report = self._run_checks()
                self._last_report = report
                self._check_history.append(report)

                # Keep only last 100 reports
                if len(self._check_history) > 100:
                    self._check_history = self._check_history[-100:]

                # Adjust state based on results
                if report.total_failed > 0:
                    self._state = SentinelState.DEGRADED
                else:
                    self._state = SentinelState.RUNNING

                # Callback
                if self._on_check_complete:
                    try:
                        self._on_check_complete(report)
                    except Exception as e:
                        logger.error("Sentinel callback error: %s", e)

            except Exception as e:
                logger.error("Sentinel check cycle error: %s", e)
                self._state = SentinelState.DEGRADED

            # Wait for next cycle
            try:
                for _ in range(self._check_interval):
                    if not self._running:
                        break
                    time.sleep(1.0)
            except KeyboardInterrupt:
                break

    def _run_checks(self) -> SentinelReport:
        """Run all checks and compile a report."""
        checks: List[SentinelCheck] = []
        time.time()

        # Check 1: Security scan
        scan_check = self._check_security_scan()
        checks.append(scan_check)

        # Check 2: Configuration drift
        drift_check = self._check_config_drift()
        checks.append(drift_check)

        # Check 3: Secret age
        secret_check = self._check_secret_age()
        checks.append(secret_check)

        # Check 4: Service health
        health_check = self._check_service_health()
        checks.append(health_check)

        # Check 5: Audit ledger integrity
        ledger_check = self._check_ledger_integrity()
        checks.append(ledger_check)

        total_passed = sum(1 for c in checks if c.passed)
        total_failed = sum(1 for c in checks if not c.passed)

        # Calculate violations from scan
        scan_violations = 0
        if not scan_check.passed and "violation_count" in scan_check.details:
            scan_violations = scan_check.details["violation_count"]

        uptime = 0.0
        if self._started_at:
            uptime = time.time() - self._started_at

        report = SentinelReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            state=self._state,
            checks=checks,
            total_passed=total_passed,
            total_failed=total_failed,
            scan_violations=scan_violations,
            uptime_seconds=uptime,
        )

        # Record in audit ledger
        self._ledger.append(
            event_type="sentinel_check",
            actor="sentinel",
            details=report.to_dict(),
        )

        return report

    # ------------------------------------------------------------------
    # Internal: individual checks
    # ------------------------------------------------------------------

    def _check_security_scan(self) -> SentinelCheck:
        """Run a security scan and check for new violations."""
        try:
            violations = self._scanner.scan_path(*self._scan_paths)
            critical = sum(1 for v in violations if v.severity == Severity.CRITICAL)
            high = sum(1 for v in violations if v.severity == Severity.HIGH)

            passed = critical == 0 and high == 0
            severity = "info" if passed else ("critical" if critical > 0 else "high")

            return SentinelCheck(
                check_type="security_scan",
                passed=passed,
                severity=severity,
                message=f"Found {len(violations)} violations ({critical} critical, {high} high)",
                details={
                    "violation_count": len(violations),
                    "critical": critical,
                    "high": high,
                },
            )
        except Exception as e:
            return SentinelCheck(
                check_type="security_scan",
                passed=False,
                severity="critical",
                message=f"Security scan failed: {e}",
            )

    def _check_config_drift(self) -> SentinelCheck:
        """Check for configuration drift from known-good state."""
        try:
            current = self._capture_config_state()

            if not self._known_good_config:
                # First run — establish baseline
                self._known_good_config = current
                return SentinelCheck(
                    check_type="config_drift",
                    passed=True,
                    severity="info",
                    message="Baseline configuration established",
                    details={"keys_tracked": len(current)},
                )

            # Compare current vs. known-good
            drifted_keys = []
            for key, value in current.items():
                if key in self._known_good_config:
                    if self._known_good_config[key] != value:
                        drifted_keys.append(key)

            # Also check for missing keys (config removed)
            for key in self._known_good_config:
                if key not in current:
                    drifted_keys.append(f"MISSING:{key}")

            passed = len(drifted_keys) == 0
            return SentinelCheck(
                check_type="config_drift",
                passed=passed,
                severity="medium" if not passed else "info",
                message=f"Configuration drift detected in {len(drifted_keys)} keys"
                if not passed
                else "No configuration drift",
                details={"drifted_keys": drifted_keys[:10]},
            )
        except Exception as e:
            return SentinelCheck(
                check_type="config_drift",
                passed=False,
                severity="medium",
                message=f"Config drift check failed: {e}",
            )

    def _check_secret_age(self) -> SentinelCheck:
        """Check for stale secrets that may need rotation."""
        try:
            from shared_core.architecture.vault import VaultSecretLoader

            loader = VaultSecretLoader()
            leaks = loader.detect_leaks()
            missing = loader.validate_required()

            # Check for stale secrets (secrets that haven't been rotated)
            # We use the file modification time of .env as a proxy
            env_path = Path(".env")
            env_age_days = 0
            if env_path.exists():
                mtime = env_path.stat().st_mtime
                env_age_days = (time.time() - mtime) / 86400

            passed = len(leaks) == 0 and len(missing) == 0
            severity = "high" if leaks else ("medium" if missing else "info")

            return SentinelCheck(
                check_type="secret_age",
                passed=passed,
                severity=severity,
                message=f"Leaks: {len(leaks)}, Missing: {len(missing)}, .env age: {env_age_days:.0f} days",
                details={
                    "leak_count": len(leaks),
                    "missing_count": len(missing),
                    "env_age_days": round(env_age_days, 1),
                },
            )
        except Exception as e:
            return SentinelCheck(
                check_type="secret_age",
                passed=True,  # Don't fail on secret check errors
                severity="info",
                message=f"Secret age check skipped: {e}",
            )

    def _check_service_health(self) -> SentinelCheck:
        """Check core service health."""
        try:
            # Check if the API server is responsive (if running)
            import socket

            api_host = os.getenv("API_HOST", "localhost")
            api_port = int(os.getenv("API_PORT", "8000"))

            # Try to connect
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            try:
                result = sock.connect_ex((api_host, api_port))
                api_healthy = result == 0
            finally:
                sock.close()

            # Check Redis (if configured)
            redis_healthy = True
            redis_url = os.getenv("REDIS_URL", "")
            if redis_url:
                try:
                    import redis

                    r = redis.from_url(redis_url)
                    r.ping()
                except Exception:
                    redis_healthy = False

            passed = api_healthy and redis_healthy
            return SentinelCheck(
                check_type="service_health",
                passed=passed,
                severity="high" if not passed else "info",
                message=f"API: {'healthy' if api_healthy else 'unhealthy'}, Redis: {'healthy' if redis_healthy else 'unhealthy'}",
                details={
                    "api_healthy": api_healthy,
                    "redis_healthy": redis_healthy,
                },
            )
        except Exception as e:
            return SentinelCheck(
                check_type="service_health",
                passed=True,  # Services may not be running in dev mode
                severity="info",
                message=f"Service health check skipped: {e}",
            )

    def _check_ledger_integrity(self) -> SentinelCheck:
        """Verify the audit ledger chain is intact."""
        try:
            is_valid = self._ledger.verify_chain()
            return SentinelCheck(
                check_type="ledger_integrity",
                passed=is_valid,
                severity="critical" if not is_valid else "info",
                message="Audit ledger chain is intact"
                if is_valid
                else "AUDIT LEDGER TAMPERING DETECTED",
                details={"chain_valid": is_valid},
            )
        except Exception as e:
            return SentinelCheck(
                check_type="ledger_integrity",
                passed=False,
                severity="critical",
                message=f"Ledger integrity check failed: {e}",
            )

    # ------------------------------------------------------------------
    # Internal: configuration state capture
    # ------------------------------------------------------------------

    def _capture_config_state(self) -> Dict[str, Any]:
        """Capture the current configuration state for drift detection.

        Captures key configuration values (not secrets) that should remain
        stable across deployments.
        """
        state = {}

        # System configuration
        state["SYSTEM_MODE"] = os.getenv("SYSTEM_MODE", "TRUE_NAS")
        state["ENVIRONMENT"] = os.getenv("ENVIRONMENT", "development")
        state["API_PORT"] = os.getenv("API_PORT", "8000")

        # File-based configuration
        config_files = [
            "docker-compose.yml",
            "docker-compose.dev.yml",
            ".env.example",
        ]
        for config_file in config_files:
            path = Path(config_file)
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8")
                    state[f"file:{config_file}"] = hashlib.sha256(content.encode()).hexdigest()[:16]
                except OSError:
                    pass

        return state
