"""
Tests for shared_core.architecture.proactive_orchestrator.

Covers: ProactiveAction, ActionPriority, ActionStatus, SystemVitalSign,
OrchestratorMode, MetricSample, HealthPrediction, ActionPlan,
SystemHealthProfile, ZeroCostStatus, PredictiveHealthAnalyzer,
AutoHealingEngine, ZeroCostModulator, ActionDispatcher, ProactiveOrchestrator.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from shared_core.architecture.proactive_orchestrator import (
    ActionDispatcher,
    ActionPlan,
    ActionPriority,
    ActionStatus,
    AutoHealingEngine,
    HealthPrediction,
    MetricSample,
    OrchestratorMode,
    PredictiveHealthAnalyzer,
    ProactiveAction,
    ProactiveOrchestrator,
    SystemHealthProfile,
    SystemVitalSign,
    ZeroCostModulator,
    ZeroCostStatus,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestProactiveAction:
    def test_all_actions_exist(self):
        expected = [
            "HEAL",
            "SCALE_UP",
            "SCALE_DOWN",
            "MIGRATE_STORAGE",
            "REBALANCE",
            "HARDEN",
            "ALERT",
            "RECONFIGURE",
            "QUARANTINE",
        ]
        for name in expected:
            assert hasattr(ProactiveAction, name), f"Missing ProactiveAction.{name}"

    def test_action_values(self):
        assert ProactiveAction.HEAL.value == "heal"
        assert ProactiveAction.QUARANTINE.value == "quarantine"


class TestActionPriority:
    def test_priority_ordering(self):
        assert ActionPriority.CRITICAL < ActionPriority.HIGH
        assert ActionPriority.HIGH < ActionPriority.MEDIUM
        assert ActionPriority.MEDIUM < ActionPriority.LOW
        assert ActionPriority.LOW < ActionPriority.INFORMATIONAL

    def test_priority_values(self):
        assert ActionPriority.CRITICAL.value == 0
        assert ActionPriority.INFORMATIONAL.value == 4


class TestActionStatus:
    def test_all_statuses(self):
        assert ActionStatus.PENDING.value == "pending"
        assert ActionStatus.EXECUTING.value == "executing"
        assert ActionStatus.COMPLETED.value == "completed"
        assert ActionStatus.FAILED.value == "failed"
        assert ActionStatus.ROLLED_BACK.value == "rolled_back"
        assert ActionStatus.CANCELLED.value == "cancelled"


class TestSystemVitalSign:
    def test_all_vital_signs(self):
        expected = [
            "CPU_LOAD",
            "MEMORY_USAGE",
            "STORAGE_CAPACITY",
            "SERVICE_HEALTH",
            "ERROR_RATE",
            "LATENCY",
            "THROUGHPUT",
            "THREAT_LEVEL",
            "CIRCUIT_HEALTH",
            "REGISTRY_HEALTH",
        ]
        for name in expected:
            assert hasattr(SystemVitalSign, name), f"Missing SystemVitalSign.{name}"


class TestOrchestratorMode:
    def test_modes_exist(self):
        assert hasattr(OrchestratorMode, "OBSERVE")
        assert hasattr(OrchestratorMode, "ASSIST")
        assert hasattr(OrchestratorMode, "AUTONOMOUS")
        assert hasattr(OrchestratorMode, "EMERGENCY")

    def test_mode_values(self):
        assert OrchestratorMode.OBSERVE.value == "observe"
        assert OrchestratorMode.AUTONOMOUS.value == "autonomous"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestMetricSample:
    def test_create_sample(self):
        sample = MetricSample(name="cpu", value=0.75)
        assert sample.name == "cpu"
        assert sample.value == 0.75
        assert sample.timestamp > 0
        assert sample.tags == {}

    def test_to_dict(self):
        sample = MetricSample(name="cpu", value=0.75, tags={"host": "a"})
        d = sample.to_dict()
        assert d["name"] == "cpu"
        assert d["value"] == 0.75
        assert d["tags"] == {"host": "a"}


class TestHealthPrediction:
    def test_create_prediction(self):
        hp = HealthPrediction(
            subsystem="storage",
            current_score=0.9,
            predicted_score=0.8,
            trend="degrading",
            confidence=0.7,
            time_to_degradation=120.0,
        )
        assert hp.subsystem == "storage"
        assert hp.trend == "degrading"
        assert hp.horizon_seconds == 300.0  # default

    def test_to_dict(self):
        hp = HealthPrediction(
            subsystem="service",
            current_score=0.8,
            predicted_score=0.6,
            trend="degrading",
            confidence=0.5,
        )
        d = hp.to_dict()
        assert d["subsystem"] == "service"
        assert d["trend"] == "degrading"


class TestActionPlan:
    def test_create_plan(self):
        plan = ActionPlan(
            id="test-1",
            action=ProactiveAction.HEAL,
            priority=ActionPriority.HIGH,
            target="storage",
            description="Heal storage",
        )
        assert plan.id == "test-1"
        assert plan.action == ProactiveAction.HEAL
        assert plan.status == ActionStatus.PENDING

    def test_to_dict(self):
        plan = ActionPlan(
            id="plan-1",
            action=ProactiveAction.ALERT,
            priority=ActionPriority.MEDIUM,
            target="service",
            description="Alert on service",
        )
        d = plan.to_dict()
        assert d["id"] == "plan-1"
        assert d["action"] == "alert"
        assert d["priority_name"] == "MEDIUM"


class TestSystemHealthProfile:
    def test_create_profile(self):
        profile = SystemHealthProfile()
        assert profile.overall_score == 1.0
        assert profile.storage_health == 1.0
        assert profile.active_actions == 0

    def test_to_dict(self):
        profile = SystemHealthProfile(overall_score=0.8, storage_health=0.6)
        d = profile.to_dict()
        assert d["overall_score"] == 0.8
        assert d["storage_health"] == 0.6


class TestZeroCostStatus:
    def test_default_compliant(self):
        status = ZeroCostStatus()
        assert status.compliant is True
        assert status.approaching_limit == []
        assert status.critical_tiers == []

    def test_to_dict(self):
        status = ZeroCostStatus(compliant=False, critical_tiers=["r2"])
        d = status.to_dict()
        assert d["compliant"] is False
        assert d["critical_tiers"] == ["r2"]


# ---------------------------------------------------------------------------
# PredictiveHealthAnalyzer tests
# ---------------------------------------------------------------------------


class TestPredictiveHealthAnalyzer:
    def setup_method(self):
        self.analyzer = PredictiveHealthAnalyzer(window_size=20, smoothing_alpha=0.3)

    def test_predict_empty_history(self):
        hp = self.analyzer.predict("test_subsystem")
        assert hp.subsystem == "test_subsystem"
        assert hp.trend == "stable"
        assert hp.confidence == 0.0

    def test_predict_with_one_sample(self):
        self.analyzer.record("storage", 0.9)
        hp = self.analyzer.predict("storage")
        assert hp.subsystem == "storage"
        assert hp.trend == "stable"  # Not enough data for trend

    def test_predict_with_history(self):
        # Record declining values
        for val in [0.9, 0.8, 0.7, 0.6, 0.5]:
            self.analyzer.record("storage", val)
        hp = self.analyzer.predict("storage")
        assert hp.subsystem == "storage"
        assert hp.trend in ("degrading", "critical")

    def test_record_and_predict(self):
        self.analyzer.record("registry", 0.95)
        self.analyzer.record("registry", 0.93)
        self.analyzer.record("registry", 0.91)
        hp = self.analyzer.predict("registry")
        assert hp.current_score > 0.0

    def test_get_all_predictions(self):
        self.analyzer.record("a", 0.8)
        self.analyzer.record("b", 0.5)
        preds = self.analyzer.get_all_predictions()
        names = {p.subsystem for p in preds}
        assert "a" in names
        assert "b" in names

    def test_get_degrading(self):
        for val in [0.9, 0.7, 0.5, 0.3, 0.1]:
            self.analyzer.record("failing_sub", val)
        degrading = self.analyzer.get_degrading()
        assert any(p.subsystem == "failing_sub" for p in degrading)

    def test_get_stats(self):
        self.analyzer.record("x", 0.5)
        stats = self.analyzer.get_stats()
        assert stats["subsystems_monitored"] == 1
        assert "ema_values" in stats


# ---------------------------------------------------------------------------
# AutoHealingEngine tests
# ---------------------------------------------------------------------------


class TestAutoHealingEngine:
    def setup_method(self):
        self.engine = AutoHealingEngine(max_concurrent=2, max_retries_per_hour=5, enabled=True)

    def test_initial_state(self):
        assert self.engine.enabled is True

    def test_can_heal_enabled(self):
        assert self.engine.can_heal("target_a") is True

    def test_can_heal_disabled(self):
        self.engine.enabled = False
        assert self.engine.can_heal("target_a") is False

    def test_can_heal_max_concurrent(self):
        self.engine.create_heal_action("t1", "test 1", executor=lambda: None)
        self.engine.create_heal_action("t2", "test 2", executor=lambda: None)
        # With max_concurrent=2, third should fail
        assert self.engine.can_heal("t3") is False

    def test_create_heal_action(self):
        plan = self.engine.create_heal_action(
            "storage_tier",
            "Heal storage tier",
            executor=lambda: {"ok": True},
            priority=ActionPriority.HIGH,
        )
        assert plan is not None
        assert plan.action == ProactiveAction.HEAL
        assert plan.target == "storage_tier"
        assert plan.priority == ActionPriority.HIGH

    def test_create_heal_action_rate_limited(self):
        # Create max concurrent actions
        for i in range(2):
            self.engine.create_heal_action(f"t{i}", f"test {i}", executor=lambda: None)
        # Next should be None (rate limited)
        result = self.engine.create_heal_action("t99", "should fail", executor=lambda: None)
        assert result is None

    @pytest.mark.asyncio
    async def test_execute_heal_success(self):
        plan = self.engine.create_heal_action(
            "test_target",
            "Test heal",
            executor=lambda: {"result": "ok"},
        )
        assert plan is not None
        result = await self.engine.execute_heal(plan)
        assert result.status == ActionStatus.COMPLETED
        assert result.result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_execute_heal_failure(self):
        def failing_executor():
            raise RuntimeError("boom")

        plan = self.engine.create_heal_action(
            "failing_target",
            "Failing heal",
            executor=failing_executor,
        )
        assert plan is not None
        result = await self.engine.execute_heal(plan)
        assert result.status == ActionStatus.FAILED
        assert "boom" in result.error

    def test_get_stats(self):
        stats = self.engine.get_stats()
        assert "enabled" in stats
        assert "max_concurrent" in stats
        assert "success_rate" in stats


# ---------------------------------------------------------------------------
# ZeroCostModulator tests
# ---------------------------------------------------------------------------


class TestZeroCostModulator:
    def setup_method(self):
        self.modulator = ZeroCostModulator(safety_margin=0.85)

    def test_check_compliance_no_storage(self):
        status = self.modulator.check_compliance()
        assert status.compliant is True  # No storage attached → compliant

    def test_should_migrate_below_margin(self):
        # Usage at 50% — well below 85% safety margin
        assert self.modulator.should_migrate("r2", 50.0) is False

    def test_should_migrate_above_margin(self):
        # Usage at 90% — above 85% safety margin
        assert self.modulator.should_migrate("r2", 90.0) is True

    def test_record_migration(self):
        self.modulator.record_migration("r2", "oci", success=True, bytes_migrated=1024)
        stats = self.modulator.get_stats()
        assert stats["total_migrations"] == 1
        assert stats["successful_migrations"] == 1

    def test_get_stats(self):
        stats = self.modulator.get_stats()
        assert "safety_margin" in stats
        assert "storage_attached" in stats


# ---------------------------------------------------------------------------
# ActionDispatcher tests
# ---------------------------------------------------------------------------


class TestActionDispatcher:
    def setup_method(self):
        self.dispatcher = ActionDispatcher()

    def test_submit_plan(self):
        plan = ActionPlan(
            id="disp-1",
            action=ProactiveAction.ALERT,
            priority=ActionPriority.MEDIUM,
            target="test",
            description="Test action",
        )
        self.dispatcher.submit(plan)
        pending = self.dispatcher.get_pending()
        assert len(pending) == 1
        assert pending[0]["id"] == "disp-1"

    def test_submit_sorted_by_priority(self):
        low_plan = ActionPlan(
            id="low",
            action=ProactiveAction.ALERT,
            priority=ActionPriority.LOW,
            target="t",
            description="low",
        )
        critical_plan = ActionPlan(
            id="critical",
            action=ProactiveAction.HEAL,
            priority=ActionPriority.CRITICAL,
            target="t",
            description="crit",
        )
        self.dispatcher.submit(low_plan)
        self.dispatcher.submit(critical_plan)
        pending = self.dispatcher.get_pending()
        assert pending[0]["id"] == "critical"  # Higher priority first

    def test_register_handler(self):
        def handler(plan):
            pass

        self.dispatcher.register_handler(ProactiveAction.ALERT, handler)
        stats = self.dispatcher.get_stats()
        assert stats["registered_handlers"]["alert"] == 1

    @pytest.mark.asyncio
    async def test_dispatch_next(self):
        plan = ActionPlan(
            id="dispatch-test",
            action=ProactiveAction.ALERT,
            priority=ActionPriority.HIGH,
            target="svc",
            description="Dispatch test",
        )
        self.dispatcher.submit(plan)
        result = await self.dispatcher.dispatch_next()
        assert result is not None
        assert result.id == "dispatch-test"
        assert result.status == ActionStatus.COMPLETED

    def test_cancel(self):
        plan = ActionPlan(
            id="cancel-me",
            action=ProactiveAction.RECONFIGURE,
            priority=ActionPriority.LOW,
            target="cfg",
            description="Cancel me",
        )
        self.dispatcher.submit(plan)
        assert self.dispatcher.cancel("cancel-me") is True
        assert len(self.dispatcher.get_pending()) == 0

    def test_get_stats(self):
        stats = self.dispatcher.get_stats()
        assert "total_dispatched" in stats
        assert "pending_count" in stats


# ---------------------------------------------------------------------------
# ProactiveOrchestrator tests
# ---------------------------------------------------------------------------


class TestProactiveOrchestrator:
    def setup_method(self):
        self.orch = ProactiveOrchestrator(mode=OrchestratorMode.AUTONOMOUS)

    def test_initial_mode(self):
        assert self.orch.mode == OrchestratorMode.AUTONOMOUS

    def test_set_mode(self):
        self.orch.set_mode(OrchestratorMode.OBSERVE)
        assert self.orch.mode == OrchestratorMode.OBSERVE

    def test_attach_storage(self):
        mock_storage = MagicMock()
        self.orch.attach_storage(mock_storage)

    def test_attach_sentinel(self):
        mock_sentinel = MagicMock()
        self.orch.attach_sentinel(mock_sentinel)

    def test_attach_defense(self):
        mock_defense = MagicMock()
        self.orch.attach_defense(mock_defense)

    def test_attach_event_bus(self):
        mock_bus = MagicMock()
        self.orch.attach_event_bus(mock_bus)

    @pytest.mark.asyncio
    async def test_run_once(self):
        profile = await self.orch.run_once()
        assert isinstance(profile, SystemHealthProfile)
        # With no subsystems, all should be healthy (1.0)
        assert profile.overall_score == 1.0
