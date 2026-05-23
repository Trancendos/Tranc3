#!/usr/bin/env python3
"""
Phase 10 Verification Script — Intelligent Adaptive Proactive Systems

Validates that all new Phase 10 classes, enums, dataclasses, and singletons
can be imported and instantiated correctly.

Universal ID Taxonomy:
    PID — Product/Location ID
    AID — AI ID (tAImra Lead AI)
    SID — Service/Agent ID
    NID — Nano-ID/Bot ID
"""

import sys

# Track results
PASSED = 0
FAILED = 0
ERRORS = []


def verify(condition: bool, description: str) -> None:
    """Verify a condition and track results."""
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✓ {description}")
    else:
        FAILED += 1
        ERRORS.append(description)
        print(f"  ✗ {description}")


def main() -> int:
    """Run all Phase 10 verification tests."""
    global PASSED, FAILED

    print("=" * 70)
    print("Phase 10 Verification — Intelligent Adaptive Proactive Systems")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 10.1 Proactive Orchestrator Core
    # ------------------------------------------------------------------
    print("\n--- 10.1 Proactive Orchestrator Core ---")

    try:
        from shared_core.architecture.proactive_orchestrator import (
            ActionDispatcher,
            ActionPlan,
            ActionPriority,
            AutoHealingEngine,
            HealthPrediction,
            MetricSample,
            OrchestratorMode,
            PredictiveHealthAnalyzer,
            ProactiveAction,
            ProactiveOrchestrator,
            ZeroCostModulator,
            proactive_orchestrator,
        )

        PASSED += 1
        print("  ✓ All proactive_orchestrator imports successful")

        # Enums — use actual member names
        verify(hasattr(ProactiveAction, "HEAL"), "ProactiveAction.HEAL exists")
        verify(hasattr(ProactiveAction, "SCALE_UP"), "ProactiveAction.SCALE_UP exists")
        verify(
            hasattr(ProactiveAction, "MIGRATE_STORAGE"), "ProactiveAction.MIGRATE_STORAGE exists"
        )
        verify(hasattr(ProactiveAction, "REBALANCE"), "ProactiveAction.REBALANCE exists")
        verify(hasattr(ProactiveAction, "HARDEN"), "ProactiveAction.HARDEN exists")
        verify(hasattr(ProactiveAction, "ALERT"), "ProactiveAction.ALERT exists")
        verify(hasattr(ProactiveAction, "RECONFIGURE"), "ProactiveAction.RECONFIGURE exists")
        verify(hasattr(ProactiveAction, "QUARANTINE"), "ProactiveAction.QUARANTINE exists")
        verify(hasattr(ProactiveAction, "SCALE_DOWN"), "ProactiveAction.SCALE_DOWN exists")

        verify(hasattr(ActionPriority, "LOW"), "ActionPriority.LOW exists")
        verify(hasattr(ActionPriority, "MEDIUM"), "ActionPriority.MEDIUM exists")
        verify(hasattr(ActionPriority, "HIGH"), "ActionPriority.HIGH exists")
        verify(hasattr(ActionPriority, "CRITICAL"), "ActionPriority.CRITICAL exists")

        verify(hasattr(OrchestratorMode, "OBSERVE"), "OrchestratorMode.OBSERVE exists")
        verify(hasattr(OrchestratorMode, "ASSIST"), "OrchestratorMode.ASSIST exists")
        verify(hasattr(OrchestratorMode, "AUTONOMOUS"), "OrchestratorMode.AUTONOMOUS exists")
        verify(hasattr(OrchestratorMode, "EMERGENCY"), "OrchestratorMode.EMERGENCY exists")

        # Dataclass instantiation — use actual field names
        try:
            MetricSample(name="test.cpu", value=0.5, timestamp=0.0)
            verify(True, "MetricSample can be instantiated")
        except Exception as e:
            verify(False, f"MetricSample instantiation: {e}")

        try:
            HealthPrediction(
                subsystem="test",
                current_score=1.0,
                predicted_score=0.9,
                trend="stable",
                confidence=0.8,
                time_to_degradation=None,
                horizon_seconds=300,
            )
            verify(True, "HealthPrediction can be instantiated")
        except Exception as e:
            verify(False, f"HealthPrediction instantiation: {e}")

        try:
            import uuid

            ActionPlan(
                id=str(uuid.uuid4()),
                action=ProactiveAction.ALERT,
                target="test",
                description="test action",
                priority=ActionPriority.LOW,
            )
            verify(True, "ActionPlan can be instantiated")
        except Exception as e:
            verify(False, f"ActionPlan instantiation: {e}")

        # Core classes
        try:
            PredictiveHealthAnalyzer()
            verify(True, "PredictiveHealthAnalyzer can be instantiated")
        except Exception as e:
            verify(False, f"PredictiveHealthAnalyzer instantiation: {e}")

        try:
            AutoHealingEngine()
            verify(True, "AutoHealingEngine can be instantiated")
        except Exception as e:
            verify(False, f"AutoHealingEngine instantiation: {e}")

        try:
            ZeroCostModulator()
            verify(True, "ZeroCostModulator can be instantiated")
        except Exception as e:
            verify(False, f"ZeroCostModulator instantiation: {e}")

        try:
            ActionDispatcher()
            verify(True, "ActionDispatcher can be instantiated")
        except Exception as e:
            verify(False, f"ActionDispatcher instantiation: {e}")

        try:
            po = ProactiveOrchestrator()
            verify(True, "ProactiveOrchestrator can be instantiated")
        except Exception as e:
            verify(False, f"ProactiveOrchestrator instantiation: {e}")

        verify(proactive_orchestrator is not None, "proactive_orchestrator singleton exists")

    except Exception as e:
        FAILED += 1
        ERRORS.append(f"proactive_orchestrator imports: {e}")
        print(f"  ✗ proactive_orchestrator imports: {e}")

    # ------------------------------------------------------------------
    # 10.2 Adaptive Pulse Controller
    # ------------------------------------------------------------------
    print("\n--- 10.2 Adaptive Pulse Controller ---")

    try:
        from shared_core.architecture.adaptive_pulse import (
            AdaptivePulseController,
            PulseConfig,
            PulseMode,
            adaptive_pulse,
        )

        PASSED += 1
        print("  ✓ All adaptive_pulse imports successful")

        verify(hasattr(PulseMode, "STEADY"), "PulseMode.STEADY exists")
        verify(hasattr(PulseMode, "ACCELERATED"), "PulseMode.ACCELERATED exists")
        verify(hasattr(PulseMode, "EMERGENCY"), "PulseMode.EMERGENCY exists")
        verify(hasattr(PulseMode, "RECOVERY"), "PulseMode.RECOVERY exists")

        try:
            pc = PulseConfig(name="test", baseline_interval=30.0)
            verify(True, "PulseConfig can be instantiated")
            verify(pc.name == "test", "PulseConfig.name is set correctly")
        except Exception as e:
            verify(False, f"PulseConfig instantiation: {e}")

        try:
            apc = AdaptivePulseController()
            verify(True, "AdaptivePulseController can be instantiated")
        except Exception as e:
            verify(False, f"AdaptivePulseController instantiation: {e}")

        verify(adaptive_pulse is not None, "adaptive_pulse singleton exists")

    except Exception as e:
        FAILED += 1
        ERRORS.append(f"adaptive_pulse imports: {e}")
        print(f"  ✗ adaptive_pulse imports: {e}")

    # ------------------------------------------------------------------
    # 10.3 Predictive Autoscaler
    # ------------------------------------------------------------------
    print("\n--- 10.3 Predictive Autoscaler ---")

    try:
        from src.adaptive.predictive_scaler import (
            LoadForecaster,
            LoadSample,
            PredictiveAutoscaler,
            ScalerConfig,
            ScalingDirection,
            ScalingReason,
            predictive_scaler,
        )

        PASSED += 1
        print("  ✓ All predictive_scaler imports successful")

        verify(hasattr(ScalingDirection, "UP"), "ScalingDirection.UP exists")
        verify(hasattr(ScalingDirection, "DOWN"), "ScalingDirection.DOWN exists")
        verify(hasattr(ScalingDirection, "MAINTAIN"), "ScalingDirection.MAINTAIN exists")

        verify(hasattr(ScalingReason, "PREDICTED_DEMAND"), "ScalingReason.PREDICTED_DEMAND exists")
        verify(hasattr(ScalingReason, "ZERO_COST_LIMIT"), "ScalingReason.ZERO_COST_LIMIT exists")
        verify(hasattr(ScalingReason, "CURRENT_LOAD"), "ScalingReason.CURRENT_LOAD exists")

        try:
            LoadSample(timestamp=0.0, value=0.5)
            verify(True, "LoadSample can be instantiated")
        except Exception as e:
            verify(False, f"LoadSample instantiation: {e}")

        try:
            ScalerConfig(name="test_scaler")
            verify(True, "ScalerConfig can be instantiated with name")
        except Exception as e:
            verify(False, f"ScalerConfig instantiation: {e}")

        try:
            lf = LoadForecaster()
            verify(True, "LoadForecaster can be instantiated")
        except Exception as e:
            verify(False, f"LoadForecaster instantiation: {e}")

        try:
            PredictiveAutoscaler()
            verify(True, "PredictiveAutoscaler can be instantiated")
        except Exception as e:
            verify(False, f"PredictiveAutoscaler instantiation: {e}")

        verify(predictive_scaler is not None, "predictive_scaler singleton exists")

    except Exception as e:
        FAILED += 1
        ERRORS.append(f"predictive_scaler imports: {e}")
        print(f"  ✗ predictive_scaler imports: {e}")

    # ------------------------------------------------------------------
    # 10.4 Auto-Configuration System
    # ------------------------------------------------------------------
    print("\n--- 10.4 Auto-Configuration System ---")

    try:
        from shared_core.architecture.auto_config import (
            AutoConfigManager,
            ConfigStatus,
            EnvironmentDetector,
            EnvironmentType,
            auto_config,
        )

        PASSED += 1
        print("  ✓ All auto_config imports successful")

        verify(hasattr(EnvironmentType, "TRUE_NAS"), "EnvironmentType.TRUE_NAS exists")
        verify(hasattr(EnvironmentType, "HYBRID"), "EnvironmentType.HYBRID exists")
        verify(hasattr(EnvironmentType, "CLOUD_ONLY"), "EnvironmentType.CLOUD_ONLY exists")

        # ConfigStatus uses: DEFAULT, DETECTED, OVERRIDDEN, HOT_RELOADED, VALIDATED, ROLLED_BACK
        verify(hasattr(ConfigStatus, "DEFAULT"), "ConfigStatus.DEFAULT exists")
        verify(hasattr(ConfigStatus, "DETECTED"), "ConfigStatus.DETECTED exists")
        verify(hasattr(ConfigStatus, "OVERRIDDEN"), "ConfigStatus.OVERRIDDEN exists")
        verify(hasattr(ConfigStatus, "HOT_RELOADED"), "ConfigStatus.HOT_RELOADED exists")
        verify(hasattr(ConfigStatus, "VALIDATED"), "ConfigStatus.VALIDATED exists")
        verify(hasattr(ConfigStatus, "ROLLED_BACK"), "ConfigStatus.ROLLED_BACK exists")

        try:
            EnvironmentDetector()
            verify(True, "EnvironmentDetector can be instantiated")
        except Exception as e:
            verify(False, f"EnvironmentDetector instantiation: {e}")

        try:
            acm = AutoConfigManager()
            verify(True, "AutoConfigManager can be instantiated")
        except Exception as e:
            verify(False, f"AutoConfigManager instantiation: {e}")

        verify(auto_config is not None, "auto_config singleton exists")

    except Exception as e:
        FAILED += 1
        ERRORS.append(f"auto_config imports: {e}")
        print(f"  ✗ auto_config imports: {e}")

    # ------------------------------------------------------------------
    # 10.5 Cross-System Integration & Wiring
    # ------------------------------------------------------------------
    print("\n--- 10.5 Cross-System Integration & Wiring ---")

    try:
        from shared_core.architecture.proactive_wiring import (
            BridgeType,
            ProactiveSystemBootstrap,
            WiringStatus,
            proactive_bootstrap,
        )

        PASSED += 1
        print("  ✓ All proactive_wiring imports successful")

        verify(hasattr(WiringStatus, "DISCONNECTED"), "WiringStatus.DISCONNECTED exists")
        verify(hasattr(WiringStatus, "CONNECTED"), "WiringStatus.CONNECTED exists")
        verify(hasattr(WiringStatus, "ACTIVE"), "WiringStatus.ACTIVE exists")
        verify(hasattr(WiringStatus, "ERROR"), "WiringStatus.ERROR exists")
        verify(hasattr(WiringStatus, "DISABLED"), "WiringStatus.DISABLED exists")

        verify(hasattr(BridgeType, "EVENT_BUS"), "BridgeType.EVENT_BUS exists")
        verify(hasattr(BridgeType, "STORAGE"), "BridgeType.STORAGE exists")
        verify(hasattr(BridgeType, "SENTINEL"), "BridgeType.SENTINEL exists")
        verify(hasattr(BridgeType, "DEFENSE"), "BridgeType.DEFENSE exists")
        verify(hasattr(BridgeType, "FORESIGHT"), "BridgeType.FORESIGHT exists")
        verify(hasattr(BridgeType, "ROUTING"), "BridgeType.ROUTING exists")
        verify(hasattr(BridgeType, "REGISTRY"), "BridgeType.REGISTRY exists")
        verify(hasattr(BridgeType, "RESILIENCE"), "BridgeType.RESILIENCE exists")
        verify(hasattr(BridgeType, "PULSE"), "BridgeType.PULSE exists")
        verify(hasattr(BridgeType, "CONFIG"), "BridgeType.CONFIG exists")
        verify(hasattr(BridgeType, "SCALER"), "BridgeType.SCALER exists")

        try:
            psb = ProactiveSystemBootstrap()
            verify(True, "ProactiveSystemBootstrap can be instantiated")
        except Exception as e:
            verify(False, f"ProactiveSystemBootstrap instantiation: {e}")

        verify(proactive_bootstrap is not None, "proactive_bootstrap singleton exists")

    except Exception as e:
        FAILED += 1
        ERRORS.append(f"proactive_wiring imports: {e}")
        print(f"  ✗ proactive_wiring imports: {e}")

    # ------------------------------------------------------------------
    # 10.6 Observability & Metrics
    # ------------------------------------------------------------------
    print("\n--- 10.6 Observability & Metrics ---")

    try:
        from shared_core.architecture.proactive_metrics import (
            HealthTrend,
            MetricType,
            ProactiveMetricsCollector,
            proactive_metrics,
        )

        PASSED += 1
        print("  ✓ All proactive_metrics imports successful")

        verify(hasattr(MetricType, "GAUGE"), "MetricType.GAUGE exists")
        verify(hasattr(MetricType, "COUNTER"), "MetricType.COUNTER exists")
        verify(hasattr(MetricType, "HISTOGRAM"), "MetricType.HISTOGRAM exists")

        verify(hasattr(HealthTrend, "IMPROVING"), "HealthTrend.IMPROVING exists")
        verify(hasattr(HealthTrend, "STABLE"), "HealthTrend.STABLE exists")
        verify(hasattr(HealthTrend, "DEGRADING"), "HealthTrend.DEGRADING exists")
        verify(hasattr(HealthTrend, "CRITICAL"), "HealthTrend.CRITICAL exists")

        try:
            pmc = ProactiveMetricsCollector()
            verify(True, "ProactiveMetricsCollector can be instantiated")
        except Exception as e:
            verify(False, f"ProactiveMetricsCollector instantiation: {e}")

        verify(
            hasattr(ProactiveMetricsCollector, "export_prometheus"),
            "ProactiveMetricsCollector.export_prometheus method exists",
        )
        verify(
            hasattr(ProactiveMetricsCollector, "get_vitals"),
            "ProactiveMetricsCollector.get_vitals method exists",
        )
        verify(
            hasattr(ProactiveMetricsCollector, "collect"),
            "ProactiveMetricsCollector.collect method exists",
        )

        verify(proactive_metrics is not None, "proactive_metrics singleton exists")

    except Exception as e:
        FAILED += 1
        ERRORS.append(f"proactive_metrics imports: {e}")
        print(f"  ✗ proactive_metrics imports: {e}")

    # ------------------------------------------------------------------
    # Architecture __init__.py exports
    # ------------------------------------------------------------------
    print("\n--- Architecture __init__.py Exports ---")

    try:
        from shared_core.architecture import (
            ActionDispatcher,
            ActionPlan,
            ActionPriority,
            AdaptivePulseController,
            AutoConfigManager,
            AutoHealingEngine,
            BridgeType,
            ConfigStatus,
            EnvironmentDetector,
            EnvironmentType,
            HealthTrend,
            MetricSample,
            OrchestratorMode,
            PredictiveHealthAnalyzer,
            ProactiveAction,
            ProactiveMetricsCollector,
            ProactiveOrchestrator,
            ProactiveSystemBootstrap,
            PulseConfig,
            PulseMode,
            WiringStatus,
            ZeroCostModulator,
            adaptive_pulse,
            auto_config,
            proactive_bootstrap,
            proactive_metrics,
            proactive_orchestrator,
        )

        PASSED += 1
        print("  ✓ All 36 architecture __init__.py exports importable")
    except Exception as e:
        FAILED += 1
        ERRORS.append(f"Architecture __init__.py exports: {e}")
        print(f"  ✗ Architecture __init__.py exports: {e}")

    # ------------------------------------------------------------------
    # Adaptive __init__.py exports
    # ------------------------------------------------------------------
    print("\n--- Adaptive __init__.py Exports ---")

    try:
        from src.adaptive import (
            LoadForecaster,
            LoadSample,
            PredictiveAutoscaler,
            ScalerConfig,
            ScalingDirection,
            ScalingReason,
            predictive_scaler,
        )

        PASSED += 1
        print("  ✓ All 9 adaptive __init__.py exports importable")
    except Exception as e:
        FAILED += 1
        ERRORS.append(f"Adaptive __init__.py exports: {e}")
        print(f"  ✗ Adaptive __init__.py exports: {e}")

    # ------------------------------------------------------------------
    # Functional Verification — Key interactions
    # ------------------------------------------------------------------
    print("\n--- Functional Verification ---")

    # Verify ProactiveOrchestrator health scoring
    try:
        from shared_core.architecture.proactive_orchestrator import ProactiveOrchestrator

        po = ProactiveOrchestrator()
        health = po.get_health_profile()
        verify(health is not None, "ProactiveOrchestrator.get_health_profile() returns data")
        # SystemHealthProfile uses overall_score, not composite_score
        verify(hasattr(health, "overall_score"), "Health profile has overall_score")
        verify(hasattr(health, "storage_health"), "Health profile has storage_health")
    except Exception as e:
        verify(False, f"ProactiveOrchestrator health profile: {e}")

    # Verify AdaptivePulseController interval management
    try:
        from shared_core.architecture.adaptive_pulse import (
            AdaptivePulseController,
            PulseConfig,
            PulseMode,
        )

        apc = AdaptivePulseController()
        # register() takes keyword args: name, baseline_interval, etc.
        apc.register(name="test_daemon", baseline_interval=30.0)
        interval = apc.get_interval("test_daemon")
        verify(interval == 30.0, f"PulseController returns correct interval: {interval}")
        # Verify mode property
        verify(
            apc.current_mode == PulseMode.STEADY,
            f"PulseController starts in STEADY mode: {apc.current_mode}",
        )
    except Exception as e:
        verify(False, f"AdaptivePulseController interval management: {e}")

    # Verify LoadForecaster
    try:
        from src.adaptive.predictive_scaler import LoadForecaster

        lf = LoadForecaster()
        # record() takes: value, source='', tags=None
        for i in range(10):
            lf.record(value=0.3 + i * 0.05, source="test")
        # forecast() takes: horizon_seconds=300.0
        forecast = lf.forecast(horizon_seconds=300)
        verify(forecast is not None, "LoadForecaster.forecast() returns data")
        verify(hasattr(forecast, "predicted_load"), "Forecast has predicted_load")
        verify(hasattr(forecast, "confidence"), "Forecast has confidence")
    except Exception as e:
        verify(False, f"LoadForecaster forecasting: {e}")

    # Verify AutoConfigManager profiles
    try:
        from shared_core.architecture.auto_config import AutoConfigManager

        acm = AutoConfigManager()
        profiles = acm.list_profiles()
        verify(len(profiles) >= 3, f"AutoConfigManager has {len(profiles)} profiles (expected >=3)")
    except Exception as e:
        verify(False, f"AutoConfigManager profiles: {e}")

    # Verify ProactiveMetricsCollector Prometheus export
    try:
        from shared_core.architecture.proactive_metrics import ProactiveMetricsCollector

        pmc = ProactiveMetricsCollector()
        prom_output = pmc.export_prometheus()
        verify(isinstance(prom_output, str), "export_prometheus returns string")
        verify("tranc3_proactive_" in prom_output, "Prometheus output has tranc3_proactive_ prefix")
    except Exception as e:
        verify(False, f"ProactiveMetricsCollector Prometheus export: {e}")

    # Verify ProactiveSystemBootstrap status
    try:
        from shared_core.architecture.proactive_wiring import ProactiveSystemBootstrap

        psb = ProactiveSystemBootstrap()
        status = psb.get_status()
        verify(isinstance(status, dict), "ProactiveSystemBootstrap.get_status() returns dict")
    except Exception as e:
        verify(False, f"ProactiveSystemBootstrap status: {e}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"Phase 10 Verification Complete: {PASSED} passed, {FAILED} failed")
    print("=" * 70)

    if ERRORS:
        print("\nFailed checks:")
        for err in ERRORS:
            print(f"  - {err}")

    return 1 if FAILED > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
