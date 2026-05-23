"""
shared_core.architecture.auto_config — Dynamic Auto-Configuration System for Tranc3.

Implements intelligent auto-detection and dynamic configuration that adapts
the platform to its runtime environment. The system automatically detects
available resources, configures optimal settings, and supports hot-reload
of configuration without service restart.

Key Features:
    - Auto-detect environment (TRUE_NAS, HYBRID, CLOUD_ONLY)
    - Auto-detect available services (Redis, MinIO, PostgreSQL, etc.)
    - Apply optimal configuration profiles based on detected environment
    - Hot-reload configuration changes without service restart
    - Conditional configuration rules (if X is available, configure Y)
    - Validate configuration before applying
    - Rollback on validation failure

Architecture:
    ┌───────────────────────────────────────────────────┐
    │              AutoConfigManager                      │
    │                                                     │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
    │  │  Environment  │  │  Config      │  │  Hot     │ │
    │  │  Detector     │  │  Profiles    │  │  Reload  │ │
    │  └──────┬───────┘  └──────┬───────┘  └────┬─────┘ │
    │         │                 │                │       │
    │  ┌──────┴─────────────────┴────────────────┴─────┐ │
    │  │           Validation & Rollback                │ │
    │  └───────────────────────────────────────────────┘ │
    └───────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EnvironmentType(str, Enum):
    """Detected runtime environment type."""

    TRUE_NAS = "TRUE_NAS"
    HYBRID = "HYBRID"
    CLOUD_ONLY = "CLOUD_ONLY"
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    UNKNOWN = "unknown"


class ConfigStatus(str, Enum):
    """Status of a configuration item."""

    DEFAULT = "default"
    DETECTED = "detected"
    OVERRIDDEN = "overridden"
    HOT_RELOADED = "hot_reloaded"
    VALIDATED = "validated"
    ROLLED_BACK = "rolled_back"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class ConfigItem:
    """A single configuration item with metadata."""

    key: str
    value: Any
    status: ConfigStatus = ConfigStatus.DEFAULT
    source: str = "default"  # Where the value came from
    previous_value: Any = None  # For rollback
    last_updated: float = field(default_factory=time.time)
    validator: Optional[Callable] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "status": self.status.value,
            "source": self.source,
            "previous_value": self.previous_value,
            "last_updated": self.last_updated,
            "description": self.description,
        }


@dataclass
class ConfigProfile:
    """A named configuration profile for a specific environment."""

    name: str
    environment: EnvironmentType
    description: str = ""
    settings: Dict[str, Any] = field(default_factory=dict)
    rules: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "environment": self.environment.value,
            "description": self.description,
            "settings": self.settings,
            "rules_count": len(self.rules),
            "created_at": self.created_at,
        }


@dataclass
class DetectionResult:
    """Result of an environment or service detection."""

    name: str
    detected: bool
    value: Any = None
    confidence: float = 1.0
    method: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "detected": self.detected,
            "value": self.value,
            "confidence": self.confidence,
            "method": self.method,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Environment Detector
# ---------------------------------------------------------------------------


class EnvironmentDetector:
    """
    Auto-detects the runtime environment and available services.

    Detection Methods:
        - Environment variables (SYSTEM_MODE, ENVIRONMENT)
        - Service connectivity (Redis, MinIO, PostgreSQL, API)
        - File system detection (ZFS pools, Docker volumes)
        - Network detection (cloud metadata endpoints)
    """

    def __init__(self):
        self._detection_results: List[DetectionResult] = []

    def detect_all(self) -> Dict[str, DetectionResult]:
        """Run all detection checks and return results."""
        results = {}

        # 1. System Mode detection
        results["system_mode"] = self._detect_system_mode()

        # 2. Environment type
        results["environment"] = self._detect_environment()

        # 3. Service availability
        results["redis"] = self._detect_redis()
        results["minio"] = self._detect_minio()
        results["postgresql"] = self._detect_postgresql()
        results["api_server"] = self._detect_api_server()

        # 4. File system detection
        results["zfs_available"] = self._detect_zfs()
        results["docker_available"] = self._detect_docker()

        # 5. Cloud provider detection
        results["cloud_provider"] = self._detect_cloud_provider()

        # 6. Zero-cost storage availability
        results["r2_available"] = self._detect_r2()
        results["oci_available"] = self._detect_oci()
        results["gcp_available"] = self._detect_gcp()
        results["azure_available"] = self._detect_azure()
        results["aws_available"] = self._detect_aws()

        self._detection_results = list(results.values())
        return results

    def _detect_system_mode(self) -> DetectionResult:
        """Detect the system mode (TRUE_NAS, HYBRID, CLOUD_ONLY)."""
        mode = os.getenv("SYSTEM_MODE", "")
        if mode.upper() in ("TRUE_NAS", "HYBRID", "CLOUD_ONLY"):
            return DetectionResult(
                name="system_mode",
                detected=True,
                value=mode.upper(),
                confidence=1.0,
                method="env_var",
            )

        # Infer from available services
        has_zfs = self._detect_zfs().detected
        has_cloud = any(
            [
                self._detect_r2().detected,
                self._detect_oci().detected,
            ]
        )

        if has_zfs and not has_cloud:
            inferred = "TRUE_NAS"
        elif has_zfs and has_cloud:
            inferred = "HYBRID"
        elif has_cloud:
            inferred = "CLOUD_ONLY"
        else:
            inferred = "HYBRID"  # Default

        return DetectionResult(
            name="system_mode",
            detected=True,
            value=inferred,
            confidence=0.7,
            method="inferred",
        )

    def _detect_environment(self) -> DetectionResult:
        """Detect if running in development or production."""
        env = os.getenv("ENVIRONMENT", os.getenv("ENV", "")).lower()
        if env in ("production", "prod"):
            value = "production"
            confidence = 1.0
        elif env in ("development", "dev"):
            value = "development"
            confidence = 1.0
        else:
            # Infer from indicators
            debug = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
            value = "development" if debug else "production"
            confidence = 0.6

        return DetectionResult(
            name="environment",
            detected=True,
            value=value,
            confidence=confidence,
            method="env_var",
        )

    def _detect_redis(self) -> DetectionResult:
        """Detect if Redis is available."""
        url = os.getenv("REDIS_URL", "")
        if not url:
            return DetectionResult(name="redis", detected=False, method="env_var")

        try:
            import redis

            r = redis.from_url(url)
            r.ping()
            return DetectionResult(
                name="redis",
                detected=True,
                value=url,
                confidence=1.0,
                method="connection_test",
            )
        except Exception:
            return DetectionResult(
                name="redis",
                detected=False,
                value=url,
                confidence=0.5,
                method="connection_test",
            )

    def _detect_minio(self) -> DetectionResult:
        """Detect if MinIO is available."""
        endpoint = os.getenv("MINIO_ENDPOINT", "")
        if not endpoint:
            return DetectionResult(name="minio", detected=False, method="env_var")

        return DetectionResult(
            name="minio",
            detected=True,
            value=endpoint,
            confidence=0.8,
            method="env_var",
        )

    def _detect_postgresql(self) -> DetectionResult:
        """Detect if PostgreSQL is available."""
        url = os.getenv("DATABASE_URL", os.getenv("POSTGRES_URL", ""))
        if not url:
            return DetectionResult(name="postgresql", detected=False, method="env_var")

        return DetectionResult(
            name="postgresql",
            detected=True,
            value="configured",
            confidence=0.8,
            method="env_var",
        )

    def _detect_api_server(self) -> DetectionResult:
        """Detect if the API server is running."""
        host = os.getenv("API_HOST", "localhost")
        port = int(os.getenv("API_PORT", "8000"))

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            result = sock.connect_ex((host, port))
            sock.close()
            return DetectionResult(
                name="api_server",
                detected=(result == 0),
                value=f"{host}:{port}",
                confidence=1.0,
                method="tcp_connect",
            )
        except Exception:
            return DetectionResult(
                name="api_server",
                detected=False,
                value=f"{host}:{port}",
                method="tcp_connect",
            )

    def _detect_zfs(self) -> DetectionResult:
        """Detect if ZFS is available."""
        # Check for ZFS commands
        zfs_path = os.path.exists("/sbin/zfs") or os.path.exists("/usr/sbin/zfs")
        zpool_path = os.path.exists("/sbin/zpool") or os.path.exists("/usr/sbin/zpool")

        if zfs_path and zpool_path:
            return DetectionResult(
                name="zfs_available",
                detected=True,
                confidence=0.9,
                method="filesystem_check",
            )

        # Check for ZFS env var
        if os.getenv("ZFS_POOL"):
            return DetectionResult(
                name="zfs_available",
                detected=True,
                value=os.getenv("ZFS_POOL"),
                confidence=0.8,
                method="env_var",
            )

        return DetectionResult(name="zfs_available", detected=False, method="filesystem_check")

    def _detect_docker(self) -> DetectionResult:
        """Detect if running inside Docker."""
        dockerenv = os.path.exists("/.dockerenv")
        cgroup = False
        try:
            with open("/proc/1/cgroup", "r") as f:
                cgroup = "docker" in f.read() or "containerd" in f.read()
        except (OSError, IOError):
            pass

        return DetectionResult(
            name="docker_available",
            detected=(dockerenv or cgroup),
            confidence=0.9 if (dockerenv or cgroup) else 0.3,
            method="filesystem_check",
        )

    def _detect_cloud_provider(self) -> DetectionResult:
        """Detect which cloud provider we're running on."""
        # Check cloud metadata endpoints
        # OCI
        if os.getenv("OCI_COMPARTMENT_ID") or os.getenv("OCI_TENANCY_ID"):
            return DetectionResult(
                name="cloud_provider",
                detected=True,
                value="oci",
                confidence=0.9,
                method="env_var",
            )
        # GCP
        if os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID"):
            return DetectionResult(
                name="cloud_provider",
                detected=True,
                value="gcp",
                confidence=0.9,
                method="env_var",
            )
        # Azure
        if os.getenv("AZURE_SUBSCRIPTION_ID") or os.getenv("AZURE_COSMOS_ENDPOINT"):
            return DetectionResult(
                name="cloud_provider",
                detected=True,
                value="azure",
                confidence=0.9,
                method="env_var",
            )
        # AWS
        if os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"):
            return DetectionResult(
                name="cloud_provider",
                detected=True,
                value="aws",
                confidence=0.9,
                method="env_var",
            )

        return DetectionResult(name="cloud_provider", detected=False, method="env_var")

    def _detect_r2(self) -> DetectionResult:
        """Detect if Cloudflare R2 is configured."""
        has_creds = bool(os.getenv("R2_ACCESS_KEY_ID") and os.getenv("R2_SECRET_ACCESS_KEY"))
        return DetectionResult(
            name="r2_available",
            detected=has_creds,
            confidence=0.8 if has_creds else 0.0,
            method="env_var",
        )

    def _detect_oci(self) -> DetectionResult:
        """Detect if OCI Object Storage is configured."""
        has_creds = bool(
            os.getenv("OCI_COMPARTMENT_ID")
            and os.getenv("OCI_TENANCY_ID")
            and os.getenv("OCI_USER_ID")
            and os.getenv("OCI_FINGERPRINT")
            and os.getenv("OCI_PRIVATE_KEY_PATH")
        )
        return DetectionResult(
            name="oci_available",
            detected=has_creds,
            confidence=0.8 if has_creds else 0.0,
            method="env_var",
        )

    def _detect_gcp(self) -> DetectionResult:
        """Detect if GCP Cloud Storage is configured."""
        has_creds = bool(os.getenv("GCP_PROJECT_ID") and os.getenv("GCP_CREDENTIALS_PATH"))
        return DetectionResult(
            name="gcp_available",
            detected=has_creds,
            confidence=0.8 if has_creds else 0.0,
            method="env_var",
        )

    def _detect_azure(self) -> DetectionResult:
        """Detect if Azure Cosmos DB is configured."""
        has_creds = bool(os.getenv("AZURE_COSMOS_ENDPOINT") and os.getenv("AZURE_COSMOS_KEY"))
        return DetectionResult(
            name="azure_available",
            detected=has_creds,
            confidence=0.8 if has_creds else 0.0,
            method="env_var",
        )

    def _detect_aws(self) -> DetectionResult:
        """Detect if AWS DynamoDB is configured."""
        has_creds = bool(os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"))
        return DetectionResult(
            name="aws_available",
            detected=has_creds,
            confidence=0.8 if has_creds else 0.0,
            method="env_var",
        )

    def get_results(self) -> List[Dict[str, Any]]:
        """Get all detection results."""
        return [r.to_dict() for r in self._detection_results]


# ---------------------------------------------------------------------------
# Auto Config Manager
# ---------------------------------------------------------------------------


class AutoConfigManager:
    """
    Dynamic auto-configuration manager for the Tranc3 platform.

    Automatically detects the runtime environment, applies optimal
    configuration profiles, and supports hot-reload of configuration
    changes without service restart.

    The manager maintains a registry of configuration items with:
        - Current value and status
        - Source tracking (default, detected, overridden, hot-reloaded)
        - Previous value for rollback
        - Optional validators

    Profiles are pre-defined configurations for specific environments
    that can be applied in bulk. Rules are conditional configurations
    that are applied when their conditions are met.

    Usage:
        manager = AutoConfigManager()

        # Auto-detect and configure
        profile = manager.auto_configure()

        # Override a specific setting
        manager.set("api.workers", 4, source="manual")

        # Hot-reload from environment
        manager.hot_reload()

        # Get current configuration
        config = manager.get_config()
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = config_path or os.getenv("TRANC3_CONFIG_PATH", "")
        self._items: Dict[str, ConfigItem] = {}
        self._profiles: Dict[str, ConfigProfile] = {}
        self._detector = EnvironmentDetector()
        self._detection_results: Dict[str, DetectionResult] = {}
        self._change_listeners: List[Callable] = []
        self._last_reload: float = 0.0
        self._total_reloads = 0
        self._total_rollbacks = 0

        # Seed built-in profiles
        self._seed_profiles()

    # ------------------------------------------------------------------
    # Built-in Profiles
    # ------------------------------------------------------------------

    def _seed_profiles(self) -> None:
        """Seed built-in configuration profiles for each environment."""
        # TRUE_NAS Profile — local-first, maximum performance
        self.register_profile(
            ConfigProfile(
                name="true_nas_production",
                environment=EnvironmentType.TRUE_NAS,
                description="TRUE_NAS production profile — local-first, ZFS primary, no cloud",
                settings={
                    "storage.primary_tier": "ZFS",
                    "storage.enable_cloud_fallback": False,
                    "storage.capacity_check_interval": 60,
                    "sentinel.check_interval": 300,
                    "sentinel.auto_remediate": True,
                    "orchestrator.mode": "AUTONOMOUS",
                    "orchestrator.interval": 30,
                    "pulse.baseline_interval": 30,
                    "pulse.acceleration_factor": 3.0,
                    "pulse.emergency_factor": 10.0,
                    "router.strategy": "weighted_health",
                    "registry.discovery_interval": 60,
                    "registry.heartbeat_timeout": 90,
                    "defense.default_action": "allow",
                    "defense.rate_limit_enabled": True,
                    "scaling.forecast_horizon": 300,
                    "scaling.free_tier_limit": 999,  # No cloud limit in TRUE_NAS
                    "scaling.smoothing_alpha": 0.3,
                },
                rules=[
                    {
                        "condition": "zfs_available == true",
                        "settings": {
                            "storage.zfs_compression": "lz4",
                            "storage.zfs_snapshot_interval": 3600,
                        },
                    },
                    {
                        "condition": "minio_available == true",
                        "settings": {
                            "storage.minio_versioning": True,
                            "storage.minio_replication": False,
                        },
                    },
                ],
            )
        )

        # HYBRID Profile — local primary, cloud fallback
        self.register_profile(
            ConfigProfile(
                name="hybrid_balanced",
                environment=EnvironmentType.HYBRID,
                description="HYBRID balanced profile — local primary, cloud free-tier fallback",
                settings={
                    "storage.primary_tier": "ZFS",
                    "storage.enable_cloud_fallback": True,
                    "storage.capacity_check_interval": 30,
                    "storage.migration_threshold": 0.85,
                    "sentinel.check_interval": 180,
                    "sentinel.auto_remediate": True,
                    "orchestrator.mode": "AUTONOMOUS",
                    "orchestrator.interval": 20,
                    "pulse.baseline_interval": 20,
                    "pulse.acceleration_factor": 4.0,
                    "pulse.emergency_factor": 12.0,
                    "router.strategy": "weighted_health",
                    "registry.discovery_interval": 45,
                    "registry.heartbeat_timeout": 75,
                    "defense.default_action": "rate_limit",
                    "defense.rate_limit_enabled": True,
                    "scaling.forecast_horizon": 300,
                    "scaling.free_tier_limit": 5,
                    "scaling.smoothing_alpha": 0.25,
                },
                rules=[
                    {
                        "condition": "r2_available == true",
                        "settings": {"storage.r2_tier_priority": 3, "storage.r2_egress_free": True},
                    },
                    {
                        "condition": "oci_available == true",
                        "settings": {"storage.oci_tier_priority": 4, "storage.oci_free_gb": 20},
                    },
                    {
                        "condition": "gcp_available == true",
                        "settings": {"storage.gcp_tier_priority": 5, "storage.gcp_free_gb": 5},
                    },
                    {
                        "condition": "azure_available == true",
                        "settings": {"storage.azure_tier_priority": 6, "storage.azure_free_gb": 25},
                    },
                    {
                        "condition": "aws_available == true",
                        "settings": {"storage.aws_tier_priority": 7, "storage.aws_free_gb": 25},
                    },
                ],
            )
        )

        # CLOUD_ONLY Profile — cloud-first, zero-cost only
        self.register_profile(
            ConfigProfile(
                name="cloud_only_zero_cost",
                environment=EnvironmentType.CLOUD_ONLY,
                description="CLOUD_ONLY zero-cost profile — cloud free-tier primary and fallback",
                settings={
                    "storage.primary_tier": "R2",
                    "storage.enable_cloud_fallback": True,
                    "storage.capacity_check_interval": 15,
                    "storage.migration_threshold": 0.80,
                    "sentinel.check_interval": 120,
                    "sentinel.auto_remediate": True,
                    "orchestrator.mode": "AUTONOMOUS",
                    "orchestrator.interval": 15,
                    "pulse.baseline_interval": 15,
                    "pulse.acceleration_factor": 5.0,
                    "pulse.emergency_factor": 15.0,
                    "router.strategy": "capability_score",
                    "registry.discovery_interval": 30,
                    "registry.heartbeat_timeout": 60,
                    "defense.default_action": "deny",
                    "defense.rate_limit_enabled": True,
                    "scaling.forecast_horizon": 300,
                    "scaling.free_tier_limit": 3,  # Conservative for cloud
                    "scaling.smoothing_alpha": 0.2,
                },
                rules=[
                    {
                        "condition": "r2_available == true",
                        "settings": {"storage.r2_tier_priority": 0, "storage.r2_egress_free": True},
                    },
                    {
                        "condition": "oci_available == true",
                        "settings": {"storage.oci_tier_priority": 1, "storage.oci_free_gb": 20},
                    },
                    {
                        "condition": "gcp_available == true",
                        "settings": {"storage.gcp_tier_priority": 2, "storage.gcp_free_gb": 5},
                    },
                    {
                        "condition": "azure_available == true",
                        "settings": {"storage.azure_tier_priority": 3, "storage.azure_free_gb": 25},
                    },
                    {
                        "condition": "aws_available == true",
                        "settings": {"storage.aws_tier_priority": 4, "storage.aws_free_gb": 25},
                    },
                ],
            )
        )

        # Development Profile — fast iterations, verbose logging
        self.register_profile(
            ConfigProfile(
                name="development",
                environment=EnvironmentType.DEVELOPMENT,
                description="Development profile — fast checks, verbose logging, relaxed security",
                settings={
                    "storage.primary_tier": "ZFS",
                    "storage.enable_cloud_fallback": False,
                    "storage.capacity_check_interval": 120,
                    "sentinel.check_interval": 600,
                    "sentinel.auto_remediate": False,
                    "orchestrator.mode": "ASSIST",
                    "orchestrator.interval": 60,
                    "pulse.baseline_interval": 60,
                    "pulse.acceleration_factor": 2.0,
                    "pulse.emergency_factor": 5.0,
                    "router.strategy": "round_robin",
                    "registry.discovery_interval": 120,
                    "registry.heartbeat_timeout": 180,
                    "defense.default_action": "allow",
                    "defense.rate_limit_enabled": False,
                    "scaling.forecast_horizon": 600,
                    "scaling.free_tier_limit": 999,
                    "scaling.smoothing_alpha": 0.4,
                    "logging.level": "DEBUG",
                },
                rules=[],
            )
        )

    # ------------------------------------------------------------------
    # Profile Management
    # ------------------------------------------------------------------

    def register_profile(self, profile: ConfigProfile) -> None:
        """Register a configuration profile."""
        self._profiles[profile.name] = profile
        logger.info(
            "Config profile registered: %s (%s)",
            sanitize_for_log(profile.name),
            profile.environment.value,
        )

    def get_profile(self, name: str) -> Optional[ConfigProfile]:
        """Get a configuration profile by name."""
        return self._profiles.get(name)

    def list_profiles(self) -> List[Dict[str, Any]]:
        """List all registered profiles."""
        return [p.to_dict() for p in self._profiles.values()]

    # ------------------------------------------------------------------
    # Configuration Management
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        item = self._items.get(key)
        if item:
            return item.value
        return default

    def set(
        self,
        key: str,
        value: Any,
        source: str = "manual",
        validator: Optional[Callable] = None,
        description: str = "",
    ) -> bool:
        """
        Set a configuration value.

        Returns True if the value was set successfully, False if validation failed.
        """
        # Validate if validator is provided
        if validator:
            try:
                if not validator(value):
                    logger.warning("Config validation failed for %s", sanitize_for_log(key))
                    return False
            except Exception as e:
                logger.error(
                    "Config validator error for %s: %s",
                    sanitize_for_log(key),
                    sanitize_for_log(str(e)),
                )
                return False

        # Store previous value for rollback
        previous = None
        if key in self._items:
            previous = self._items[key].value

        # Determine status
        if source == "hot_reload":
            status = ConfigStatus.HOT_RELOADED
        elif source in ("detected", "auto_detect"):
            status = ConfigStatus.DETECTED
        elif source == "override":
            status = ConfigStatus.OVERRIDDEN
        else:
            status = ConfigStatus.DEFAULT

        self._items[key] = ConfigItem(
            key=key,
            value=value,
            status=status,
            source=source,
            previous_value=previous,
            validator=validator,
            description=description,
        )

        # Notify listeners
        for listener in self._change_listeners:
            try:
                listener(key, value, previous)
            except Exception as e:
                logger.error("Config change listener error: %s", sanitize_for_log(str(e)))

        return True

    def rollback(self, key: str) -> bool:
        """Rollback a configuration value to its previous value."""
        item = self._items.get(key)
        if not item or item.previous_value is None:
            return False

        old_value = item.value
        item.value = item.previous_value
        item.previous_value = old_value
        item.status = ConfigStatus.ROLLED_BACK
        item.last_updated = time.time()
        self._total_rollbacks += 1

        logger.info(
            "Config rolled back: %s (%s → %s)", sanitize_for_log(key), old_value, item.value
        )
        return True

    # ------------------------------------------------------------------
    # Auto-Configuration
    # ------------------------------------------------------------------

    def auto_configure(self) -> str:
        """
        Auto-detect environment and apply optimal configuration profile.

        Returns the name of the applied profile.
        """
        # Run detections
        self._detection_results = self._detector.detect_all()

        # Determine environment
        system_mode = self._detection_results.get("system_mode")
        environment = self._detection_results.get("environment")

        mode_value = system_mode.value if system_mode and system_mode.detected else "HYBRID"
        env_value = environment.value if environment and environment.detected else "development"

        # Select profile
        profile_name = self._select_profile(mode_value, env_value)
        profile = self._profiles.get(profile_name)

        if not profile:
            logger.warning("No profile found for mode=%s, env=%s", mode_value, env_value)
            return ""

        # Apply profile settings
        self._apply_profile(profile)

        # Apply conditional rules
        self._apply_rules(profile)

        # Store detection results as config
        for name, result in self._detection_results.items():
            self.set(
                f"detection.{name}",
                result.value if result.detected else None,
                source="auto_detect",
                description=f"Auto-detected: {name}",
            )

        logger.info(
            "Auto-configured with profile: %s (mode=%s, env=%s)",
            sanitize_for_log(profile_name),
            mode_value,
            env_value,
        )
        return profile_name

    def _select_profile(self, mode_value: str, env_value: str) -> str:
        """Select the best configuration profile for the detected environment."""
        # Development override
        if env_value == "development":
            return "development"

        # Mode-based selection
        mode_profiles = {
            "TRUE_NAS": "true_nas_production",
            "HYBRID": "hybrid_balanced",
            "CLOUD_ONLY": "cloud_only_zero_cost",
        }
        return mode_profiles.get(mode_value, "hybrid_balanced")

    def _apply_profile(self, profile: ConfigProfile) -> None:
        """Apply all settings from a profile."""
        for key, value in profile.settings.items():
            self.set(key, value, source=f"profile:{profile.name}")

    def _apply_rules(self, profile: ConfigProfile) -> None:
        """Apply conditional rules from a profile."""
        for rule in profile.rules:
            condition = rule.get("condition", "")
            settings = rule.get("settings", {})

            if self._evaluate_condition(condition):
                for key, value in settings.items():
                    self.set(key, value, source=f"rule:{profile.name}")

    def _evaluate_condition(self, condition: str) -> bool:
        """Evaluate a simple condition string (e.g., 'r2_available == true')."""
        try:
            # Simple condition parser: "key == value" or "key != value"
            if " == " in condition:
                key, expected = condition.split(" == ", 1)
                key = key.strip()
                expected = expected.strip().strip("\"'")

                # Check detection results first
                det_key = key.replace("_available", "")
                if det_key in self._detection_results:
                    result = self._detection_results[det_key]
                    return str(result.detected).lower() == expected.lower()

                # Check config items
                item = self._items.get(key)
                if item:
                    return str(item.value).lower() == expected.lower()

            elif " != " in condition:
                key, expected = condition.split(" != ", 1)
                key = key.strip()
                expected = expected.strip().strip("\"'")

                det_key = key.replace("_available", "")
                if det_key in self._detection_results:
                    result = self._detection_results[det_key]
                    return str(result.detected).lower() != expected.lower()

        except Exception as e:
            logger.error(
                "Condition evaluation error for '%s': %s",
                sanitize_for_log(condition),
                sanitize_for_log(str(e)),
            )

        return False

    # ------------------------------------------------------------------
    # Hot Reload
    # ------------------------------------------------------------------

    def hot_reload(self) -> int:
        """
        Hot-reload configuration from environment variables and config file.

        Returns the number of configuration items that were updated.
        """
        updated = 0
        self._last_reload = time.time()
        self._total_reloads += 1

        # 1. Reload from environment variables (TRANC3_ prefix)
        for key, value in os.environ.items():
            if key.startswith("TRANC3_"):
                config_key = key[7:].lower()  # Remove TRANC3_ prefix
                current = self._items.get(config_key)
                if not current or current.value != value:
                    if self.set(config_key, value, source="hot_reload"):
                        updated += 1

        # 2. Reload from config file if available
        if self._config_path and Path(self._config_path).exists():
            try:
                with open(self._config_path, "r") as f:
                    file_config = json.load(f)
                for key, value in file_config.items():
                    current = self._items.get(key)
                    if not current or current.value != value:
                        if self.set(key, value, source="hot_reload"):
                            updated += 1
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Config file reload error: %s", sanitize_for_log(str(e)))

        # 3. Re-run environment detection
        self._detection_results = self._detector.detect_all()

        logger.info("Hot reload completed: %d items updated", updated)
        return updated

    # ------------------------------------------------------------------
    # Change Listeners
    # ------------------------------------------------------------------

    def add_listener(self, callback: Callable) -> None:
        """Register a callback for configuration changes."""
        self._change_listeners.append(callback)

    def remove_listener(self, callback: Callable) -> None:
        """Remove a configuration change listener."""
        self._change_listeners = [
            listener for listener in self._change_listeners if listener != callback
        ]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_config(self) -> Dict[str, Any]:
        """Get the current configuration as a dictionary."""
        return {key: item.value for key, item in self._items.items()}

    def get_config_details(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed configuration with metadata."""
        return {key: item.to_dict() for key, item in self._items.items()}

    def get_detection_results(self) -> Dict[str, Any]:
        """Get the latest environment detection results."""
        return {name: result.to_dict() for name, result in self._detection_results.items()}

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive auto-config statistics."""
        return {
            "config_items": len(self._items),
            "profiles_available": len(self._profiles),
            "detection_results": len(self._detection_results),
            "change_listeners": len(self._change_listeners),
            "total_reloads": self._total_reloads,
            "total_rollbacks": self._total_rollbacks,
            "last_reload": self._last_reload,
            "config_path": self._config_path,
            "items_by_status": {
                status.value: sum(1 for i in self._items.values() if i.status == status)
                for status in ConfigStatus
            },
        }


# Singleton
auto_config = AutoConfigManager()
