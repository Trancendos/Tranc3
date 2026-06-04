"""Feature Flag Service — Phase 12

Dynamic capability toggling with gradual rollouts, A/B testing,
and kill switches. Zero-cost in-memory implementation.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class FlagState(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    KILL_SWITCH = "kill_switch"  # Emergency off — cannot be overridden


class RolloutStrategy(Enum):
    ALL = "all"
    PERCENTAGE = "percentage"
    USER_LIST = "user_list"
    SERVICE_LIST = "service_list"
    GRADUAL = "gradual"
    SCHEDULED = "scheduled"


@dataclass
class FlagRule:
    name: str
    strategy: RolloutStrategy = RolloutStrategy.ALL
    percentage: float = 0.0
    user_ids: Set[str] = field(default_factory=set)
    service_names: Set[str] = field(default_factory=set)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    variant: str = "default"
    priority: int = 0


@dataclass
class FeatureFlag:
    key: str
    name: str
    description: str = ""
    state: FlagState = FlagState.DISABLED
    default_value: Any = False
    rules: List[FlagRule] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    owner: str = ""
    tags: Set[str] = field(default_factory=set)
    version: int = 1


@dataclass
class FlagEvaluation:
    flag_key: str
    enabled: bool
    variant: str = "default"
    reason: str = ""
    rule_name: str = ""
    evaluated_at: float = field(default_factory=time.time)


@dataclass
class FlagAuditEntry:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    flag_key: str = ""
    action: str = ""  # created, updated, enabled, disabled, killed
    old_value: Any = None
    new_value: Any = None
    actor: str = ""
    timestamp: float = field(default_factory=time.time)


class FeatureFlagService:
    """Central feature flag service with rollouts and audit trail."""

    def __init__(self):
        self._flags: Dict[str, FeatureFlag] = {}
        self._audit: List[FlagAuditEntry] = []
        self._change_listeners: List[Callable[[str, FlagState, FlagState], None]] = []

    def initialize(self) -> None:
        # Register core feature flags
        core_flags = [
            ("quantum_solver.enabled", "Quantum Solver", "Enable QAOA/VQE quantum optimization"),
            (
                "chaos_engineering.enabled",
                "Chaos Engineering",
                "Enable fault injection experiments",
            ),
            ("genetic_optimizer.enabled", "Genetic Optimizer", "Enable NSGA-II optimization"),
            ("auto_healing.enabled", "Auto Healing", "Enable proactive self-repair"),
            (
                "predictive_scaling.enabled",
                "Predictive Scaling",
                "Enable anticipatory resource provisioning",
            ),
            (
                "circuit_breaker.enabled",
                "Circuit Breaker Mesh",
                "Enable inter-service fault tolerance",
            ),
            ("event_sourcing.enabled", "Event Sourcing", "Enable CQRS event sourcing"),
            ("neural_symbolic.enabled", "Neural Symbolic", "Enable neural-symbolic reasoning"),
            ("consciousness.enabled", "Consciousness Field", "Enable IIT consciousness simulation"),
            ("bio_synthetic.enabled", "Bio Synthetic", "Enable synthetic biology simulation"),
        ]
        for key, name, desc in core_flags:
            self.create_flag(key, name, desc, state=FlagState.ENABLED)

        logger.info("FeatureFlagService initialized with %d core flags", len(core_flags))

    def create_flag(
        self,
        key: str,
        name: str,
        description: str = "",
        state: FlagState = FlagState.DISABLED,
        default_value: Any = False,
        owner: str = "",
    ) -> FeatureFlag:
        if key in self._flags:
            return self._flags[key]
        flag = FeatureFlag(
            key=key,
            name=name,
            description=description,
            state=state,
            default_value=default_value,
            owner=owner,
        )
        self._flags[key] = flag
        self._audit_action(key, "created", None, state.value, owner)
        logger.info("Created feature flag: %s (%s)", key, state.value)
        return flag

    def evaluate(self, flag_key: str, context: Optional[Dict[str, Any]] = None) -> FlagEvaluation:
        flag = self._flags.get(flag_key)
        if not flag:
            return FlagEvaluation(flag_key=flag_key, enabled=False, reason="flag_not_found")

        # Kill switch overrides everything
        if flag.state == FlagState.KILL_SWITCH:
            return FlagEvaluation(
                flag_key=flag_key,
                enabled=False,
                reason="kill_switch",
                variant="disabled",
            )

        # Disabled state
        if flag.state == FlagState.DISABLED:
            # Check if any rule overrides for specific users/services
            if context:
                for rule in flag.rules:
                    if rule.strategy == RolloutStrategy.USER_LIST:
                        user_id = context.get("user_id", "")
                        if user_id in rule.user_ids:
                            return FlagEvaluation(
                                flag_key=flag_key,
                                enabled=True,
                                reason="user_override",
                                rule_name=rule.name,
                                variant=rule.variant,
                            )
                    if rule.strategy == RolloutStrategy.SERVICE_LIST:
                        service = context.get("service_name", "")
                        if service in rule.service_names:
                            return FlagEvaluation(
                                flag_key=flag_key,
                                enabled=True,
                                reason="service_override",
                                rule_name=rule.name,
                                variant=rule.variant,
                            )
            return FlagEvaluation(flag_key=flag_key, enabled=False, reason="disabled")

        # Enabled — check rules
        if not flag.rules:
            return FlagEvaluation(flag_key=flag_key, enabled=True, reason="enabled_no_rules")

        ctx = context or {}
        for rule in sorted(flag.rules, key=lambda r: -r.priority):
            result = self._evaluate_rule(rule, ctx, flag_key)
            if result is not None:
                return result

        return FlagEvaluation(
            flag_key=flag_key,
            enabled=True,
            reason="enabled_default",
            variant="default",
        )

    def _evaluate_rule(
        self,
        rule: FlagRule,
        context: Dict[str, Any],
        flag_key: str,
    ) -> Optional[FlagEvaluation]:
        if rule.strategy == RolloutStrategy.ALL:
            return FlagEvaluation(
                flag_key=flag_key,
                enabled=True,
                reason="rule_all",
                variant=rule.variant,
                rule_name=rule.name,
            )

        if rule.strategy == RolloutStrategy.PERCENTAGE:
            user_id = context.get("user_id", str(random.random()))
            bucket = self._hash_bucket(f"{flag_key}:{user_id}")
            if bucket < rule.percentage / 100.0:
                return FlagEvaluation(
                    flag_key=flag_key,
                    enabled=True,
                    reason="rule_percentage",
                    variant=rule.variant,
                    rule_name=rule.name,
                )
            return FlagEvaluation(
                flag_key=flag_key,
                enabled=False,
                reason="rule_percentage_excluded",
                rule_name=rule.name,
            )

        if rule.strategy == RolloutStrategy.USER_LIST:
            if context.get("user_id", "") in rule.user_ids:
                return FlagEvaluation(
                    flag_key=flag_key,
                    enabled=True,
                    reason="rule_user_list",
                    variant=rule.variant,
                    rule_name=rule.name,
                )
            return None  # Fall through to next rule

        if rule.strategy == RolloutStrategy.SERVICE_LIST:
            if context.get("service_name", "") in rule.service_names:
                return FlagEvaluation(
                    flag_key=flag_key,
                    enabled=True,
                    reason="rule_service_list",
                    variant=rule.variant,
                    rule_name=rule.name,
                )
            return None

        if rule.strategy == RolloutStrategy.GRADUAL:
            elapsed = time.time() - (rule.start_time or time.time())
            duration = (rule.end_time or time.time() + 3600) - (rule.start_time or time.time())
            if duration > 0:
                progress = min(1.0, elapsed / duration)
                user_id = context.get("user_id", str(random.random()))
                bucket = self._hash_bucket(f"{flag_key}:{user_id}")
                if bucket < progress:
                    return FlagEvaluation(
                        flag_key=flag_key,
                        enabled=True,
                        reason="rule_gradual",
                        variant=rule.variant,
                        rule_name=rule.name,
                    )
            return None

        if rule.strategy == RolloutStrategy.SCHEDULED:
            now = time.time()
            if rule.start_time and now < rule.start_time:
                return FlagEvaluation(
                    flag_key=flag_key,
                    enabled=False,
                    reason="rule_scheduled_not_started",
                    rule_name=rule.name,
                )
            if rule.end_time and now > rule.end_time:
                return FlagEvaluation(
                    flag_key=flag_key,
                    enabled=False,
                    reason="rule_scheduled_expired",
                    rule_name=rule.name,
                )
            return FlagEvaluation(
                flag_key=flag_key,
                enabled=True,
                reason="rule_scheduled_active",
                variant=rule.variant,
                rule_name=rule.name,
            )

        return None

    def _hash_bucket(self, key: str) -> float:
        h = hashlib.sha256(key.encode()).hexdigest()
        return int(h[:8], 16) / 0xFFFFFFFF

    def enable_flag(self, key: str, actor: str = "") -> bool:
        return self._set_state(key, FlagState.ENABLED, actor)

    def disable_flag(self, key: str, actor: str = "") -> bool:
        return self._set_state(key, FlagState.DISABLED, actor)

    def kill_flag(self, key: str, actor: str = "") -> bool:
        return self._set_state(key, FlagState.KILL_SWITCH, actor)

    def _set_state(self, key: str, new_state: FlagState, actor: str) -> bool:
        flag = self._flags.get(key)
        if not flag:
            return False
        old_state = flag.state
        flag.state = new_state
        flag.updated_at = time.time()
        flag.version += 1
        self._audit_action(key, new_state.value, old_state.value, new_state.value, actor)
        for listener in self._change_listeners:
            try:
                listener(key, old_state, new_state)
            except Exception:
                pass
        return True

    def add_rule(self, flag_key: str, rule: FlagRule) -> bool:
        flag = self._flags.get(flag_key)
        if not flag:
            return False
        flag.rules.append(rule)
        flag.updated_at = time.time()
        flag.version += 1
        self._audit_action(flag_key, "rule_added", None, rule.name)
        return True

    def _audit_action(
        self,
        flag_key: str,
        action: str,
        old_value: Any = None,
        new_value: Any = None,
        actor: str = "",
    ) -> None:
        self._audit.append(
            FlagAuditEntry(
                flag_key=flag_key,
                action=action,
                old_value=old_value,
                new_value=new_value,
                actor=actor,
            ),
        )

    def get_flag(self, key: str) -> Optional[FeatureFlag]:
        return self._flags.get(key)

    def get_all_flags(self) -> Dict[str, FeatureFlag]:
        return dict(self._flags)

    def get_audit_trail(self, flag_key: str = "", limit: int = 100) -> List[FlagAuditEntry]:
        entries = self._audit
        if flag_key:
            entries = [e for e in entries if e.flag_key == flag_key]
        return entries[-limit:]

    def add_change_listener(self, listener: Callable[[str, FlagState, FlagState], None]) -> None:
        self._change_listeners.append(listener)

    def gradual_rollout(
        self,
        flag_key: str,
        start_time: float,
        end_time: float,
        actor: str = "",
    ) -> bool:
        flag = self._flags.get(flag_key)
        if not flag:
            return False
        flag.state = FlagState.ENABLED
        flag.rules.append(
            FlagRule(
                name="gradual_rollout",
                strategy=RolloutStrategy.GRADUAL,
                start_time=start_time,
                end_time=end_time,
                priority=100,
            ),
        )
        flag.updated_at = time.time()
        self._audit_action(
            flag_key,
            "gradual_rollout_started",
            None,
            f"{start_time}-{end_time}",
            actor,
        )
        return True
