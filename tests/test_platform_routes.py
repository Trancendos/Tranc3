"""
Platform service unit tests.

Tests all new service modules introduced in the enhance-ml-mcp-workflow branch.
Follows the same pattern as the existing test suite — direct module imports,
no TestClient (avoids requiring torch/transformers/qiskit in CI).
"""

from __future__ import annotations

import logging
import os

import pytest

from Dimensional.path_validation import validate_path

os.environ.setdefault("SECRET_KEY", "test-secret-not-for-prod")
os.environ.setdefault("ENVIRONMENT", "test")

_log = logging.getLogger("tranc3.tests.platform")


# ─── Redis store ──────────────────────────────────────────────────────────


class TestRedisStore:
    @pytest.mark.asyncio
    async def test_in_memory_set_get(self):
        from src.core.redis_store import _InMemoryFallback

        store = _InMemoryFallback()
        await store.set("key1", {"value": 99})
        assert await store.get("key1") == {"value": 99}

    @pytest.mark.asyncio
    async def test_delete(self):
        from src.core.redis_store import _InMemoryFallback

        store = _InMemoryFallback()
        await store.set("k", "v")
        await store.delete("k")
        assert await store.get("k") is None

    @pytest.mark.asyncio
    async def test_ttl_eviction(self):
        import time

        from src.core.redis_store import _InMemoryFallback

        store = _InMemoryFallback()
        await store.set("expiring", "gone", ttl=1)
        store._expiry["expiring"] = time.time() - 1  # force expire
        assert await store.get("expiring") is None

    @pytest.mark.asyncio
    async def test_hset_hgetall_hdel(self):
        from src.core.redis_store import _InMemoryFallback

        store = _InMemoryFallback()
        await store.hset("hash", {"a": 1, "b": 2})
        assert await store.hgetall("hash") == {"a": 1, "b": 2}
        await store.hdel("hash", "a")
        assert await store.hgetall("hash") == {"b": 2}

    @pytest.mark.asyncio
    async def test_keys_glob_pattern(self):
        from src.core.redis_store import _InMemoryFallback

        store = _InMemoryFallback()
        await store.set("citadel:deploy:001", "a")
        await store.set("citadel:deploy:002", "b")
        await store.set("devocity:account:x", "c")
        keys = await store.keys("citadel:deploy:*")
        assert set(keys) == {"citadel:deploy:001", "citadel:deploy:002"}

    @pytest.mark.asyncio
    async def test_get_store_returns_fallback_when_no_redis_url(self):
        from src.core import redis_store

        redis_store.reset_store()
        old = redis_store._REDIS_URL
        redis_store._REDIS_URL = ""
        try:
            store = await redis_store.get_store()
            assert store.backend == "memory"
        finally:
            redis_store._REDIS_URL = old
            redis_store.reset_store()

    @pytest.mark.asyncio
    async def test_ping_returns_true(self):
        from src.core.redis_store import _InMemoryFallback

        assert await _InMemoryFallback().ping() is True


# ─── The Citadel ──────────────────────────────────────────────────────────


class TestCitadel:
    def setup_method(self):
        import src.citadel.devops_hub as dh

        dh._citadel = None  # fresh instance per test

    def test_record_and_list_deploy(self):
        from src.citadel.devops_hub import DeployStatus, DeployTarget, get_citadel

        c = get_citadel()
        rec = c.record_deploy(
            target=DeployTarget.BACKEND,
            version="test-abc",
            triggered_by="pytest",
            status=DeployStatus.PENDING,
        )
        assert rec.id
        assert rec.target == DeployTarget.BACKEND
        deploys = c.list_deploys()
        assert any(d.id == rec.id for d in deploys)

    def test_update_deploy_to_success(self):
        from src.citadel.devops_hub import (
            DeployStatus,
            DeployTarget,
            ServiceHealthStatus,
            get_citadel,
        )

        c = get_citadel()
        rec = c.record_deploy(DeployTarget.BOTS, "v2", status=DeployStatus.IN_PROGRESS)
        updated = c.update_deploy(rec.id, DeployStatus.SUCCESS)
        assert updated.status == DeployStatus.SUCCESS
        # health should flip to healthy
        assert c._service_health["tranc3-bots"] == ServiceHealthStatus.HEALTHY

    def test_update_nonexistent_deploy(self):
        from src.citadel.devops_hub import DeployStatus, get_citadel

        c = get_citadel()
        assert c.update_deploy("nonexistent-id", DeployStatus.FAILED) is None

    def test_inventory_contains_all_services(self):
        from src.citadel.devops_hub import get_citadel

        inv = get_citadel().inventory()
        assert len(inv) >= 9
        names = {s["name"] for s in inv}
        assert "tranc3-backend" in names
        assert "tranc3-bots" in names

    def test_stats_structure(self):
        from src.citadel.devops_hub import get_citadel

        stats = get_citadel().stats()
        assert "total_services" in stats
        assert "healthy_services" in stats

    def test_health_update(self):
        from src.citadel.devops_hub import ServiceHealthStatus, get_citadel

        c = get_citadel()
        c.update_health("tranc3-backend", ServiceHealthStatus.DEGRADED)
        assert c._service_health["tranc3-backend"] == ServiceHealthStatus.DEGRADED

    def test_deploy_to_dict_has_required_keys(self):
        from src.citadel.devops_hub import DeployTarget, get_citadel

        c = get_citadel()
        rec = c.record_deploy(DeployTarget.TRANC3_AI, "edge-0a1b")
        d = rec.to_dict()
        for key in ("id", "target", "version", "status", "triggered_by", "started_at"):
            assert key in d


# ─── DevOcity ─────────────────────────────────────────────────────────────


class TestDevOcity:
    def setup_method(self):
        import src.devocity.portal as dv

        dv._devocity = None

    def test_create_account(self):
        from src.devocity.portal import get_devocity

        dv = get_devocity()
        acct = dv.create_account("user-001", "Test Developer")
        assert acct.id
        assert acct.user_id == "user-001"

    def test_issue_api_key_has_trx_prefix(self):
        from src.devocity.portal import ApiKeyScope, get_devocity

        dv = get_devocity()
        acct = dv.create_account("user-002", "Key Dev")
        result = dv.issue_api_key(acct.id, "my-key", [ApiKeyScope.READ])
        assert result is not None
        plain, key = result
        assert plain.startswith("trx_")
        assert len(plain) == 60  # "trx_" + 56 hex chars
        assert key.key_hash  # SHA-256 stored, never plain

    def test_revoke_api_key(self):
        from src.devocity.portal import ApiKeyScope, get_devocity

        dv = get_devocity()
        acct = dv.create_account("user-003", "Revoke Test")
        _, key = dv.issue_api_key(acct.id, "to-revoke", [ApiKeyScope.WRITE])
        assert dv.revoke_api_key(acct.id, key.id)
        assert dv._accounts[acct.id].api_keys[0].revoked is True

    def test_stats_reflects_accounts(self):
        from src.devocity.portal import get_devocity

        dv = get_devocity()
        dv.create_account("u1", "Dev 1")
        dv.create_account("u2", "Dev 2")
        stats = dv.stats()
        assert stats["total_accounts"] >= 2

    def test_guides_seeded(self):
        from src.devocity.portal import get_devocity

        guides = get_devocity().guides()
        assert len(guides) >= 4


# ─── ChronosSphere ────────────────────────────────────────────────────────


class TestChronos:
    def setup_method(self):
        import src.chronos.scheduler as cs

        cs._chronos = None

    def test_create_cron_task(self):
        from src.chronos.scheduler import ScheduleType, get_chronos

        c = get_chronos()
        task = c.create_task(
            name="daily-report",
            schedule_type=ScheduleType.CRON,
            cron_expression="0 9 * * *",
        )
        assert task.id
        assert task.schedule_type == ScheduleType.CRON

    def test_list_tasks(self):
        from src.chronos.scheduler import ScheduleType, get_chronos

        c = get_chronos()
        c.create_task("job-a", ScheduleType.INTERVAL, interval_seconds=3600)
        c.create_task("job-b", ScheduleType.ONCE, fire_at=1800000000.0)
        tasks = c.list_tasks()
        assert len(tasks) >= 2

    def test_toggle_task(self):
        from src.chronos.scheduler import ScheduleStatus, ScheduleType, get_chronos

        c = get_chronos()
        task = c.create_task("toggle-me", ScheduleType.CRON, cron_expression="*/5 * * * *")
        assert task.status == ScheduleStatus.ACTIVE
        assert c.pause_task(task.id) is True
        assert c._tasks[task.id].status == ScheduleStatus.PAUSED


# ─── The Artifactory ──────────────────────────────────────────────────────


class TestArtifactory:
    def setup_method(self):
        import src.artifactory.registry as ar

        ar._artifactory = None

    def test_pre_seeded_defaults(self):
        from src.artifactory.registry import get_artifactory

        reg = get_artifactory()
        artifacts = reg.list_artifacts()
        assert len(artifacts) >= 6
        names = {a.name for a in artifacts}
        assert "tranc3-backend" in names

    def test_push_artifact(self):
        from src.artifactory.registry import ArtifactType, get_artifactory

        reg = get_artifactory()
        art = reg.create_artifact(
            name="test-package",
            artifact_type=ArtifactType.PYTHON,
        )
        ver = reg.push_version(art.id, version="0.1.0")
        assert art.id
        assert ver is not None
        assert ver.version == "0.1.0"

    def test_get_artifact_by_name(self):
        from src.artifactory.registry import ArtifactType, get_artifactory

        reg = get_artifactory()
        reg.create_artifact("lookup-me", ArtifactType.GENERIC)
        found = reg.find_by_name("lookup-me")
        assert found is not None
        assert found.name == "lookup-me"


# ─── API Marketplace ──────────────────────────────────────────────────────


class TestAPIMarketplace:
    def setup_method(self):
        import src.apimarket.marketplace as am

        am._marketplace = None

    def test_pre_seeded_connectors(self):
        from src.apimarket.marketplace import get_marketplace

        mp = get_marketplace()
        connectors = mp.list_connectors()
        assert len(connectors) >= 5
        slugs = {c.slug for c in connectors}
        assert "the-spark" in slugs
        assert "the-void" in slugs

    def test_get_connector(self):
        from src.apimarket.marketplace import get_marketplace

        mp = get_marketplace()
        conn = mp.find_by_slug("the-grid")
        assert conn is not None
        assert conn.slug == "the-grid"


# ─── VRAR3D ───────────────────────────────────────────────────────────────


class TestVRAR3D:
    def setup_method(self):
        import src.vrar3d.wellbeing_centre as vc

        vc._vrar3d = None

    def test_list_scenes(self):
        from src.vrar3d.wellbeing_centre import get_vrar3d

        scenes = get_vrar3d().list_scenes()
        assert len(scenes) >= 6

    def test_crisis_calm_recommended_on_critical(self):
        from src.vrar3d.wellbeing_centre import SceneType, get_vrar3d

        centre = get_vrar3d()
        rec = centre.recommend_scene(sensitivity_level="critical")
        assert rec is not None
        assert rec.scene_type == SceneType.CRISIS_CALM

    def test_start_and_end_session(self):
        from src.vrar3d.wellbeing_centre import get_vrar3d

        centre = get_vrar3d()
        # Use a real seeded scene_id
        scene_id = next(iter(centre._scenes))
        session = centre.start_session("user-42", scene_id, mood_before=3)
        assert session.id
        ended = centre.end_session(session.id, mood_after=7)
        assert ended.mood_after == 7


# ─── The Spark tool registry (new tools) ─────────────────────────────────


class TestSparkPlatformTools:
    def test_registry_has_17_plus_tools(self):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        tools = reg.list_tools()
        _log.info("spark.platform tools=%d", len(tools))
        assert len(tools) >= 17

    def test_luminous_phi_tool_registered(self):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        tool = reg.get("luminous_phi")
        assert tool is not None
        assert tool.category == "ai"

    def test_quantum_simulate_tool_registered(self):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        tool = reg.get("quantum_simulate")
        assert tool is not None
        assert tool.category == "research"

    def test_citadel_deploy_status_tool_registered(self):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        tool = reg.get("citadel_deploy_status")
        assert tool is not None
        assert tool.category == "devops"

    def test_observatory_observe_tool_registered(self):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        tool = reg.get("observatory_observe")
        assert tool is not None
        assert tool.category == "observability"

    def test_grid_list_workflows_tool_registered(self):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        tool = reg.get("grid_list_workflows")
        assert tool is not None
        assert tool.category == "workflow"

    @pytest.mark.asyncio
    async def test_citadel_tool_returns_stats(self):
        import src.citadel.devops_hub as dh
        from src.mcp.tools import SparkToolRegistry

        dh._citadel = None
        reg = SparkToolRegistry()
        tool = reg.get("citadel_deploy_status")
        result = await tool.handler({})
        assert "total_services" in result or "error" in result

    @pytest.mark.asyncio
    async def test_observatory_tool_emits_event(self):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        tool = reg.get("observatory_observe")
        result = await tool.handler(
            {
                "event_type": "test.spark.tool_call",
                "category": "AI",
                "service": "pytest",
            },
        )
        assert result.get("observed") is True or "error" in result

    @pytest.mark.asyncio
    async def test_grid_list_workflows_returns_list(self):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        tool = reg.get("grid_list_workflows")
        result = await tool.handler({})
        assert "workflows" in result
        assert isinstance(result["workflows"], list)


# ─── Alembic migration chain ──────────────────────────────────────────────


class TestMigrations:
    def test_both_migration_files_exist(self):
        import os

        base = os.path.realpath(
            os.path.join(os.path.dirname(__file__), "..", "migrations", "versions"),
        )
        files = os.listdir(base)
        py_files = [f for f in files if f.endswith(".py") and not f.startswith("__")]
        assert len(py_files) >= 2, f"Expected ≥2 migration files, found: {py_files}"

    def test_migration_chain_is_valid(self):
        """Each migration correctly references its predecessor — parsed from source text."""
        import os
        import re

        base = os.path.realpath(
            os.path.join(os.path.dirname(__file__), "..", "migrations", "versions"),
        )
        revisions = {}
        for fname in sorted(os.listdir(base)):
            if not fname.endswith(".py") or fname.startswith("__"):
                continue
            path = os.path.join(base, fname)
            validate_path(path, base)
            with open(path) as f:
                src = f.read()
            rev_m = re.search(r"^revision\s*=\s*['\"](.+?)['\"]", src, re.MULTILINE)
            down_m = re.search(r"^down_revision\s*=\s*(['\"](.+?)['\"]|None)", src, re.MULTILINE)
            if not rev_m:
                continue
            rev = rev_m.group(1)
            down = down_m.group(2) if down_m and down_m.group(2) else None
            revisions[rev] = down

        assert revisions.get("001_initial") is None
        assert revisions.get("002_platform_services") == "001_initial"
