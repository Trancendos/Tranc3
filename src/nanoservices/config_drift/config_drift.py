"""Configuration Drift Detector — Phase 12

Proactive configuration validation and drift detection across
nanoservices. Ensures running config matches declared intent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class DriftSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfigSource(Enum):
    FILE = "file"
    ENVIRONMENT = "environment"
    GITOPS = "gitops"
    RUNTIME = "runtime"
    DEFAULT = "default"


@dataclass
class ConfigEntry:
    key: str
    value: Any
    source: ConfigSource = ConfigSource.DEFAULT
    schema_type: str = "str"
    required: bool = False
    sensitive: bool = False
    description: str = ""
    last_updated: float = field(default_factory=time.time)


@dataclass
class ConfigSnapshot:
    service_name: str
    entries: Dict[str, ConfigEntry] = field(default_factory=dict)
    hash: str = ""
    timestamp: float = field(default_factory=time.time)

    def compute_hash(self) -> str:
        content = json.dumps(
            {k: {"v": str(e.value), "s": e.source.value} for k, e in sorted(self.entries.items())},
            sort_keys=True,
        )
        self.hash = hashlib.sha256(content.encode()).hexdigest()
        return self.hash


@dataclass
class DriftReport:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    service_name: str = ""
    expected_hash: str = ""
    actual_hash: str = ""
    drifted_keys: List[str] = field(default_factory=list)
    severity: DriftSeverity = DriftSeverity.LOW
    details: List[Dict[str, Any]] = field(default_factory=list)
    detected_at: float = field(default_factory=time.time)
    auto_remediated: bool = False


class ConfigSchema:
    """Defines expected configuration for a service."""

    def __init__(self, service_name: str):
        self._service_name = service_name
        self._required_keys: Dict[str, ConfigEntry] = {}
        self._optional_keys: Dict[str, ConfigEntry] = {}

    @property
    def service_name(self) -> str:
        return self._service_name

    def add_required(
        self,
        key: str,
        value_type: str = "str",
        default: Any = None,
        sensitive: bool = False,
        description: str = "",
    ) -> None:
        self._required_keys[key] = ConfigEntry(
            key=key,
            value=default,
            schema_type=value_type,
            required=True,
            sensitive=sensitive,
            description=description,
        )

    def add_optional(
        self,
        key: str,
        value_type: str = "str",
        default: Any = None,
        sensitive: bool = False,
        description: str = "",
    ) -> None:
        self._optional_keys[key] = ConfigEntry(
            key=key,
            value=default,
            schema_type=value_type,
            required=False,
            sensitive=sensitive,
            description=description,
        )

    def validate(self, snapshot: ConfigSnapshot) -> List[str]:
        errors = []
        for key, entry in self._required_keys.items():
            if key not in snapshot.entries:
                errors.append(f"Missing required key: {key}")
            elif snapshot.entries[key].value is None:
                errors.append(f"Required key has no value: {key}")

        for key, entry in snapshot.entries.items():
            if key in self._required_keys:
                expected_type = self._required_keys[key].schema_type
            elif key in self._optional_keys:
                expected_type = self._optional_keys[key].schema_type
            else:
                continue
            if entry.value is not None and not self._type_matches(entry.value, expected_type):
                errors.append(
                    f"Type mismatch for {key}: expected {expected_type}, got {type(entry.value).__name__}"
                )

        return errors

    def _type_matches(self, value: Any, expected_type: str) -> bool:
        type_map = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        return isinstance(value, expected)

    @property
    def all_keys(self) -> Set[str]:
        return set(self._required_keys.keys()) | set(self._optional_keys.keys())


class ConfigDriftDetector:
    """Detects configuration drift between expected and actual state."""

    def __init__(self):
        self._baselines: Dict[str, ConfigSnapshot] = {}
        self._schemas: Dict[str, ConfigSchema] = {}
        self._drift_history: List[DriftReport] = []

    def register_schema(self, schema: ConfigSchema) -> None:
        self._schemas[schema.service_name] = schema

    def set_baseline(self, snapshot: ConfigSnapshot) -> None:
        snapshot.compute_hash()
        self._baselines[snapshot.service_name] = snapshot

    def detect_drift(self, current: ConfigSnapshot) -> Optional[DriftReport]:
        baseline = self._baselines.get(current.service_name)
        schema = self._schemas.get(current.service_name)

        # Schema validation
        schema_errors = schema.validate(current) if schema else []

        # Baseline comparison
        drifted_keys = []
        details = []
        severity = DriftSeverity.LOW

        if baseline:
            current.compute_hash()
            if current.hash != baseline.hash:
                for key in set(list(current.entries.keys()) + list(baseline.entries.keys())):
                    current_val = current.entries.get(key)
                    baseline_val = baseline.entries.get(key)

                    if current_val is None and baseline_val is not None:
                        drifted_keys.append(key)
                        details.append(
                            {"key": key, "change": "removed", "was": str(baseline_val.value)}
                        )
                        if baseline_val.required:
                            severity = DriftSeverity.CRITICAL
                        elif severity == DriftSeverity.LOW:
                            severity = DriftSeverity.MEDIUM
                    elif current_val is not None and baseline_val is None:
                        drifted_keys.append(key)
                        details.append(
                            {"key": key, "change": "added", "now": str(current_val.value)}
                        )
                    elif (
                        current_val
                        and baseline_val
                        and str(current_val.value) != str(baseline_val.value)
                    ):
                        drifted_keys.append(key)
                        details.append(
                            {
                                "key": key,
                                "change": "modified",
                                "was": str(baseline_val.value),
                                "now": str(current_val.value),
                                "source_change": f"{baseline_val.source.value} → {current_val.source.value}",
                            }
                        )
                        if current_val.sensitive:
                            severity = DriftSeverity.HIGH
                        elif baseline_val.required:
                            severity = DriftSeverity.HIGH
                        elif severity == DriftSeverity.LOW:
                            severity = DriftSeverity.MEDIUM

        for err in schema_errors:
            details.append({"key": "schema", "change": "validation_error", "detail": err})
            if "required" in err.lower():
                severity = DriftSeverity.CRITICAL

        if not drifted_keys and not schema_errors:
            return None

        report = DriftReport(
            service_name=current.service_name,
            expected_hash=baseline.hash if baseline else "",
            actual_hash=current.compute_hash(),
            drifted_keys=drifted_keys,
            severity=severity,
            details=details,
        )
        self._drift_history.append(report)
        return report

    def get_drift_history(self, service_name: str = "", limit: int = 50) -> List[DriftReport]:
        reports = self._drift_history
        if service_name:
            reports = [r for r in reports if r.service_name == service_name]
        return reports[-limit:]

    def auto_remediate(self, current: ConfigSnapshot) -> bool:
        """Reset drifted config back to baseline."""
        baseline = self._baselines.get(current.service_name)
        if not baseline:
            return False
        for key, entry in baseline.entries.items():
            if key in current.entries:
                current.entries[key].value = entry.value
                current.entries[key].source = entry.source
        current.compute_hash()
        return True


class ConfigDriftDetectorService:
    """Main service: proactive config validation and drift detection."""

    def __init__(self):
        self._detector = ConfigDriftDetector()
        self._watch_interval: float = 60.0

    def initialize(self) -> None:
        # Register schemas for core services
        core_schema = ConfigSchema("tranc3_core")
        core_schema.add_required("LOG_LEVEL", "str", "INFO", description="Logging level")
        core_schema.add_required("NANOSERVICE_POOL_SIZE", "int", 10, description="Worker pool size")
        core_schema.add_optional(
            "ENABLE_QUANTUM", "bool", False, description="Quantum solver toggle"
        )
        core_schema.add_optional("MAX_CONCURRENT_FLOWS", "int", 100, description="DNF flow limit")
        core_schema.add_optional(
            "SHI_FALLBACK_ENABLED", "bool", True, description="SHI fallback chain"
        )
        self._detector.register_schema(core_schema)

        logger.info("ConfigDriftDetectorService initialized with core schema")

    def register_schema(self, schema: ConfigSchema) -> None:
        self._detector.register_schema(schema)

    def set_baseline(self, snapshot: ConfigSnapshot) -> None:
        self._detector.set_baseline(snapshot)

    def check_drift(self, current: ConfigSnapshot) -> Optional[DriftReport]:
        report = self._detector.detect_drift(current)
        if report:
            logger.warning(
                "Config drift detected in %s: %d keys drifted (severity=%s)",
                current.service_name,
                len(report.drifted_keys),
                report.severity.value,
            )
        return report

    def remediate(self, current: ConfigSnapshot) -> bool:
        return self._detector.auto_remediate(current)

    def get_drift_history(self, service_name: str = "", limit: int = 50) -> List[DriftReport]:
        return self._detector.get_drift_history(service_name, limit)
