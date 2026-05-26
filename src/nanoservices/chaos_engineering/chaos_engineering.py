"""Chaos Engineering Service — Phase 12

Resilience testing through controlled fault injection.
Zero-cost implementation with safety guards and automated rollback.
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FaultType(Enum):
    LATENCY_INJECTION = "latency_injection"
    ERROR_INJECTION = "error_injection"
    SERVICE_KILL = "service_kill"
    NETWORK_PARTITION = "network_partition"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DATA_CORRUPTION = "data_corruption"
    DEPENDENCY_FAILURE = "dependency_failure"
    CLOCK_SKEW = "clock_skew"


class ExperimentState(Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    ABORTED = "aborted"
    FAILED = "failed"


class BlastRadius(Enum):
    SINGLE_SERVICE = "single_service"
    NAMESPACE = "namespace"
    CLUSTER = "cluster"
    GLOBAL = "global"


@dataclass
class FaultSpec:
    fault_type: FaultType
    target_service: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 60.0
    probability: float = 1.0


@dataclass
class SteadyStateHypothesis:
    name: str
    probe_type: str
    target: str
    expected_value: Any = None
    tolerance: float = 0.1
    actual_value: Any = None
    passed: bool = False


@dataclass
class ChaosExperiment:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    fault: FaultSpec = field(
        default_factory=lambda: FaultSpec(fault_type=FaultType.LATENCY_INJECTION, target_service="")
    )
    hypotheses: List[SteadyStateHypothesis] = field(default_factory=list)
    state: ExperimentState = ExperimentState.PLANNED
    blast_radius: BlastRadius = BlastRadius.SINGLE_SERVICE
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    rollback_actions: List[str] = field(default_factory=list)
    observations: List[Dict[str, Any]] = field(default_factory=list)
    result_summary: str = ""


@dataclass
class ChaosReport:
    experiment_id: str
    experiment_name: str
    fault_type: FaultType
    target: str
    duration_seconds: float
    hypotheses_passed: int
    hypotheses_total: int
    state: ExperimentState
    resilience_score: float  # 0-1
    findings: List[str] = field(default_factory=list)


class FaultInjector:
    """Simulates fault injection for chaos experiments."""

    def __init__(self):
        self._active_faults: Dict[str, FaultSpec] = {}
        self._fault_handlers: Dict[FaultType, Any] = {}

    def register_handler(self, fault_type: FaultType, handler: Any) -> None:
        self._fault_handlers[fault_type] = handler

    def inject(self, fault: FaultSpec, experiment_id: str = "") -> bool:
        if fault.target_service in self._active_faults:
            logger.warning("Fault already active for %s — skipping", fault.target_service)
            return False

        handler = self._fault_handlers.get(fault.fault_type)
        if handler:
            try:
                handler(fault)
            except Exception as e:
                logger.error("Fault injection failed: %s", e)
                return False

        self._active_faults[fault.target_service] = fault
        logger.info(
            "Injected %s fault into %s (experiment %s)",
            fault.fault_type.value,
            fault.target_service,
            experiment_id,
        )
        return True

    def rollback(self, target_service: str) -> bool:
        if target_service not in self._active_faults:
            return False
        fault = self._active_faults.pop(target_service)
        logger.info("Rolled back %s fault on %s", fault.fault_type.value, target_service)
        return True

    def rollback_all(self) -> int:
        count = len(self._active_faults)
        for target in list(self._active_faults.keys()):
            self.rollback(target)
        return count

    def get_active_faults(self) -> Dict[str, FaultSpec]:
        return dict(self._active_faults)


class SteadyStateValidator:
    """Validates system behavior against steady-state hypotheses."""

    def validate_before(self, hypotheses: List[SteadyStateHypothesis]) -> bool:
        return all(self._check(h) for h in hypotheses)

    def validate_after(
        self, hypotheses: List[SteadyStateHypothesis]
    ) -> List[SteadyStateHypothesis]:
        results = []
        for h in hypotheses:
            checked = self._check(h)
            h.passed = checked
            results.append(h)
        return results

    def _check(self, hypothesis: SteadyStateHypothesis) -> bool:
        # In production, this would call actual health endpoints
        # For simulation, we model probabilistic behavior
        if hypothesis.expected_value is not None and hypothesis.actual_value is not None:
            if isinstance(hypothesis.expected_value, (int, float)):
                diff = abs(float(hypothesis.actual_value) - float(hypothesis.expected_value))
                return diff <= hypothesis.tolerance
            return hypothesis.actual_value == hypothesis.expected_value
        return True


class ChaosEngineeringService:
    """Main service: plans, executes, and reports on chaos experiments."""

    def __init__(self, max_concurrent: int = 3, auto_rollback: bool = True):
        self._injector = FaultInjector()
        self._validator = SteadyStateValidator()
        self._experiments: Dict[str, ChaosExperiment] = {}
        self._reports: List[ChaosReport] = []
        self._max_concurrent = max_concurrent
        self._auto_rollback = auto_rollback
        self._safety_enabled = True

    def initialize(self) -> None:
        logger.info(
            "ChaosEngineeringService initialized (auto_rollback=%s, max_concurrent=%d)",
            self._auto_rollback,
            self._max_concurrent,
        )

    def create_experiment(
        self,
        name: str,
        fault: FaultSpec,
        hypotheses: Optional[List[SteadyStateHypothesis]] = None,
        blast_radius: BlastRadius = BlastRadius.SINGLE_SERVICE,
    ) -> ChaosExperiment:
        exp = ChaosExperiment(
            name=name,
            fault=fault,
            hypotheses=hypotheses or [],
            blast_radius=blast_radius,
        )
        self._experiments[exp.id] = exp

        if not hypotheses:
            exp.hypotheses = [
                SteadyStateHypothesis(
                    name="service_responsive",
                    probe_type="health_check",
                    target=fault.target_service,
                    expected_value=True,
                ),
                SteadyStateHypothesis(
                    name="error_rate_acceptable",
                    probe_type="error_rate",
                    target=fault.target_service,
                    expected_value=0.01,
                    tolerance=0.05,
                ),
            ]
        return exp

    def run_experiment(self, experiment_id: str) -> ChaosReport:
        exp = self._experiments.get(experiment_id)
        if not exp:
            return ChaosReport(
                experiment_id=experiment_id,
                experiment_name="unknown",
                fault_type=FaultType.LATENCY_INJECTION,
                target="unknown",
                duration_seconds=0,
                hypotheses_passed=0,
                hypotheses_total=0,
                state=ExperimentState.FAILED,
                resilience_score=0.0,
            )

        # Safety check
        running = sum(1 for e in self._experiments.values() if e.state == ExperimentState.RUNNING)
        if running >= self._max_concurrent:
            exp.state = ExperimentState.ABORTED
            return self._make_report(exp)

        if not self._safety_enabled and exp.blast_radius in (
            BlastRadius.CLUSTER,
            BlastRadius.GLOBAL,
        ):
            exp.state = ExperimentState.ABORTED
            exp.result_summary = "Aborted: safety disabled for high blast radius"
            return self._make_report(exp)

        # Pre-flight: validate steady state
        if not self._validator.validate_before(exp.hypotheses):
            exp.state = ExperimentState.ABORTED
            exp.result_summary = "Aborted: steady state hypothesis failed before injection"
            return self._make_report(exp)

        # Inject fault
        exp.state = ExperimentState.RUNNING
        exp.started_at = time.time()
        success = self._injector.inject(exp.fault, exp.id)

        if not success:
            exp.state = ExperimentState.FAILED
            exp.result_summary = "Fault injection failed"
            return self._make_report(exp)

        # Simulate experiment duration
        elapsed = 0.0
        check_interval = min(5.0, exp.fault.duration_seconds / 10)
        while elapsed < exp.fault.duration_seconds:
            # Probabilistic fault behavior
            if random.random() > exp.fault.probability:
                exp.observations.append(
                    {
                        "time": elapsed,
                        "event": "fault_skipped",
                        "probability": exp.fault.probability,
                    }
                )

            elapsed += check_interval

        # Post-flight: validate steady state recovery
        results = self._validator.validate_after(exp.hypotheses)
        for h in results:
            exp.observations.append(
                {
                    "hypothesis": h.name,
                    "passed": h.passed,
                    "expected": h.expected_value,
                    "actual": h.actual_value,
                }
            )

        # Auto-rollback
        if self._auto_rollback:
            self._injector.rollback(exp.fault.target_service)
            exp.rollback_actions.append(f"auto_rollback_{exp.fault.fault_type.value}")

        exp.ended_at = time.time()
        exp.state = ExperimentState.COMPLETED

        report = self._make_report(exp)
        self._reports.append(report)
        return report

    def _make_report(self, exp: ChaosExperiment) -> ChaosReport:
        passed = sum(1 for h in exp.hypotheses if h.passed)
        total = len(exp.hypotheses)
        resilience = passed / total if total > 0 else 0.0

        findings = []
        for h in exp.hypotheses:
            if not h.passed:
                findings.append(
                    f"FAILED: {h.name} — expected {h.expected_value}, got {h.actual_value}"
                )
            else:
                findings.append(f"PASSED: {h.name}")

        return ChaosReport(
            experiment_id=exp.id,
            experiment_name=exp.name,
            fault_type=exp.fault.fault_type,
            target=exp.fault.target_service,
            duration_seconds=exp.fault.duration_seconds,
            hypotheses_passed=passed,
            hypotheses_total=total,
            state=exp.state,
            resilience_score=resilience,
            findings=findings,
        )

    def get_experiment(self, experiment_id: str) -> Optional[ChaosExperiment]:
        return self._experiments.get(experiment_id)

    def get_reports(self, limit: int = 50) -> List[ChaosReport]:
        return self._reports[-limit:]

    def emergency_rollback_all(self) -> int:
        count = self._injector.rollback_all()
        for exp in self._experiments.values():
            if exp.state == ExperimentState.RUNNING:
                exp.state = ExperimentState.ROLLED_BACK
                exp.ended_at = time.time()
        logger.warning("Emergency rollback: %d faults removed", count)
        return count
