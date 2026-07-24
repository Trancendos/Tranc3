# src/core/feature_flags.py

import os
from enum import Enum
from typing import Any, Dict, Optional

import redis


class FeatureFlag(Enum):
    QUANTUM_OPTIMIZATION = "quantum_optimization"
    CONSCIOUSNESS_ENGINE = "consciousness_engine"
    NEUROMORPHIC_PROCESSING = "neuromorphic_processing"
    HOLOGRAPHIC_MEMORY = "holographic_memory"
    SELF_EVOLUTION = "self_evolution"
    SWARM_INTELLIGENCE = "swarm_intelligence"


class FeatureFlagManager:
    """
    Centralized feature flag management with Redis backend
    Supports gradual rollouts, A/B testing, and emergency disables
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._load_defaults()

    def _load_defaults(self):
        """Load default feature flag states from environment"""
        defaults = {
            FeatureFlag.QUANTUM_OPTIMIZATION: os.getenv("ENABLE_QUANTUM_OPT", "false").lower()
            == "true",
            FeatureFlag.CONSCIOUSNESS_ENGINE: os.getenv("ENABLE_CONSCIOUSNESS", "false").lower()
            == "true",
            FeatureFlag.NEUROMORPHIC_PROCESSING: os.getenv("ENABLE_NEUROMORPHIC", "false").lower()
            == "true",
            FeatureFlag.HOLOGRAPHIC_MEMORY: os.getenv("ENABLE_HOLOGRAPHIC", "false").lower()
            == "true",
            FeatureFlag.SELF_EVOLUTION: os.getenv("ENABLE_EVOLUTION", "false").lower() == "true",
            FeatureFlag.SWARM_INTELLIGENCE: os.getenv("ENABLE_SWARM", "false").lower() == "true",
        }

        for flag, enabled in defaults.items():
            self.redis.set(f"feature:{flag.value}", "1" if enabled else "0")

    def is_enabled(self, flag: FeatureFlag, user_id: Optional[str] = None) -> bool:
        """
        Check if feature is enabled, with optional user-based rollout
        """
        base_enabled = self.redis.get(f"feature:{flag.value}") == b"1"

        if not base_enabled:
            return False

        # Check percentage rollout
        rollout_key = f"rollout:{flag.value}"
        rollout_pct = int(self.redis.get(rollout_key) or 0)

        if rollout_pct < 100 and user_id:
            # Simple hash-based rollout
            user_hash = hash(user_id) % 100
            return user_hash < rollout_pct

        return rollout_pct == 100 or rollout_pct == 0  # 0 means disabled

    def set_rollout_percentage(self, flag: FeatureFlag, percentage: int):
        """Set percentage rollout for gradual deployment"""
        self.redis.set(f"rollout:{flag.value}", str(min(100, max(0, percentage))))

    def emergency_disable(self, flag: FeatureFlag):
        """Emergency disable a feature"""
        self.redis.set(f"feature:{flag.value}", "0")
        print(f"🚨 EMERGENCY: Disabled {flag.value}")

    def get_all_flags(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all feature flags"""
        flags = {}
        for flag in FeatureFlag:
            enabled = self.redis.get(f"feature:{flag.value}") == b"1"
            rollout = int(self.redis.get(f"rollout:{flag.value}") or 0)
            flags[flag.value] = {"enabled": enabled, "rollout_percentage": rollout}
        return flags


class AlwaysEnabledFeatureManager:
    """
    Redis-free stand-in for FeatureFlagManager. Used by callers that want to
    exercise a feature-flagged subsystem (consciousness engine, self-evolution)
    without wiring up a Redis-backed FeatureFlagManager first — e.g. a one-off
    worker job rather than the main API process.

    Reads the same environment variables FeatureFlagManager._load_defaults()
    seeds Redis from, so operators keep the same on/off control surface (e.g.
    ENABLE_EVOLUTION=false in production) without needing a live Redis
    connection. Real FeatureFlagManager instances remain fully supported for
    callers that need actual rollout/percentage control or a live kill switch.
    """

    _ENV_VARS = {
        FeatureFlag.QUANTUM_OPTIMIZATION: "ENABLE_QUANTUM_OPT",
        FeatureFlag.CONSCIOUSNESS_ENGINE: "ENABLE_CONSCIOUSNESS",
        FeatureFlag.NEUROMORPHIC_PROCESSING: "ENABLE_NEUROMORPHIC",
        FeatureFlag.HOLOGRAPHIC_MEMORY: "ENABLE_HOLOGRAPHIC",
        FeatureFlag.SELF_EVOLUTION: "ENABLE_EVOLUTION",
        FeatureFlag.SWARM_INTELLIGENCE: "ENABLE_SWARM",
    }

    def is_enabled(self, flag: FeatureFlag, user_id: Optional[str] = None) -> bool:  # noqa: ARG002
        env_var = self._ENV_VARS.get(flag)
        if env_var is None:
            return False
        return os.getenv(env_var, "false").lower() == "true"
