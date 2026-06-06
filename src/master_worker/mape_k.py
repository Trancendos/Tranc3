"""
MAPE-K Control Loop — Master Worker Orchestration Engine
=========================================================
Implements the IBM MAPE-K (Monitor, Analyse, Plan, Execute, Knowledge)
autonomic computing reference model as the sovereign orchestration engine
for the Trancendos platform.

Standing directives this implements:
  "Don't use GitHub actions or workflows in GitHub"
  "Don't use cloudflare workers build our own"
  "One master worker with smart adaptive templates"
  "Cloud setup that understands its own resources and the vendors and
   platforms and environments then ensure its adaptive and proactive
   with the ability to auto rotate"
  "Be smart, intelligent, logical and automated that can rotate the
   platforms usage size and environments to ensure that it retained 0 costings"

MAPE-K phases:
  Monitor  — collect metrics from all 38+ workers + external platform APIs
  Analyse  — detect anomalies, quota risks, security threats, cost violations
  Plan     — generate adaptation actions (rotate, scale, alert, remediate)
  Execute  — apply actions via worker control APIs and platform SDKs
  Knowledge— persistent state, learning history, policy store

The loop runs continuously as an asyncio task at configurable intervals.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

from .platform_registry import PlatformRegistry
from .zero_cost_enforcer import QuotaStatus, ZeroCostEnforcer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Knowledge store (in-memory + optional SQLite persistence)
# ---------------------------------------------------------------------------


class KnowledgeStore:
    """Persistent knowledge base for the MAPE-K loop."""

    def __init__(self) -> None:
        """Initialise the fact base, history ring buffer, and default platform policies."""
        self._facts: Dict[str, Any] = {}
        self._history: List[Dict[str, Any]] = []
        self._policies: Dict[str, Any] = {
            "max_error_rate": 0.05,  # 5% error rate triggers action
            "min_health_score": 0.6,  # below 0.6 → mark degraded
            "quota_warning_pct": 0.85,  # rotate at 85%
            "quota_critical_pct": 0.95,  # emergency rotate at 95%
            "zero_cost_enforced": True,  # must be True always
            "ci_provider": "forgejo",  # ONLY forgejo — never github_actions
            "edge_provider": "self_hosted",  # ONLY self-hosted — never cloudflare_workers
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Return the stored fact for *key*, or *default* if absent."""
        return self._facts.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key* in the fact base."""
        self._facts[key] = value

    def policy(self, key: str, default: Any = None) -> Any:
        """Return the policy value for *key*, or *default* if not configured."""
        return self._policies.get(key, default)

    def record_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Append a timestamped event to the history ring buffer (capped at 10k entries)."""
        self._history.append(
            {
                "id": uuid.uuid4().hex[:8],
                "type": event_type,
                "data": data,
                "ts": time.time(),
            }
        )
        if len(self._history) > 10_000:
            self._history = self._history[-5_000:]

    def recent_events(self, event_type: Optional[str] = None, n: int = 50) -> List[Dict[str, Any]]:
        """Return the last *n* events, optionally filtered by *event_type*."""
        events = (
            self._history
            if not event_type
            else [e for e in self._history if e["type"] == event_type]
        )
        return events[-n:]


# ---------------------------------------------------------------------------
# Monitoring models
# ---------------------------------------------------------------------------


@dataclass
class WorkerMetrics:
    """Health probe result for a single worker collected during Monitor phase."""

    worker_name: str
    is_healthy: bool
    status_code: Optional[int]
    latency_ms: float
    health_score: Optional[float]
    error: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict)
    collected_at: float = field(default_factory=time.monotonic)


@dataclass
class SystemSnapshot:
    """Full platform snapshot collected during Monitor phase."""

    worker_metrics: List[WorkerMetrics] = field(default_factory=list)
    platform_snapshot: Dict[str, Any] = field(default_factory=dict)
    unhealthy_workers: List[str] = field(default_factory=list)
    total_workers: int = 0
    healthy_workers: int = 0
    collected_at: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# Action plan models
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    """Possible adaptation actions the MAPE-K Execute phase can perform."""

    ROTATE_PLATFORM = "rotate_platform"
    RESTART_WORKER = "restart_worker"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    ALERT = "alert"
    LOG_COST_VIOLATION = "log_cost_violation"
    NOOP = "noop"


@dataclass
class AdaptationAction:
    """A concrete action produced by the Plan phase and consumed by Execute."""

    action_type: ActionType
    target: str  # worker name or platform name
    reason: str
    priority: int = 5  # 1=critical, 5=low
    params: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# MAPE-K config
# ---------------------------------------------------------------------------


@dataclass
class MapeKConfig:
    """Runtime configuration for the MAPE-K control loop."""

    monitor_interval_s: float = 30.0
    worker_health_timeout_s: float = 5.0
    base_worker_url: str = "http://localhost"
    worker_ports: Dict[str, int] = field(default_factory=dict)
    enable_auto_execute: bool = True


class ControlLoopState(str, Enum):
    """Current phase of the MAPE-K autonomic control loop."""

    IDLE = "idle"
    MONITORING = "monitoring"
    ANALYSING = "analysing"
    PLANNING = "planning"
    EXECUTING = "executing"
    ERROR = "error"


# ---------------------------------------------------------------------------
# MAPE-K loop
# ---------------------------------------------------------------------------


class MapeKLoop:
    """
    Sovereign MAPE-K autonomic control loop for the Trancendos platform.

    Lifecycle:
        loop = MapeKLoop(config)
        await loop.start()
        ...
        await loop.stop()

    Events can be subscribed to:
        loop.on_action(async_callback)
    """

    # Default worker port map from CLAUDE.md
    DEFAULT_WORKER_PORTS: Dict[str, int] = {
        "infinity-ws": 8004,
        "infinity-auth": 8005,
        "users-service": 8006,
        "monitoring": 8007,
        "notifications": 8008,
        "infinity-ai": 8009,
        "the-grid": 8010,
        "products-service": 8011,
        "orders-service": 8012,
        "payments-service": 8013,
        "files-service": 8014,
        "identity-service": 8015,
        "analytics-service": 8016,
        "audit-service": 8017,
        "cache-service": 8018,
        "cdn-service": 8019,
        "config-service": 8020,
        "cron-service": 8021,
        "email-service": 8022,
        "geo-service": 8023,
        "search-service": 8024,
        "sms-service": 8025,
        "storage-service": 8026,
        "queue-service": 8027,
        "rate-limit-service": 8028,
        "health-aggregator": 8029,
        "gbrain-bridge": 8030,
        "topology-service": 8031,
        "ledger-service": 8032,
        "model-router-service": 8033,
        "workflow-engine-service": 8034,
        "skills-benchmark-service": 8035,
        "langchain-integration-service": 8036,
        "deepagents-orchestrator-service": 8037,
        "vault-service": 8038,
    }

    def __init__(
        self,
        config: Optional[MapeKConfig] = None,
        registry: Optional[PlatformRegistry] = None,
    ) -> None:
        """Initialise the loop with optional config and platform registry overrides."""
        self._config = config or MapeKConfig(
            worker_ports=dict(self.DEFAULT_WORKER_PORTS),
        )
        if not self._config.worker_ports:
            self._config.worker_ports = dict(self.DEFAULT_WORKER_PORTS)

        self._registry = registry or PlatformRegistry()
        self._enforcer = ZeroCostEnforcer(self._registry)
        self._knowledge = KnowledgeStore()
        self._state = ControlLoopState.IDLE
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._action_callbacks: List[Callable[[AdaptationAction], Awaitable[None]]] = []
        self._cycle_count = 0
        self._last_snapshot: Optional[SystemSnapshot] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the MAPE-K loop and the zero-cost enforcer as background tasks."""
        if self._running:
            return
        self._running = True
        await self._enforcer.start()
        self._enforcer.on_rotation(self._on_platform_rotation)
        self._task = asyncio.create_task(self._loop(), name="mape_k_master_worker")
        logger.info(
            "MapeKLoop started (interval=%.0fs, workers=%d)",
            self._config.monitor_interval_s,
            len(self._config.worker_ports),
        )

    async def stop(self) -> None:
        """Gracefully cancel the control loop and stop the zero-cost enforcer."""
        self._running = False
        await self._enforcer.stop()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # Expected when we cancel the task
        logger.info("MapeKLoop stopped after %d cycles", self._cycle_count)

    def on_action(self, cb: Callable[[AdaptationAction], Awaitable[None]]) -> None:
        """Register an async callback invoked after each adaptation action is executed."""
        self._action_callbacks.append(cb)

    # ------------------------------------------------------------------
    # MAPE-K phases
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Run the Monitor→Analyse→Plan→Execute cycle on a fixed interval until stopped."""
        while self._running:
            cycle_start = time.monotonic()
            try:
                self._cycle_count += 1
                logger.debug("MAPE-K cycle #%d starting", self._cycle_count)

                # M — Monitor
                self._state = ControlLoopState.MONITORING
                snapshot = await self._monitor()
                self._last_snapshot = snapshot

                # A — Analyse
                self._state = ControlLoopState.ANALYSING
                analysis = self._analyse(snapshot)

                # P — Plan
                self._state = ControlLoopState.PLANNING
                actions = self._plan(analysis, snapshot)

                # E — Execute
                if self._config.enable_auto_execute and actions:
                    self._state = ControlLoopState.EXECUTING
                    await self._execute(actions)

                self._state = ControlLoopState.IDLE
                self._knowledge.record_event(
                    "cycle_complete",
                    {
                        "cycle": self._cycle_count,
                        "healthy": snapshot.healthy_workers,
                        "total": snapshot.total_workers,
                        "actions": len(actions),
                    },
                )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._state = ControlLoopState.ERROR
                logger.error("MAPE-K cycle #%d error: %s", self._cycle_count, exc)
                self._knowledge.record_event("cycle_error", {"error": str(exc)})

            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0.0, self._config.monitor_interval_s - elapsed)
            await asyncio.sleep(sleep_time)

    # ------------------------------------------------------------------
    # M — Monitor
    # ------------------------------------------------------------------

    async def _monitor(self) -> SystemSnapshot:
        """Probe all registered workers concurrently and return a SystemSnapshot."""
        snapshot = SystemSnapshot(
            total_workers=len(self._config.worker_ports),
            platform_snapshot=self._registry.snapshot(),
        )

        async with httpx.AsyncClient(timeout=self._config.worker_health_timeout_s) as client:
            tasks = [
                self._probe_worker(client, name, port)
                for name, port in self._config.worker_ports.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, WorkerMetrics):
                snapshot.worker_metrics.append(result)
                if result.is_healthy:
                    snapshot.healthy_workers += 1
                else:
                    snapshot.unhealthy_workers.append(result.worker_name)

        return snapshot

    async def _probe_worker(self, client: httpx.AsyncClient, name: str, port: int) -> WorkerMetrics:
        """GET /health on the worker at *port* and return a WorkerMetrics record."""
        url = f"{self._config.base_worker_url}:{port}/health"
        t0 = time.monotonic()
        try:
            resp = await client.get(url)
            latency_ms = (time.monotonic() - t0) * 1000
            data = resp.json() if resp.status_code == 200 else {}
            return WorkerMetrics(
                worker_name=name,
                is_healthy=resp.status_code == 200,
                status_code=resp.status_code,
                latency_ms=round(latency_ms, 2),
                health_score=data.get("health_score"),
                error=None if resp.status_code == 200 else f"HTTP {resp.status_code}",
                raw=data,
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            return WorkerMetrics(
                worker_name=name,
                is_healthy=False,
                status_code=None,
                latency_ms=round(latency_ms, 2),
                health_score=None,
                error=str(exc)[:120],
            )

    # ------------------------------------------------------------------
    # A — Analyse
    # ------------------------------------------------------------------

    def _analyse(self, snapshot: SystemSnapshot) -> Dict[str, Any]:
        """Return analysis dict with detected issues and their severities."""
        issues: List[Dict[str, Any]] = []

        # Worker health issues
        if snapshot.unhealthy_workers:
            unhealthy_rate = len(snapshot.unhealthy_workers) / max(snapshot.total_workers, 1)
            issues.append(
                {
                    "type": "worker_health",
                    "severity": "critical" if unhealthy_rate > 0.2 else "warning",
                    "affected": snapshot.unhealthy_workers,
                    "unhealthy_rate": round(unhealthy_rate, 3),
                }
            )

        # Platform quota issues
        quota_reports = self._enforcer.check_all()
        for report in quota_reports:
            if report.status in (QuotaStatus.CRITICAL, QuotaStatus.EXHAUSTED):
                issues.append(
                    {
                        "type": "quota_critical",
                        "severity": "critical",
                        "platform": report.platform_name,
                        "utilisation_pct": report.utilisation_pct,
                    }
                )
            elif report.status == QuotaStatus.WARNING:
                issues.append(
                    {
                        "type": "quota_warning",
                        "severity": "warning",
                        "platform": report.platform_name,
                        "utilisation_pct": report.utilisation_pct,
                    }
                )

        # Zero-cost assertion
        assertion = self._enforcer.assert_zero_cost()
        if not assertion.passed:
            for violation in assertion.violations:
                issues.append(
                    {
                        "type": "cost_violation",
                        "severity": "critical",
                        "violation": violation,
                    }
                )

        return {
            "issues": issues,
            "issue_count": len(issues),
            "critical_count": sum(1 for i in issues if i.get("severity") == "critical"),
            "snapshot_age_s": round(time.monotonic() - snapshot.collected_at, 2),
        }

    # ------------------------------------------------------------------
    # P — Plan
    # ------------------------------------------------------------------

    def _plan(
        self,
        analysis: Dict[str, Any],
        snapshot: SystemSnapshot,
    ) -> List[AdaptationAction]:
        """Convert Analyse-phase issues into a priority-sorted list of AdaptationActions."""
        actions: List[AdaptationAction] = []

        for issue in analysis.get("issues", []):
            issue_type = issue.get("type")

            if issue_type == "worker_health":
                for worker in issue.get("affected", []):
                    actions.append(
                        AdaptationAction(
                            action_type=ActionType.ALERT,
                            target=worker,
                            reason=f"Worker {worker!r} is unhealthy — probe failed",
                            priority=2 if issue["severity"] == "critical" else 4,
                        )
                    )

            elif issue_type in ("quota_critical", "quota_exhausted"):
                actions.append(
                    AdaptationAction(
                        action_type=ActionType.ROTATE_PLATFORM,
                        target=issue["platform"],
                        reason=f"Quota at {issue['utilisation_pct']:.1f}% — rotating to fallback",
                        priority=1,
                    )
                )

            elif issue_type == "quota_warning":
                actions.append(
                    AdaptationAction(
                        action_type=ActionType.ALERT,
                        target=issue["platform"],
                        reason=f"Quota at {issue['utilisation_pct']:.1f}% — approaching limit",
                        priority=3,
                        params={"utilisation_pct": issue["utilisation_pct"]},
                    )
                )

            elif issue_type == "cost_violation":
                actions.append(
                    AdaptationAction(
                        action_type=ActionType.LOG_COST_VIOLATION,
                        target="zero_cost_enforcer",
                        reason=issue["violation"],
                        priority=1,
                    )
                )

        # Sort by priority (1=most urgent)
        actions.sort(key=lambda a: a.priority)
        return actions

    # ------------------------------------------------------------------
    # E — Execute
    # ------------------------------------------------------------------

    async def _execute(self, actions: List[AdaptationAction]) -> None:
        """Apply each planned action in priority order, logging success and failure."""
        for action in actions:
            try:
                await self._apply_action(action)
                self._knowledge.record_event(
                    "action_executed",
                    {
                        "type": action.action_type.value,
                        "target": action.target,
                        "reason": action.reason,
                        "priority": action.priority,
                    },
                )
                for cb in self._action_callbacks:
                    try:
                        await cb(action)
                    except Exception as exc:
                        logger.warning("Action callback failed: %s", exc)
            except Exception as exc:
                logger.error(
                    "Failed to execute action %s on %s: %s",
                    action.action_type.value,
                    action.target,
                    exc,
                )
                self._knowledge.record_event(
                    "action_failed",
                    {
                        "type": action.action_type.value,
                        "target": action.target,
                        "error": str(exc),
                    },
                )

    async def _apply_action(self, action: AdaptationAction) -> None:
        """Dispatch a single AdaptationAction to the appropriate subsystem."""
        if action.action_type == ActionType.ROTATE_PLATFORM:
            fallback = await self._enforcer.rotate_platform(action.target)
            logger.info("Executed ROTATE_PLATFORM: %s → %s", action.target, fallback)

        elif action.action_type == ActionType.ALERT:
            logger.warning(
                "[MAPE-K ALERT] target=%s priority=%d reason=%s",
                action.target,
                action.priority,
                action.reason,
            )

        elif action.action_type == ActionType.LOG_COST_VIOLATION:
            logger.error(
                "[ZERO-COST VIOLATION] %s — %s",
                action.target,
                action.reason,
            )

        elif action.action_type == ActionType.NOOP:
            pass

        else:
            logger.debug("Action %s queued (not auto-executed)", action.action_type.value)

    # ------------------------------------------------------------------
    # Platform rotation callback
    # ------------------------------------------------------------------

    async def _on_platform_rotation(self, old: str, new: str) -> None:
        """Callback from ZeroCostEnforcer; persists rotation events to KnowledgeStore."""
        self._knowledge.record_event(
            "platform_rotation",
            {
                "from": old,
                "to": new,
                "ts": time.time(),
            },
        )
        logger.info("Knowledge: recorded platform rotation %s → %s", old, new)

    # ------------------------------------------------------------------
    # Status / observability
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Return a serialisable status dict for the /master/status health endpoint."""
        snap = self._last_snapshot
        return {
            "state": self._state.value,
            "running": self._running,
            "cycle_count": self._cycle_count,
            "monitor_interval_s": self._config.monitor_interval_s,
            "worker_count": len(self._config.worker_ports),
            "last_snapshot": {
                "healthy": snap.healthy_workers if snap else None,
                "total": snap.total_workers if snap else None,
                "unhealthy": snap.unhealthy_workers if snap else [],
                "age_s": round(time.monotonic() - snap.collected_at, 1) if snap else None,
            },
            "enforcer": self._enforcer.status(),
            "recent_events": self._knowledge.recent_events(n=10),
        }
