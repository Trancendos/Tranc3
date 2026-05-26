# Proactive Systems Architecture

**Module:** `Dimensional/architecture/` + `src/adaptive/`
**Phase:** 10 (Intelligent Adaptive Proactive Systems)
**Last Updated:** May 23, 2026

---

## Overview

The Proactive Systems architecture enables the Tranc3 platform to autonomously anticipate, detect, and respond to system health issues, cost constraints, and workload changes without manual intervention. The system operates on a continuous observe-analyze-act loop, with four modes of autonomy ranging from passive observation to emergency response.

## Module Map

| Module | Location | Purpose |
|--------|----------|---------|
| `proactive_orchestrator.py` | `Dimensional/architecture/` | Central decision engine, health analysis, healing, zero-cost enforcement |
| `adaptive_pulse.py` | `Dimensional/architecture/` | Dynamic heartbeat control based on system health |
| `auto_config.py` | `Dimensional/architecture/` | Environment-aware configuration with hot-reload |
| `proactive_metrics.py` | `Dimensional/architecture/` | Unified metrics collection and Prometheus export |
| `proactive_wiring.py` | `Dimensional/architecture/` | Component lifecycle and bridge connection management |
| `predictive_scaler.py` | `src/adaptive/` | Load forecasting and zero-cost-constrained autoscaling |

## Data Flow

```
External Events ─────────────────────┐
                                     │
Storage Health ──────────────────────┤
                                     ▼
                         ┌───────────────────────┐
                         │  ProactiveMetrics-    │
                         │  Collector            │
                         │  (collect vitals,     │
                         │   export Prometheus)  │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │  ProactiveOrchestrator│
                         │  (observe→analyze→    │
                         │   plan→act cycle)     │
                         └───────────┬───────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │ AutoHealingEngine│  │ ZeroCostModulator│  │ ActionDispatcher │
   │ (create_heal_    │  │ (check_compliance│  │ (submit,         │
   │  action, track   │  │  should_migrate, │  │  dispatch_next,  │
   │  active heals)   │  │  record_migration│  │  register_handler│
   └──────────────────┘  └──────────────────┘  └──────────────────┘
              │                      │                      │
              ▼                      ▼                      ▼
   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │ AdaptivePulse-   │  │ PredictiveAuto-  │  │ AutoConfigManager│
   │ Controller       │  │ scaler           │  │ (auto_configure, │
   │ (update health,  │  │ (forecast load,  │  │  hot_reload,     │
   │  force mode,     │  │  evaluate scale  │  │  rollback)       │
   │  adjust interval)│  │  decisions)      │  │                  │
   └──────────────────┘  └──────────────────┘  └──────────────────┘
```

## Component Details

### ProactiveOrchestrator

The central decision engine that coordinates all proactive actions. It operates in one of four modes:

| Mode | Description |
|------|-------------|
| OBSERVE | Passive monitoring, no actions taken |
| ASSIST | Suggests actions but waits for approval |
| AUTONOMOUS | Executes actions without human approval |
| EMERGENCY | Critical response mode with highest priority |

**Key Classes:**

- `PredictiveHealthAnalyzer`: Records subsystem health scores and produces `HealthPrediction` forecasts with trend analysis and confidence scores
- `AutoHealingEngine`: Creates and tracks healing `ActionPlan` instances with rollback support, priority queuing, and execution statistics
- `ZeroCostModulator`: Enforces zero-cost mandate by checking storage compliance, evaluating tier migration needs, and recording migration outcomes
- `ActionDispatcher`: Asynchronous action queue with per-action-type handlers, plan submission, cancellation, and statistics

**Supported Actions:** HEAL, SCALE_UP, SCALE_DOWN, MIGRATE_STORAGE, REBALANCE, HARDEN, ALERT, RECONFIGURE, QUARANTINE

**Priority Levels:** CRITICAL (0), HIGH (1), MEDIUM (2), LOW (3), INFORMATIONAL (4)

### AdaptivePulseController

Manages the system heartbeat with dynamic interval adjustment. The controller transitions through four pulse modes based on the overall health score:

| Pulse Mode | Trigger | Interval Range |
|------------|---------|----------------|
| STEADY | Health ≥ 0.8 | Baseline (default 30s) |
| ACCELERATED | Health 0.5–0.8 | Baseline ÷ acceleration factor |
| EMERGENCY | Health < 0.5 | Baseline ÷ emergency factor |
| RECOVERY | Post-emergency | Gradually returns to baseline |

Each named daemon registers its own baseline interval. The controller tracks mode transition history, time spent in each mode, and compression ratios for observability.

### AutoConfigManager

Environment-aware configuration management with automatic profile detection. The system defines four built-in profiles:

| Profile | Environment | Key Characteristics |
|---------|-------------|-------------------|
| true_nas_production | TRUE_NAS | Local-first, ZFS primary, no cloud fallback |
| hybrid_balanced | HYBRID | ZFS + cloud tier, weighted health routing |
| cloud_only_zero_cost | CLOUD_ONLY | Free-tier cloud only, aggressive scaling limits |
| development | DEVELOPMENT | Relaxed intervals, debug-friendly settings |

Configuration items track their lifecycle through statuses: DEFAULT → DETECTED → OVERRIDDEN → HOT_RELOADED → VALIDATED → ROLLED_BACK. The `auto_configure()` method uses the EnvironmentDetector to determine the appropriate profile, and `hot_reload()` supports runtime configuration changes without restart.

### PredictiveAutoscaler

Load forecasting and resource scaling with zero-cost constraint enforcement. Uses Holt's double exponential smoothing method to separate level and trend components in load data:

- **Alpha (α):** Smoothing factor for the level component (default 0.3)
- **Beta (β):** Smoothing factor for the trend component (default 0.1)
- **Window size:** Number of samples for initial estimation (default 10)

Scaling decisions respect free-tier limits: when `zero_cost_compliant` is True, the scaler will not exceed the `free_tier_limit` for any resource. Cooldown periods prevent thrashing between scale-up and scale-down actions.

### ProactiveMetricsCollector

Aggregates vitals from all proactive subsystems into unified `SystemVitals` and `MetricsSnapshot` objects. The collector supports:

- Composite health scoring across subsystems
- Health trend detection (IMPROVING, STABLE, DEGRADING, CRITICAL, UNKNOWN)
- Prometheus-format metric export with configurable prefix
- Custom collector registration for domain-specific metrics
- Snapshot history with configurable size

### ProactiveSystemBootstrap

Manages the wiring and lifecycle of all proactive components. It establishes bridge connections across 11 bridge types, each representing a connection to a core subsystem:

| Bridge Type | Target Subsystem |
|-------------|-----------------|
| EVENT_BUS | Central event bus |
| STORAGE | Storage orchestrator |
| SENTINEL | Health sentinel |
| DEFENSE | Defense perimeter |
| FORESIGHT | Predictive foresight |
| ROUTING | Service router |
| REGISTRY | Service registry |
| RESILIENCE | Circuit breaker/resilience |
| PULSE | Adaptive pulse controller |
| CONFIG | Auto-config manager |
| SCALER | Predictive autoscaler |

Bridge connections progress through states: DISCONNECTED → CONNECTING → CONNECTED → ACTIVE (or ERROR/DISABLED). The bootstrap process is fully asynchronous with graceful startup and shutdown.

## Test Coverage

Phase 11.3 provides 173 tests across 6 test files covering all proactive system modules:

| Test File | Tests | Coverage |
|-----------|-------|----------|
| test_proactive_orchestrator.py | 35 | Enums, dataclasses, analyzer, healing, zero-cost, dispatcher, orchestrator |
| test_adaptive_pulse.py | 23 | PulseMode, PulseConfig, transitions, metrics, controller |
| test_auto_config.py | 27 | ConfigStatus, EnvironmentType, ConfigItem, ConfigProfile, DetectionResult, detector, manager |
| test_predictive_scaler.py | 32 | ScalingDirection, ScalingReason, LoadSample, LoadForecast, ScalerConfig, ScalingDecision, forecaster, autoscaler |
| test_proactive_metrics.py | 20 | MetricType, HealthTrend, SubsystemMetrics, SystemVitals, MetricsSnapshot, collector |
| test_proactive_wiring.py | 19 | BridgeType, WiringStatus, BridgeConnection, ProactiveSystemBootstrap |

## Zero-Cost Compliance

All proactive system modules enforce the zero-cost mandate. The ZeroCostModulator continuously monitors storage utilization across tiers and triggers automated migration when a tier approaches its free-tier limit. The PredictiveAutoscaler respects free-tier resource limits in all scaling decisions. The AutoConfigManager selects profiles that optimize for zero-cost operation based on the detected environment.
