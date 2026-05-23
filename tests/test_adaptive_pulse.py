"""
Tests for shared_core.architecture.adaptive_pulse.

Covers: PulseMode, PulseConfig, PulseTransition, PulseMetrics,
AdaptivePulseController.
"""

from __future__ import annotations

from shared_core.architecture.adaptive_pulse import (
    AdaptivePulseController,
    PulseConfig,
    PulseMetrics,
    PulseMode,
    PulseTransition,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestPulseMode:
    def test_all_modes(self):
        assert PulseMode.STEADY.value == "steady"
        assert PulseMode.ACCELERATED.value == "accelerated"
        assert PulseMode.EMERGENCY.value == "emergency"
        assert PulseMode.RECOVERY.value == "recovery"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestPulseConfig:
    def test_create_config(self):
        config = PulseConfig(name="test_daemon", baseline_interval=30.0)
        assert config.name == "test_daemon"
        assert config.baseline_interval == 30.0
        # current_interval should be set to baseline in __post_init__
        assert config.current_interval == 30.0
        assert config.pulse_mode == PulseMode.STEADY

    def test_default_values(self):
        config = PulseConfig(name="test")
        assert config.baseline_interval == 30.0  # _DEFAULT_BASELINE_INTERVAL
        assert config.min_interval == 1.0
        assert config.max_interval == 300.0
        assert config.adaptive_enabled is True

    def test_to_dict(self):
        config = PulseConfig(name="daemon_x", baseline_interval=60.0)
        d = config.to_dict()
        assert d["name"] == "daemon_x"
        assert d["baseline_interval"] == 60.0
        assert d["pulse_mode"] == "steady"


class TestPulseTransition:
    def test_create_transition(self):
        t = PulseTransition(
            from_mode=PulseMode.STEADY,
            to_mode=PulseMode.ACCELERATED,
            reason="load spike",
        )
        assert t.from_mode == PulseMode.STEADY
        assert t.to_mode == PulseMode.ACCELERATED
        assert t.reason == "load spike"

    def test_to_dict(self):
        t = PulseTransition(
            from_mode=PulseMode.EMERGENCY,
            to_mode=PulseMode.RECOVERY,
            reason="health improving",
            health_score=0.7,
        )
        d = t.to_dict()
        assert d["from_mode"] == "emergency"
        assert d["to_mode"] == "recovery"
        assert d["health_score"] == 0.7


class TestPulseMetrics:
    def test_create_metrics(self):
        pm = PulseMetrics()
        assert pm.current_mode == PulseMode.STEADY
        assert pm.total_transitions == 0
        assert pm.daemons_managed == 0

    def test_to_dict(self):
        pm = PulseMetrics(
            current_mode=PulseMode.ACCELERATED,
            total_transitions=5,
            daemons_managed=3,
        )
        d = pm.to_dict()
        assert d["current_mode"] == "accelerated"
        assert d["total_transitions"] == 5
        assert d["daemons_managed"] == 3


# ---------------------------------------------------------------------------
# AdaptivePulseController tests
# ---------------------------------------------------------------------------


class TestAdaptivePulseController:
    def setup_method(self):
        self.controller = AdaptivePulseController()

    def test_initial_mode(self):
        assert self.controller.current_mode == PulseMode.STEADY

    def test_register_daemon(self):
        config = self.controller.register("test_daemon", baseline_interval=60.0)
        assert config.name == "test_daemon"
        assert config.baseline_interval == 60.0

    def test_get_interval_unregistered(self):
        # Unregistered daemon returns global baseline
        interval = self.controller.get_interval("nonexistent")
        assert interval > 0

    def test_get_interval_registered(self):
        self.controller.register("my_daemon", baseline_interval=120.0)
        interval = self.controller.get_interval("my_daemon")
        assert interval == 120.0  # Should start at baseline

    def test_update_to_accelerated(self):
        # health_score below 0.7 threshold triggers ACCELERATED
        new_mode = self.controller.update(health_score=0.5, reason="high load")
        assert new_mode == PulseMode.ACCELERATED

    def test_update_to_emergency(self):
        # health_score below 0.3 threshold triggers EMERGENCY
        new_mode = self.controller.update(health_score=0.2, reason="system failing")
        assert new_mode == PulseMode.EMERGENCY

    def test_update_stays_steady(self):
        new_mode = self.controller.update(health_score=0.95, reason="all good")
        assert new_mode == PulseMode.STEADY

    def test_force_mode(self):
        self.controller.force_mode(PulseMode.EMERGENCY, reason="manual test")
        assert self.controller.current_mode == PulseMode.EMERGENCY

    def test_deregister(self):
        self.controller.register("temp_daemon", baseline_interval=30.0)
        assert self.controller.deregister("temp_daemon") is True
        assert self.controller.deregister("nonexistent") is False

    def test_should_fire_first_time(self):
        self.controller.register("fire_test", baseline_interval=60.0)
        assert self.controller.should_fire("fire_test") is True

    def test_record_fire(self):
        self.controller.register("fire_rec", baseline_interval=60.0)
        self.controller.record_fire("fire_rec")
        config = self.controller.get_config("fire_rec")
        assert config.fire_count == 1

    def test_get_metrics(self):
        self.controller.register("daemon_a", baseline_interval=30.0)
        self.controller.register("daemon_b", baseline_interval=60.0)
        metrics = self.controller.get_metrics()
        assert isinstance(metrics, PulseMetrics)
        assert metrics.daemons_managed >= 3  # 2 registered + pulse_controller

    def test_get_stats(self):
        stats = self.controller.get_stats()
        assert "current_mode" in stats
        assert "daemons" in stats
        assert "metrics" in stats

    def test_get_transition_history(self):
        self.controller.update(0.5, "trigger transition")
        history = self.controller.get_transition_history()
        assert isinstance(history, list)

    def test_get_health_trend(self):
        # Initially not enough data
        trend = self.controller.get_health_trend()
        assert trend in ("stable", "improving", "degrading")
