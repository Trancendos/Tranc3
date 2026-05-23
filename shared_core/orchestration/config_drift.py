"""
shared_core.orchestration.config_drift — Configuration drift detection and monitoring.

Captures baselines of configuration state (files, environment variables,
service parameters) and detects when drift occurs from the baseline.
Supports file-content hashing, env-var tracking, and service parameter
monitoring.

Zero-cost: All detection is local, no external services required.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DriftItem:
    """A single detected drift."""
    category: str  # "file", "env", "service_param"
    key: str
    old_value: str
    new_value: str
    detected_at: str = ""

    def __post_init__(self) -> None:
        if not self.detected_at:
            self.detected_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, str]:
        return {
            "category": self.category,
            "key": self.key,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "detected_at": self.detected_at,
        }


@dataclass
class DriftReport:
    """Report of configuration drift from baseline."""
    drift_count: int = 0
    items: List[DriftItem] = field(default_factory=list)
    checked_at: str = ""

    def __post_init__(self) -> None:
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drift_count": self.drift_count,
            "items": [item.to_dict() for item in self.items],
            "checked_at": self.checked_at,
        }


class ConfigDriftDetector:
    """Configuration drift detector and monitor.

    Captures baselines of file contents, environment variables, and service
    parameters, then detects when the current state drifts from baseline.

    Args:
        baseline_dir: Directory to store baseline snapshots.
        root_dir: Root directory for relative file paths.
        config_files: List of config file paths (relative to root_dir).
        env_vars: List of environment variable names to track.
    """

    def __init__(
        self,
        baseline_dir: Optional[str] = None,
        root_dir: Optional[str] = None,
        config_files: Optional[List[str]] = None,
        env_vars: Optional[List[str]] = None,
    ) -> None:
        self._baseline_dir = Path(baseline_dir) if baseline_dir else Path.cwd() / ".drift_baseline"
        self._root_dir = Path(root_dir) if root_dir else Path.cwd()
        self._config_files = config_files or []
        self._env_vars = env_vars or []
        self._service_params: Dict[str, Any] = {}
        self._baseline: Dict[str, Any] = {}

    def capture_baseline(self) -> str:
        """Capture current state as baseline.

        Returns:
            SHA-256 hash of the baseline state.
        """
        self._baseline = {}

        # Capture file contents
        for config_file in self._config_files:
            filepath = self._root_dir / config_file
            if filepath.exists():
                content = filepath.read_text()
                self._baseline[f"file:{config_file}"] = hashlib.sha256(
                    content.encode()
                ).hexdigest()

        # Capture environment variables
        for var in self._env_vars:
            self._baseline[f"env:{var}"] = os.environ.get(var, "")

        # Capture service parameters
        for key, value in self._service_params.items():
            self._baseline[f"service_param:{key}"] = str(value)

        # Save baseline to disk
        self._baseline_dir.mkdir(parents=True, exist_ok=True)
        baseline_path = self._baseline_dir / "baseline.json"
        baseline_path.write_text(json.dumps(self._baseline, indent=2))

        # Return hash of entire baseline
        baseline_hash = hashlib.sha256(
            json.dumps(self._baseline, sort_keys=True).encode()
        ).hexdigest()
        return baseline_hash

    def detect_drift(self) -> DriftReport:
        """Detect drift from the captured baseline.

        Returns:
            DriftReport with all detected drift items.
        """
        items: List[DriftItem] = []

        # Check file drift
        for config_file in self._config_files:
            key = f"file:{config_file}"
            filepath = self._root_dir / config_file
            if filepath.exists():
                current_hash = hashlib.sha256(
                    filepath.read_text().encode()
                ).hexdigest()
                baseline_hash = self._baseline.get(key, "")
                if current_hash != baseline_hash:
                    items.append(DriftItem(
                        category="file",
                        key=config_file,
                        old_value=baseline_hash[:16],
                        new_value=current_hash[:16],
                    ))

        # Check environment variable drift
        for var in self._env_vars:
            key = f"env:{var}"
            current = os.environ.get(var, "")
            baseline_val = self._baseline.get(key, "")
            if current != baseline_val:
                items.append(DriftItem(
                    category="env",
                    key=var,
                    old_value=baseline_val,
                    new_value=current,
                ))

        # Check service parameter drift
        for key, value in self._service_params.items():
            bkey = f"service_param:{key}"
            current = str(value)
            baseline_val = self._baseline.get(bkey, "")
            if current != baseline_val:
                items.append(DriftItem(
                    category="service_param",
                    key=key,
                    old_value=baseline_val,
                    new_value=current,
                ))

        return DriftReport(drift_count=len(items), items=items)

    def register_service_param(self, name: str, value: Any) -> None:
        """Register a service parameter for tracking.

        Args:
            name: Parameter name.
            value: Current value.
        """
        self._service_params[name] = value

    def update_service_param(self, name: str, value: Any) -> None:
        """Update a service parameter value.

        Args:
            name: Parameter name.
            value: New value.
        """
        self._service_params[name] = value
