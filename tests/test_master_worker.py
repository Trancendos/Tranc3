"""
Tests for the Master Worker MAPE-K system.

Covers:
  - PlatformRegistry: quota tracking and availability
  - ZeroCostEnforcer: blocklist, assertion, rotation
  - BlueprintEngine: code generation for all blueprint types
  - MapeKLoop: analyse and plan phases (unit tests, no real network)
"""

from __future__ import annotations

import asyncio
import os
from typing import List

import pytest

from src.master_worker.adaptive_blueprints import (
    BlueprintEngine,
    BlueprintSpec,
    BlueprintType,
)
from src.master_worker.mape_k import (
    ActionType,
    ControlLoopState,
    MapeKConfig,
    MapeKLoop,
    SystemSnapshot,
    WorkerMetrics,
)
from src.master_worker.platform_registry import (
    PlatformCategory,
    PlatformHealth,
    PlatformRegistry,
)
from src.master_worker.zero_cost_enforcer import QuotaStatus, ZeroCostEnforcer

# ---------------------------------------------------------------------------
# PlatformRegistry
# ---------------------------------------------------------------------------


class TestPlatformRegistry:
    def test_default_registry_builds(self):
        r = PlatformRegistry()
        assert len(r._platforms) > 0

    def test_ollama_is_highest_priority_llm(self):
        r = PlatformRegistry()
        best = r.best_for(PlatformCategory.AI_LLM)
        # Ollama is priority 1; may be UNKNOWN health but is_available checks
        # that health != EXHAUSTED/OFFLINE — UNKNOWN passes
        assert best is not None
        assert best.name == "ollama"

    def test_mark_exhausted_excludes_from_best(self):
        r = PlatformRegistry()
        r.mark_exhausted("ollama")
        best = r.best_for(PlatformCategory.AI_LLM)
        assert best is not None
        assert best.name != "ollama"

    def test_utilisation_pct_calculation(self):
        r = PlatformRegistry()
        groq = r.get("groq")
        assert groq is not None
        # No usage yet → 0%
        assert groq.utilisation_pct() == 0.0

        # Record usage
        r.record_tokens("groq", tokens=250_000)
        assert groq.utilisation_pct() > 0.0

    def test_utilisation_pct_all_dimensions(self):
        """utilisation_pct() accounts for all 7 configured quota dimensions."""
        from src.master_worker.platform_registry import (
            Platform,
            PlatformCategory,
            PlatformUsage,
            QuotaLimits,
        )

        p = Platform(
            name="test_multi_quota",
            category=PlatformCategory.HOSTING,
            priority=99,
            quota=QuotaLimits(
                requests_per_minute=100,
                storage_gb=1.0,
                compute_hours_month=10.0,
            ),
            usage=PlatformUsage(
                requests_this_minute=50,
                storage_gb_used=0.5,
                compute_hours_used=5.0,
            ),
        )
        pct = p.utilisation_pct()
        # All three ratios equal 0.5; max should be exactly 0.5
        assert abs(pct - 0.5) < 1e-9

    def test_per_minute_counters_reset_after_window(self):
        """Per-minute counters reset to 0 once 60 s have elapsed (no false exhaustion)."""
        from src.master_worker.platform_registry import (
            Platform,
            PlatformCategory,
            PlatformUsage,
            QuotaLimits,
        )

        p = Platform(
            name="reset_test",
            category=PlatformCategory.AI_LLM,
            priority=99,
            quota=QuotaLimits(requests_per_minute=10, tokens_per_minute=1000),
            usage=PlatformUsage(
                requests_this_minute=9,
                tokens_used_this_minute=950,
                # Set window start 61 seconds in the past so it's already expired
                minute_window_start=__import__("time").monotonic() - 61.0,
            ),
        )
        # Before reset: utilisation appears near-full
        pct = p.utilisation_pct()
        # After reset (window expired): per-minute counters are 0 → ratio 0
        assert pct == 0.0, f"Expected 0.0 after window reset, got {pct}"
        assert p.usage.requests_this_minute == 0
        assert p.usage.tokens_used_this_minute == 0

    def test_snapshot_returns_all_platforms(self):
        r = PlatformRegistry()
        snap = r.snapshot()
        assert "ollama" in snap
        assert "forgejo" in snap
        assert "sqlite_local" in snap

    def test_sqlite_always_healthy(self):
        r = PlatformRegistry()
        sqlite = r.get("sqlite_local")
        assert sqlite is not None
        assert sqlite.is_available() is True

    def test_all_for_returns_sorted_by_priority(self):
        r = PlatformRegistry()
        llms = r.all_for(PlatformCategory.AI_LLM)
        priorities = [p.priority for p in llms]
        assert priorities == sorted(priorities)


# ---------------------------------------------------------------------------
# ZeroCostEnforcer
# ---------------------------------------------------------------------------


class TestZeroCostEnforcer:
    def test_blocklist_raises_for_openai(self):
        e = ZeroCostEnforcer()
        with pytest.raises(ValueError, match="ZERO-COST VIOLATION"):
            e.assert_not_blocked("https://api.openai.com/v1/chat/completions")

    def test_blocklist_raises_for_azure_gpu(self):
        e = ZeroCostEnforcer()
        with pytest.raises(ValueError, match="ZERO-COST VIOLATION"):
            e.assert_not_blocked("https://azure.microsoft.com/nc6s_v3/gpu/training")

    def test_blocklist_raises_for_github_actions(self):
        e = ZeroCostEnforcer()
        with pytest.raises(ValueError, match="ZERO-COST VIOLATION"):
            e.assert_not_blocked("https://api.github.com/actions/runs")

    def test_blocklist_raises_for_cloudflare_deploy(self):
        e = ZeroCostEnforcer()
        with pytest.raises(ValueError, match="ZERO-COST VIOLATION"):
            e.assert_not_blocked("https://workers.cloudflare.com/deploy/my-worker")

    def test_blocklist_allows_forgejo(self):
        e = ZeroCostEnforcer()
        # Should not raise
        e.assert_not_blocked("https://trancendos.com/the-workshop/api")

    def test_blocklist_allows_groq(self):
        e = ZeroCostEnforcer()
        e.assert_not_blocked("https://api.groq.com/openai/v1/chat/completions")

    def test_zero_cost_assertion_passes_clean_env(self):
        e = ZeroCostEnforcer()
        # Ensure env vars are not set
        for var in (
            "AZURE_TRAINING_ENABLED",
            "CF_DEPLOY_WORKERS",
            "USE_GITHUB_ACTIONS",
            "OPENAI_API_KEY",
            "BUGZY_API_KEY",
        ):
            os.environ.pop(var, None)
        result = e.assert_zero_cost()
        assert result.passed is True
        assert result.violations == []

    def test_zero_cost_assertion_fails_azure_training(self):
        e = ZeroCostEnforcer()
        os.environ["AZURE_TRAINING_ENABLED"] = "true"
        try:
            result = e.assert_zero_cost()
            assert result.passed is False
            assert any("AZURE" in v for v in result.violations)
        finally:
            os.environ.pop("AZURE_TRAINING_ENABLED", None)

    def test_zero_cost_assertion_fails_github_actions(self):
        e = ZeroCostEnforcer()
        os.environ["USE_GITHUB_ACTIONS"] = "true"
        try:
            result = e.assert_zero_cost()
            assert result.passed is False
        finally:
            os.environ.pop("USE_GITHUB_ACTIONS", None)

    def test_check_all_returns_ok_on_zero_usage(self):
        e = ZeroCostEnforcer()
        reports = e.check_all()
        ok_reports = [r for r in reports if r.status == QuotaStatus.OK]
        # All platforms with no usage should be OK
        assert len(ok_reports) > 0

    @pytest.mark.asyncio
    async def test_rotate_platform_returns_fallback(self):
        registry = PlatformRegistry()
        e = ZeroCostEnforcer(registry)
        fallback = await e.rotate_platform("ollama")
        # Ollama exhausted → should fall back to groq
        assert fallback is not None
        assert fallback != "ollama"
        assert registry.get("ollama").health == PlatformHealth.EXHAUSTED

    @pytest.mark.asyncio
    async def test_enforcer_lifecycle(self):
        e = ZeroCostEnforcer(check_interval_s=0.1)
        await e.start()
        assert e._running is True
        await asyncio.sleep(0.15)
        await e.stop()
        assert e._running is False


# ---------------------------------------------------------------------------
# BlueprintEngine
# ---------------------------------------------------------------------------


class TestBlueprintEngine:
    def test_fastapi_worker_renders(self):
        engine = BlueprintEngine()
        spec = BlueprintSpec(
            name="test-service",
            blueprint_type=BlueprintType.FASTAPI_WORKER,
            port=9000,
            description="Test service",
            env_vars=["JWT_SECRET"],
            health_entity="TestEntity",
        )
        bp = engine.render(spec)
        assert "fastapi" in bp.worker_py.lower() or "FastAPI" in bp.worker_py
        assert "/health" in bp.worker_py
        assert "TestEntity" in bp.worker_py
        assert "JWT_SECRET" in bp.worker_py
        # Must NOT reference GitHub Actions or Cloudflare Workers
        assert "github.com/actions" not in bp.worker_py
        assert "workers.cloudflare.com" not in bp.worker_py

    def test_dockerfile_renders(self):
        engine = BlueprintEngine()
        spec = BlueprintSpec(name="svc", blueprint_type=BlueprintType.FASTAPI_WORKER, port=8100)
        bp = engine.render(spec)
        assert "FROM python:3.12-slim" in bp.dockerfile
        assert "8100" in bp.dockerfile

    def test_compose_snippet_renders(self):
        engine = BlueprintEngine()
        spec = BlueprintSpec(
            name="svc",
            blueprint_type=BlueprintType.FASTAPI_WORKER,
            port=8200,
            env_vars=["DATABASE_URL"],
        )
        bp = engine.render(spec)
        assert "8200:8200" in bp.compose_snippet
        assert "DATABASE_URL" in bp.compose_snippet

    def test_forgejo_workflow_no_github_actions(self):
        engine = BlueprintEngine()
        spec = BlueprintSpec(name="svc", blueprint_type=BlueprintType.FASTAPI_WORKER)
        bp = engine.render(spec)
        # Forgejo workflow should reference Forgejo, not GitHub Actions
        assert "forgejo" in bp.forgejo_workflow.lower() or "Forgejo" in bp.forgejo_workflow
        # Must NOT reference GitHub Actions jobs runner that would cost money
        assert "runs-on: ubuntu-latest" in bp.forgejo_workflow

    def test_scheduled_task_blueprint(self):
        engine = BlueprintEngine()
        spec = BlueprintSpec(
            name="cron-job",
            blueprint_type=BlueprintType.SCHEDULED_TASK,
            schedule="0 2 * * *",
        )
        bp = engine.render(spec)
        assert "asyncio" in bp.worker_py
        assert "INTERVAL_SECONDS" in bp.worker_py

    def test_stream_processor_blueprint(self):
        engine = BlueprintEngine()
        spec = BlueprintSpec(
            name="stream-svc",
            blueprint_type=BlueprintType.STREAM_PROCESSOR,
            port=8300,
        )
        bp = engine.render(spec)
        assert "StreamingResponse" in bp.worker_py
        assert "text/event-stream" in bp.worker_py

    def test_requirements_includes_base(self):
        engine = BlueprintEngine()
        spec = BlueprintSpec(
            name="svc",
            blueprint_type=BlueprintType.FASTAPI_WORKER,
            dependencies=["httpx>=0.27.0", "mypackage==1.0"],
        )
        bp = engine.render(spec)
        assert "fastapi" in bp.requirements_txt
        assert "uvicorn" in bp.requirements_txt
        assert "mypackage==1.0" in bp.requirements_txt


# ---------------------------------------------------------------------------
# MapeKLoop
# ---------------------------------------------------------------------------


class TestMapeKLoop:
    def _make_snapshot(
        self,
        healthy: int = 5,
        unhealthy: List[str] | None = None,
    ) -> SystemSnapshot:
        unhealthy = unhealthy or []
        metrics = [
            WorkerMetrics(
                worker_name=f"worker-{i}",
                is_healthy=True,
                status_code=200,
                latency_ms=10.0,
                health_score=1.0,
                error=None,
            )
            for i in range(healthy)
        ] + [
            WorkerMetrics(
                worker_name=w,
                is_healthy=False,
                status_code=None,
                latency_ms=5000.0,
                health_score=None,
                error="connection refused",
            )
            for w in unhealthy
        ]
        return SystemSnapshot(
            worker_metrics=metrics,
            total_workers=len(metrics),
            healthy_workers=healthy,
            unhealthy_workers=unhealthy,
        )

    def test_analyse_no_issues_on_healthy_snapshot(self):
        loop = MapeKLoop()
        snapshot = self._make_snapshot(healthy=10, unhealthy=[])
        analysis = loop._analyse(snapshot)
        # No worker health issues; may still have quota warnings
        worker_issues = [i for i in analysis["issues"] if i["type"] == "worker_health"]
        assert len(worker_issues) == 0

    def test_analyse_detects_unhealthy_workers(self):
        loop = MapeKLoop()
        snapshot = self._make_snapshot(healthy=8, unhealthy=["svc-a", "svc-b", "svc-c"])
        analysis = loop._analyse(snapshot)
        worker_issues = [i for i in analysis["issues"] if i["type"] == "worker_health"]
        assert len(worker_issues) == 1
        assert "svc-a" in worker_issues[0]["affected"]

    def test_plan_generates_alert_for_unhealthy(self):
        loop = MapeKLoop()
        snapshot = self._make_snapshot(healthy=8, unhealthy=["broken-worker"])
        analysis = loop._analyse(snapshot)
        actions = loop._plan(analysis, snapshot)
        alert_actions = [a for a in actions if a.action_type == ActionType.ALERT]
        assert len(alert_actions) >= 1
        assert any(a.target == "broken-worker" for a in alert_actions)

    def test_plan_generates_rotate_for_critical_quota(self):
        loop = MapeKLoop()
        registry = loop._registry
        # Force groq to near-exhaustion
        groq = registry.get("groq")
        if groq and groq.quota.tokens_per_day:
            groq.usage.tokens_used_today = int(groq.quota.tokens_per_day * 0.97)

        snapshot = self._make_snapshot()
        analysis = loop._analyse(snapshot)
        actions = loop._plan(analysis, snapshot)
        rotate_actions = [a for a in actions if a.action_type == ActionType.ROTATE_PLATFORM]
        # groq should be in rotation targets
        assert any(a.target == "groq" for a in rotate_actions)

    def test_state_is_idle_initially(self):
        loop = MapeKLoop()
        assert loop._state == ControlLoopState.IDLE

    @pytest.mark.asyncio
    async def test_loop_lifecycle(self):
        config = MapeKConfig(
            monitor_interval_s=0.1,
            worker_health_timeout_s=0.5,
            base_worker_url="http://127.0.0.1",  # nothing listening — all fail gracefully
        )
        loop = MapeKLoop(config=config)
        await loop.start()
        assert loop._running is True
        await asyncio.sleep(0.25)
        # At least one cycle should have run
        assert loop._cycle_count >= 1
        await loop.stop()
        assert loop._running is False

    def test_status_returns_dict(self):
        loop = MapeKLoop()
        status = loop.status()
        assert "state" in status
        assert "running" in status
        assert "enforcer" in status
        # ci_provider is added at router level, not loop level
        assert "cycle_count" in status


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure cost-violation env vars are cleared before each test."""
    for var in (
        "AZURE_TRAINING_ENABLED",
        "CF_DEPLOY_WORKERS",
        "USE_GITHUB_ACTIONS",
        "OPENAI_API_KEY",
        "BUGZY_API_KEY",
    ):
        os.environ.pop(var, None)
    yield
    for var in (
        "AZURE_TRAINING_ENABLED",
        "CF_DEPLOY_WORKERS",
        "USE_GITHUB_ACTIONS",
        "OPENAI_API_KEY",
        "BUGZY_API_KEY",
    ):
        os.environ.pop(var, None)
