# shared_core/orchestration/config_drift.py
# Configuration drift detection — tracks config files, env vars, and
# service parameters, alerting when they deviate from the known-good baseline.

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class DriftSeverity(str, Enum):
    """Severity of a configuration drift."""

    INFO = "info"  # Cosmetic or non-impactful change
    WARNING = "warning"  # May affect behavior under certain conditions
    CRITICAL = "critical"  # Likely to cause failures or security issues


@dataclass
class DriftItem:
    """A single detected drift between baseline and current state."""

    key: str
    category: str  # "file", "env", "service_param"
    baseline_value: str
    current_value: str
    severity: DriftSeverity
    description: str = ""
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "category": self.category,
            "baseline_value": self.baseline_value,
            "current_value": self.current_value,
            "severity": self.severity.value,
            "description": self.description,
            "detected_at": self.detected_at,
        }


@dataclass
class DriftReport:
    """Complete drift detection report."""

    timestamp: float = field(default_factory=time.time)
    items: List[DriftItem] = field(default_factory=list)
    baseline_hash: str = ""
    current_hash: str = ""
    scan_duration_ms: float = 0.0

    @property
    def has_critical(self) -> bool:
        return any(d.severity == DriftSeverity.CRITICAL for d in self.items)

    @property
    def has_warnings(self) -> bool:
        return any(d.severity == DriftSeverity.WARNING for d in self.items)

    @property
    def drift_count(self) -> int:
        return len(self.items)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "drift_count": self.drift_count,
            "has_critical": self.has_critical,
            "has_warnings": self.has_warnings,
            "baseline_hash": self.baseline_hash,
            "current_hash": self.current_hash,
            "scan_duration_ms": round(self.scan_duration_ms, 2),
            "items": [d.to_dict() for d in self.items],
        }


class ConfigDriftDetector:
    """
    Detects configuration drift by comparing current state against a baseline.

    Tracks three categories:
      1. Files — watches config files for content/hash changes
      2. Environment — tracks environment variables that affect behavior
      3. Service params — monitors service configuration parameters

    Severity rules:
      - Files: docker-compose, nginx configs → CRITICAL; others → WARNING
      - Env vars: SECRET/KEY/PASSWORD changes → CRITICAL; operational → WARNING; cosmetic → INFO
      - Service params: port/host changes → WARNING; version changes → INFO

    Usage:
        detector = ConfigDriftDetector(baseline_dir="/app/.config_baseline")
        detector.capture_baseline()
        # ... later ...
        report = detector.detect_drift()
        if report.has_critical:
            alert_team(report)
    """

    # Default config files to track
    DEFAULT_CONFIG_FILES = [
        "docker-compose.yml",
        "docker-compose.yaml",
        ".env",
        ".env.production",
        "nginx/nginx.conf",
        "nginx/conf.d/default.conf",
        "config/production.json",
        "config/settings.json",
        "pyproject.toml",
        "requirements.txt",
    ]

    # Default environment variables to track
    DEFAULT_ENV_VARS = [
        "SYSTEM_MODE",
        "ENVIRONMENT",
        "API_PORT",
        "LOG_LEVEL",
        "DATABASE_URL",
        "SECRET_KEY",
        "JWT_SECRET",
        "JWT_ALGORITHM",
        "CORS_ORIGINS",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
    ]

    # Severity rules for env var changes
    CRITICAL_ENV_PATTERNS = ["SECRET", "KEY", "PASSWORD", "TOKEN", "PRIVATE"]
    WARNING_ENV_PATTERNS = ["PORT", "HOST", "URL", "DATABASE", "CORS"]

    def __init__(
        self,
        baseline_dir: str = ".config_baseline",
        config_files: Optional[List[str]] = None,
        env_vars: Optional[List[str]] = None,
        root_dir: str = ".",
        exclude_patterns: Optional[List[str]] = None,
    ):
        self._baseline_dir = Path(baseline_dir)
        self._root_dir = Path(root_dir)
        self._config_files = config_files or self.DEFAULT_CONFIG_FILES
        self._env_vars = env_vars or self.DEFAULT_ENV_VARS
        self._exclude_patterns = exclude_patterns or []
        self._service_params: Dict[str, Any] = {}
        self._callbacks: List[Callable] = []
        self._baseline_captured = False

    # ── Baseline Management ───────────────────────────────────────

    def capture_baseline(self) -> str:
        """
        Capture the current state as the baseline.
        Returns the baseline hash.
        """
        self._baseline_dir.mkdir(parents=True, exist_ok=True)

        baseline = {
            "timestamp": time.time(),
            "files": self._capture_files(),
            "env": self._capture_env(),
            "service_params": dict(self._service_params),
        }

        baseline_hash = self._hash_state(baseline)
        baseline["hash"] = baseline_hash

        baseline_path = self._baseline_dir / "baseline.json"
        with open(baseline_path, "w") as f:
            json.dump(baseline, f, indent=2, default=str)

        self._baseline_captured = True
        logger.info("Baseline captured: hash=%s", baseline_hash)
        return baseline_hash

    def load_baseline(self) -> Optional[Dict[str, Any]]:
        """Load the saved baseline."""
        baseline_path = self._baseline_dir / "baseline.json"
        if not baseline_path.exists():
            return None
        with open(baseline_path) as f:
            return json.load(f)

    # ── Drift Detection ───────────────────────────────────────────

    def detect_drift(self) -> DriftReport:
        """
        Compare current state against the baseline and return a DriftReport.
        """
        start = time.monotonic()
        report = DriftReport()

        baseline = self.load_baseline()
        if not baseline:
            logger.warning("No baseline found — capturing initial baseline")
            self.capture_baseline()
            report.scan_duration_ms = (time.monotonic() - start) * 1000
            return report

        report.baseline_hash = baseline.get("hash", "")

        # Detect file drift
        current_files = self._capture_files()
        report.items.extend(self._diff_files(baseline.get("files", {}), current_files))

        # Detect env drift
        current_env = self._capture_env()
        report.items.extend(self._diff_env(baseline.get("env", {}), current_env))

        # Detect service param drift
        current_params = dict(self._service_params)
        report.items.extend(self._diff_params(baseline.get("service_params", {}), current_params))

        # Compute current state hash
        current_state = {
            "files": current_files,
            "env": current_env,
            "service_params": current_params,
        }
        report.current_hash = self._hash_state(current_state)
        report.scan_duration_ms = (time.monotonic() - start) * 1000

        # Notify callbacks if drift detected
        if report.drift_count > 0:
            self._notify_drift(report)

        return report

    # ── Service Param Tracking ────────────────────────────────────

    def register_service_param(self, key: str, value: Any) -> None:
        """Register a service configuration parameter for tracking."""
        self._service_params[key] = value

    def update_service_param(self, key: str, value: Any) -> None:
        """Update a service parameter value."""
        old = self._service_params.get(key)
        self._service_params[key] = value
        if old != value and self._baseline_captured:
            logger.info("Service param changed: %s", sanitize_for_log(key))

    # ── Callbacks ─────────────────────────────────────────────────

    def on_drift(self, callback: Callable) -> None:
        """Register a callback for drift detection events."""
        self._callbacks.append(callback)

    def _notify_drift(self, report: DriftReport) -> None:
        for cb in self._callbacks:
            try:
                cb(report)
            except Exception as e:
                logger.error("Drift callback error: %s", sanitize_for_log(str(e)))

    # ── Internal: State Capture ───────────────────────────────────

    def _capture_files(self) -> Dict[str, Dict[str, Any]]:
        """Capture hashes and metadata for tracked config files."""
        result = {}
        for rel_path in self._config_files:
            # Skip excluded patterns
            if any(pat in rel_path for pat in self._exclude_patterns):
                continue
            full_path = self._root_dir / rel_path
            if full_path.exists() and full_path.is_file():
                try:
                    content = full_path.read_bytes()
                    file_hash = hashlib.sha256(content).hexdigest()
                    stat = full_path.stat()
                    result[rel_path] = {
                        "hash": file_hash,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                except (OSError, PermissionError) as e:
                    result[rel_path] = {"error": str(e)}
            else:
                result[rel_path] = {"status": "missing"}
        return result

    def _capture_env(self) -> Dict[str, str]:
        """Capture environment variables (masked for sensitive values)."""
        result = {}
        for var in self._env_vars:
            value = os.environ.get(var, "")
            if value:
                # Store a masked version + hash for comparison
                if self._is_sensitive_var(var):
                    result[var] = f"***masked:{hashlib.sha256(value.encode()).hexdigest()[:16]}"
                else:
                    result[var] = value
            else:
                result[var] = ""
        return result

    # ── Internal: Diffing ─────────────────────────────────────────

    def _diff_files(self, baseline: Dict[str, Any], current: Dict[str, Any]) -> List[DriftItem]:
        """Detect drift between baseline and current file states."""
        drifts = []
        all_keys = set(baseline.keys()) | set(current.keys())

        for key in all_keys:
            b = baseline.get(key, {})
            c = current.get(key, {})
            b_hash = b.get("hash", b.get("status", ""))
            c_hash = c.get("hash", c.get("status", ""))

            if b_hash != c_hash:
                # Determine severity
                severity = self._file_severity(key)
                desc = self._describe_file_drift(key, b, c)
                drifts.append(
                    DriftItem(
                        key=key,
                        category="file",
                        baseline_value=str(b_hash)[:16] if b_hash else "<missing>",
                        current_value=str(c_hash)[:16] if c_hash else "<missing>",
                        severity=severity,
                        description=desc,
                    ),
                )

        return drifts

    def _diff_env(self, baseline: Dict[str, str], current: Dict[str, str]) -> List[DriftItem]:
        """Detect drift between baseline and current environment state."""
        drifts = []
        all_keys = set(baseline.keys()) | set(current.keys())

        for key in all_keys:
            b_val = baseline.get(key, "")
            c_val = current.get(key, "")

            if b_val != c_val:
                severity = self._env_severity(key, b_val, c_val)
                desc = f"Environment variable {key} changed"
                if not b_val and c_val:
                    desc = f"Environment variable {key} was set (was unset)"
                elif b_val and not c_val:
                    desc = f"Environment variable {key} was unset (was set)"

                drifts.append(
                    DriftItem(
                        key=key,
                        category="env",
                        baseline_value=b_val or "<unset>",
                        current_value=c_val or "<unset>",
                        severity=severity,
                        description=desc,
                    ),
                )

        return drifts

    def _diff_params(self, baseline: Dict[str, Any], current: Dict[str, Any]) -> List[DriftItem]:
        """Detect drift in service parameters."""
        drifts = []
        all_keys = set(baseline.keys()) | set(current.keys())

        for key in all_keys:
            b_val = str(baseline.get(key, ""))
            c_val = str(current.get(key, ""))

            if b_val != c_val:
                severity = (
                    DriftSeverity.WARNING
                    if any(p in key.upper() for p in ["PORT", "HOST", "URL"])
                    else DriftSeverity.INFO
                )
                desc = f"Service parameter {key} changed from {b_val} to {c_val}"

                drifts.append(
                    DriftItem(
                        key=key,
                        category="service_param",
                        baseline_value=b_val or "<unset>",
                        current_value=c_val or "<unset>",
                        severity=severity,
                        description=desc,
                    ),
                )

        return drifts

    # ── Internal: Severity Classification ─────────────────────────

    def _file_severity(self, file_path: str) -> DriftSeverity:
        """Classify the severity of a file drift."""
        critical_files = ["docker-compose", ".env.production", "nginx.conf"]
        if any(cf in file_path for cf in critical_files):
            return DriftSeverity.CRITICAL
        warning_files = [".env", "requirements", "pyproject", "settings"]
        if any(wf in file_path for wf in warning_files):
            return DriftSeverity.WARNING
        return DriftSeverity.INFO

    def _env_severity(self, var_name: str, old_val: str, new_val: str) -> DriftSeverity:
        """Classify the severity of an environment variable drift."""
        upper = var_name.upper()
        # Critical: secrets being changed or unset
        if any(p in upper for p in self.CRITICAL_ENV_PATTERNS):
            # A secret changing is critical
            if old_val and new_val:
                return DriftSeverity.WARNING  # Rotation is expected
            return DriftSeverity.CRITICAL  # Secret appearing/disappearing is critical
        # Warning: operational config changes
        if any(p in upper for p in self.WARNING_ENV_PATTERNS):
            return DriftSeverity.WARNING
        return DriftSeverity.INFO

    def _is_sensitive_var(self, var_name: str) -> bool:
        """Check if an environment variable is sensitive."""
        upper = var_name.upper()
        return any(p in upper for p in self.CRITICAL_ENV_PATTERNS)

    # ── Internal: Utilities ───────────────────────────────────────

    @staticmethod
    def _hash_state(state: Dict[str, Any]) -> str:
        """Compute a deterministic hash of the entire state."""
        canonical = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]

    @staticmethod
    def _describe_file_drift(key: str, baseline: Dict, current: Dict) -> str:
        """Generate a human-readable description of a file drift."""
        b_status = baseline.get(
            "status",
            baseline.get("hash", "")[:8] if baseline.get("hash") else "absent",
        )
        c_status = current.get(
            "status",
            current.get("hash", "")[:8] if current.get("hash") else "absent",
        )

        if b_status == "missing" and c_status != "missing":
            return f"File {key} was created"
        if b_status != "missing" and c_status == "missing":
            return f"File {key} was deleted"
        if baseline.get("error") or current.get("error"):
            return f"File {key} access error"
        return f"File {key} content changed (hash: {str(b_status)[:8]}→{str(c_status)[:8]})"
