# Dimensional/architecture/__init__.py
# Tranc3 Architecture Layer — Intelligent Adaptive Proactive Systems

from .adaptive_pulse import (
    AdaptivePulseController,
    PulseConfig,
    PulseMetrics,
    PulseMode,
    PulseTransition,
    adaptive_pulse,
)
from .auto_config import (
    AutoConfigManager,
    ConfigItem,
    ConfigProfile,
    ConfigStatus,
    DetectionResult,
    EnvironmentDetector,
    EnvironmentType,
    auto_config,
)
from .proactive_metrics import (
    HealthTrend,
    MetricsSnapshot,
    ProactiveMetricsCollector,
    SubsystemMetrics,
    SystemVitals,
    proactive_metrics,
)
from .proactive_orchestrator import (
    ActionDispatcher,
    ActionPlan,
    ActionPriority,
    AutoHealingEngine,
    MetricSample,
    OrchestratorMode,
    PredictiveHealthAnalyzer,
    ProactiveAction,
    ProactiveOrchestrator,
    SystemHealthProfile,
    ZeroCostModulator,
    ZeroCostStatus,
    proactive_orchestrator,
)
from .proactive_wiring import (
    BridgeConnection,
    BridgeType,
    ProactiveSystemBootstrap,
    WiringStatus,
    proactive_bootstrap,
)

__all__ = [
    # Proactive Orchestrator
    "ProactiveOrchestrator",
    "ProactiveAction",
    "ActionPriority",
    "OrchestratorMode",
    "MetricSample",
    "ActionPlan",
    "SystemHealthProfile",
    "ZeroCostStatus",
    "PredictiveHealthAnalyzer",
    "AutoHealingEngine",
    "ZeroCostModulator",
    "ActionDispatcher",
    "proactive_orchestrator",
    # Adaptive Pulse
    "AdaptivePulseController",
    "PulseMode",
    "PulseConfig",
    "PulseTransition",
    "PulseMetrics",
    "adaptive_pulse",
    # Auto Config
    "AutoConfigManager",
    "EnvironmentType",
    "ConfigStatus",
    "ConfigItem",
    "ConfigProfile",
    "DetectionResult",
    "EnvironmentDetector",
    "auto_config",
    # Proactive Metrics
    "ProactiveMetricsCollector",
    "SystemVitals",
    "SubsystemMetrics",
    "MetricsSnapshot",
    "HealthTrend",
    "proactive_metrics",
    # Proactive Wiring
    "ProactiveSystemBootstrap",
    "BridgeType",
    "BridgeConnection",
    "WiringStatus",
    "proactive_bootstrap",
]
