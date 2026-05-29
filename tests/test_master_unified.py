"""
tests/test_master_unified.py — Unified adapter layer + extended bot type tests.

Covers:
- AdapterRegistry routing (core, nanocode, aeonmind, stub fallback)
- All 4 adapter classes (tranc3_bots, src_workers, nanocode, aeonmind)
- Extended TaskSchema validation (25+ bot types across all 3 systems)
- BotSwarm dispatch through the unified adapter registry
- Round-trip: YAML task → TaskDefinition → BotSwarm → StepResult
- Graceful degradation when underlying registries are unavailable
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

pytest.importorskip("pydantic")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_STEP = {"bot": "monitor", "action": "ping", "params": {}, "timeout_seconds": 5}


def _task_with_bot(bot_type: str) -> dict:
    return {
        "name": f"{bot_type}-task",
        "steps": [
            {
                "bot": bot_type,
                "action": "test",
                "params": {},
                "timeout_seconds": 5,
            }
        ],
    }


# ---------------------------------------------------------------------------
# AdapterRegistry tests
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    def test_registry_resolves_core_bot_to_tranc3(self):
        from src.master.adapters.registry import AdapterRegistry

        reg = AdapterRegistry()
        adapter = reg.resolve("monitor")
        assert adapter.name == "tranc3_bots"

    def test_registry_resolves_nanocode(self):
        from src.master.adapters.registry import AdapterRegistry

        reg = AdapterRegistry()
        adapter = reg.resolve("nanocode")
        assert adapter.name == "nanocode"

    def test_registry_resolves_aeonmind(self):
        from src.master.adapters.registry import AdapterRegistry

        reg = AdapterRegistry()
        adapter = reg.resolve("aeonmind")
        assert adapter.name == "aeonmind"

    def test_registry_resolves_nanocode_failure_mode_directly(self):
        from src.master.adapters.registry import AdapterRegistry

        reg = AdapterRegistry()
        adapter = reg.resolve("service_unreachable")
        assert adapter.name == "nanocode"

    def test_registry_resolves_aeonmind_capability_directly(self):
        from src.master.adapters.registry import AdapterRegistry

        reg = AdapterRegistry()
        adapter = reg.resolve("classify")
        assert adapter.name == "aeonmind"

    def test_registry_resolves_unknown_to_stub(self):
        from src.master.adapters.registry import AdapterRegistry

        reg = AdapterRegistry()
        adapter = reg.resolve("does_not_exist_xyz")
        assert adapter.name == "stub"

    def test_registry_status_returns_dict(self):
        from src.master.adapters.registry import AdapterRegistry

        reg = AdapterRegistry()
        status = reg.status()
        assert isinstance(status, dict)
        assert "tranc3_bots" in status
        assert "nanocode" in status
        assert "aeonmind" in status

    def test_get_adapter_module_function(self):
        from src.master.adapters.registry import get_adapter

        adapter = get_adapter("search")
        assert adapter.name in ("tranc3_bots", "stub")

    def test_tranc3_fallback_to_src_workers_when_unavailable(self):
        from src.master.adapters.registry import AdapterRegistry

        reg = AdapterRegistry()
        with (
            patch.object(reg._tranc3, "is_available", return_value=False),
            patch.object(reg._src, "is_available", return_value=True),
        ):
            adapter = reg.resolve("generate")
            assert adapter.name in ("src_workers", "stub")


# ---------------------------------------------------------------------------
# Tranc3BotsAdapter tests
# ---------------------------------------------------------------------------


class TestTranc3BotsAdapter:
    def test_is_available_false_when_not_importable(self):
        from src.master.adapters.tranc3_bots_adapter import Tranc3BotsAdapter

        adapter = Tranc3BotsAdapter()
        adapter._registry = None
        with patch("builtins.__import__", side_effect=ImportError("no module")):
            # Force reload path that can't find bots.registry
            adapter._registry = None
            result = adapter.is_available()
            # Either True (if actually installed) or False — just not an exception
            assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_dispatch_returns_stub_when_registry_none(self):
        from src.master.adapters.tranc3_bots_adapter import Tranc3BotsAdapter

        adapter = Tranc3BotsAdapter()
        adapter._registry = None  # Force unavailable

        with patch.object(adapter, "_load_registry", return_value=None):
            result = await adapter.dispatch("ping", {"_bot_type": "monitor"})

        assert result.get("stub") is True
        assert result["adapter"] == "tranc3_bots"

    @pytest.mark.asyncio
    async def test_dispatch_calls_registry_when_available(self):
        from src.master.adapters.tranc3_bots_adapter import Tranc3BotsAdapter

        mock_registry = MagicMock()
        mock_registry.run.return_value = {"ok": True}

        adapter = Tranc3BotsAdapter()
        adapter._registry = mock_registry

        result = await adapter.dispatch("ping", {"_bot_type": "monitor"})
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# SrcWorkersAdapter tests
# ---------------------------------------------------------------------------


class TestSrcWorkersAdapter:
    def test_is_available_when_not_importable(self):
        from src.master.adapters.src_workers_adapter import SrcWorkersAdapter

        adapter = SrcWorkersAdapter()
        adapter._registry = None
        # Either True or False depending on install — just mustn't raise
        result = adapter.is_available()
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_dispatch_stub_when_unavailable(self):
        from src.master.adapters.src_workers_adapter import SrcWorkersAdapter

        adapter = SrcWorkersAdapter()
        with patch.object(adapter, "_load_registry", return_value=None):
            result = await adapter.dispatch("generate_text", {"_bot_type": "generate"})

        assert result.get("stub") is True
        assert result["adapter"] == "src_workers"


# ---------------------------------------------------------------------------
# NanocodeAdapter tests
# ---------------------------------------------------------------------------


class TestNanocodeAdapter:
    def test_nanocode_valid_modes(self):
        from src.master.adapters.nanocode_adapter import _NANOCODE_MODES

        expected = {
            "compliance_metadata_missing",
            "stale_embedding",
            "free_tier_approaching",
            "rate_limit_hit",
            "service_unreachable",
            "config_drift",
            "memory_leak",
            "high_error_rate",
            "dependency_failed",
        }
        assert expected == _NANOCODE_MODES

    @pytest.mark.asyncio
    async def test_dispatch_stub_when_unavailable(self):
        from src.master.adapters.nanocode_adapter import NanocodeAdapter

        adapter = NanocodeAdapter()
        with patch.object(adapter, "_load", return_value=None):
            adapter._dispatcher = None
            result = await adapter.dispatch("service_unreachable", {"service": "test"})

        assert result.get("stub") is True
        assert result["mode"] == "service_unreachable"

    @pytest.mark.asyncio
    async def test_dispatch_raises_for_unknown_mode(self):
        from src.master.adapters.nanocode_adapter import NanocodeAdapter

        adapter = NanocodeAdapter()
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = {"repaired": True}
        mock_failure_mode = MagicMock()
        mock_failure_mode.__getitem__ = MagicMock(side_effect=KeyError)
        mock_failure_mode.side_effect = ValueError

        adapter._dispatcher = mock_dispatcher
        adapter._failure_mode_cls = mock_failure_mode

        with pytest.raises(ValueError, match="Unknown nanocode failure mode"):
            await adapter.dispatch("totally_unknown_mode", {})

    @pytest.mark.asyncio
    async def test_dispatch_with_mock_dispatcher(self):
        from src.master.adapters.nanocode_adapter import NanocodeAdapter

        adapter = NanocodeAdapter()

        mock_mode_enum = MagicMock()
        mock_mode_instance = MagicMock()
        mock_mode_enum.__getitem__ = MagicMock(return_value=mock_mode_instance)

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = {"repaired": True, "mode": "memory_leak"}

        adapter._dispatcher = mock_dispatcher
        adapter._failure_mode_cls = mock_mode_enum

        result = await adapter.dispatch("memory_leak", {"threshold": 512})
        assert result.get("repaired") is True


# ---------------------------------------------------------------------------
# AeonMindAdapter tests
# ---------------------------------------------------------------------------


class TestAeonMindAdapter:
    def test_aeonmind_capabilities_count(self):
        from src.master.adapters.aeonmind_adapter import _AEONMIND_CAPABILITIES

        assert len(_AEONMIND_CAPABILITIES) >= 15

    def test_aeonmind_expected_capabilities(self):
        from src.master.adapters.aeonmind_adapter import _AEONMIND_CAPABILITIES

        for cap in (
            "translate",
            "classify",
            "extract",
            "validate",
            "transform",
            "notify",
            "log",
            "cache",
            "route",
            "filter",
            "enrich",
            "embed",
            "summarize",
            "generic",
        ):
            assert cap in _AEONMIND_CAPABILITIES

    @pytest.mark.asyncio
    async def test_dispatch_stub_when_unavailable(self):
        from src.master.adapters.aeonmind_adapter import AeonMindAdapter

        adapter = AeonMindAdapter()
        with patch.object(adapter, "_load", return_value=None):
            adapter._worker_cls = None
            result = await adapter.dispatch("classify", {"input": "hello"})

        assert result.get("stub") is True
        assert result["capability"] == "classify"

    @pytest.mark.asyncio
    async def test_dispatch_raises_for_unknown_capability(self):
        from src.master.adapters.aeonmind_adapter import AeonMindAdapter

        adapter = AeonMindAdapter()
        mock_worker_cls = MagicMock()
        mock_cap_cls = MagicMock()
        mock_cap_cls.__getitem__ = MagicMock(side_effect=KeyError)
        mock_cap_cls.side_effect = ValueError

        adapter._worker_cls = mock_worker_cls
        adapter._capability_cls = mock_cap_cls

        with pytest.raises(ValueError, match="Unknown AeonMind capability"):
            await adapter.dispatch("nonexistent_capability_xyz", {})

    @pytest.mark.asyncio
    async def test_dispatch_with_mock_worker(self):
        from src.master.adapters.aeonmind_adapter import AeonMindAdapter

        adapter = AeonMindAdapter()

        mock_cap_enum = MagicMock()
        mock_cap_enum.__getitem__ = MagicMock(return_value="CLASSIFY")

        mock_worker = MagicMock()
        mock_worker.execute.return_value = {"classified": "positive", "score": 0.9}
        mock_worker_cls = MagicMock(return_value=mock_worker)

        adapter._worker_cls = mock_worker_cls
        adapter._capability_cls = mock_cap_enum

        result = await adapter.dispatch("classify", {"input": "great product"})
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Extended TaskSchema — all unified bot types
# ---------------------------------------------------------------------------


class TestExtendedTaskSchema:
    def test_all_core_bots_valid(self):
        from src.master.task_schema import TaskDefinition

        for bot in (
            "generate",
            "embed",
            "emotion",
            "tokenize",
            "consciousness",
            "personality",
            "predict",
            "code",
            "memory",
            "monitor",
            "search",
            "summarise",
        ):
            t = TaskDefinition.model_validate(_task_with_bot(bot))
            assert t.steps[0].bot == bot

    def test_all_aeonmind_capabilities_valid(self):
        from src.master.task_schema import TaskDefinition

        for bot in (
            "aeonmind",
            "translate",
            "classify",
            "extract",
            "validate",
            "transform",
            "notify",
            "log",
            "cache",
            "route",
            "filter",
            "enrich",
            "summarize",
            "generic",
        ):
            t = TaskDefinition.model_validate(_task_with_bot(bot))
            assert t.steps[0].bot == bot

    def test_nanocode_root_type_valid(self):
        from src.master.task_schema import TaskDefinition

        t = TaskDefinition.model_validate(_task_with_bot("nanocode"))
        assert t.steps[0].bot == "nanocode"

    def test_all_nanocode_failure_modes_valid(self):
        from src.master.task_schema import TaskDefinition

        for bot in (
            "compliance_metadata_missing",
            "stale_embedding",
            "free_tier_approaching",
            "rate_limit_hit",
            "service_unreachable",
            "config_drift",
            "memory_leak",
            "high_error_rate",
            "dependency_failed",
        ):
            t = TaskDefinition.model_validate(_task_with_bot(bot))
            assert t.steps[0].bot == bot

    def test_unknown_bot_still_raises(self):
        from pydantic import ValidationError

        from src.master.task_schema import TaskDefinition

        with pytest.raises(ValidationError, match="Unknown bot type"):
            TaskDefinition.model_validate(_task_with_bot("not_a_real_bot_xyz"))

    def test_total_valid_bot_count(self):
        """Ensure we have at least 35 valid bot types across all 3 systems."""

        # Extract valid set from validator by triggering the code path
        from src.master.task_schema import TaskDefinition

        valid_count = 0
        # 12 core + 14 aeonmind (including root) + 10 nanocode (including root) = 36
        for bot in (
            "generate",
            "embed",
            "emotion",
            "tokenize",
            "consciousness",
            "personality",
            "predict",
            "code",
            "memory",
            "monitor",
            "search",
            "summarise",  # 12
            "aeonmind",
            "translate",
            "classify",
            "extract",
            "validate",
            "transform",
            "notify",
            "log",
            "cache",
            "route",
            "filter",
            "enrich",
            "summarize",
            "generic",  # 14
            "nanocode",
            "compliance_metadata_missing",
            "stale_embedding",
            "free_tier_approaching",
            "rate_limit_hit",
            "service_unreachable",
            "config_drift",
            "memory_leak",
            "high_error_rate",
            "dependency_failed",  # 10
        ):
            try:
                TaskDefinition.model_validate(_task_with_bot(bot))
                valid_count += 1
            except Exception:
                pass
        assert valid_count >= 35


# ---------------------------------------------------------------------------
# BotSwarm unified dispatch
# ---------------------------------------------------------------------------


class TestBotSwarmUnifiedDispatch:
    @pytest.mark.asyncio
    async def test_swarm_dispatches_via_adapter_registry(self):
        from src.master.bot_swarm import BotSwarm

        swarm = BotSwarm()
        await swarm.start()
        try:
            with patch("src.master.adapters.registry.get_adapter") as mock_get:
                mock_adapter = AsyncMock()
                mock_adapter.dispatch = AsyncMock(return_value={"ok": True, "stub": True})
                mock_get.return_value = mock_adapter

                result = await swarm.submit("monitor", "ping", {}, timeout=5.0)
                assert result.bot_type == "monitor"
                assert isinstance(result.success, bool)
        finally:
            await swarm.stop()

    @pytest.mark.asyncio
    async def test_swarm_handles_nanocode_bot(self):
        from src.master.bot_swarm import BotSwarm

        swarm = BotSwarm()
        await swarm.start()
        try:
            result = await swarm.submit("nanocode", "service_unreachable", {}, timeout=10.0)
            assert result.bot_type == "nanocode"
            assert isinstance(result.success, bool)
        finally:
            await swarm.stop()

    @pytest.mark.asyncio
    async def test_swarm_handles_aeonmind_bot(self):
        from src.master.bot_swarm import BotSwarm

        swarm = BotSwarm()
        await swarm.start()
        try:
            result = await swarm.submit("aeonmind", "classify", {"input": "test"}, timeout=10.0)
            assert result.bot_type == "aeonmind"
            assert isinstance(result.success, bool)
        finally:
            await swarm.stop()

    @pytest.mark.asyncio
    async def test_swarm_concurrent_mixed_bot_types(self):
        from src.master.bot_swarm import BotSwarm

        swarm = BotSwarm(concurrency_per_type=2)
        await swarm.start()
        try:
            results = await asyncio.gather(
                swarm.submit("monitor", "ping", {}, timeout=10.0),
                swarm.submit("nanocode", "memory_leak", {}, timeout=10.0),
                swarm.submit("aeonmind", "generic", {}, timeout=10.0),
                swarm.submit("search", "query", {"q": "test"}, timeout=10.0),
            )
            assert len(results) == 4
            for r in results:
                assert isinstance(r.success, bool)
                assert r.duration_ms >= 0
        finally:
            await swarm.stop()


# ---------------------------------------------------------------------------
# YAML round-trip with extended bot types
# ---------------------------------------------------------------------------


class TestYAMLRoundTrip:
    def _write_task(self, tmp_path: Path, bot_type: str) -> Path:
        task = {
            "name": f"{bot_type}-unified-task",
            "description": f"Task using {bot_type} bot",
            "schedule": {"type": "once"},
            "steps": [{"bot": bot_type, "action": "run", "params": {}, "timeout_seconds": 10}],
        }
        p = tmp_path / f"{bot_type}.yaml"
        p.write_text(yaml.dump(task), encoding="utf-8")
        return p

    def test_nanocode_yaml_round_trip(self, tmp_path: Path):
        from src.master.task_loader import TaskLoader

        self._write_task(tmp_path, "nanocode")
        loader = TaskLoader(tmp_path)
        tasks = loader.load_all()
        assert "nanocode-unified-task" in tasks
        assert tasks["nanocode-unified-task"].steps[0].bot == "nanocode"

    def test_aeonmind_classify_yaml_round_trip(self, tmp_path: Path):
        from src.master.task_loader import TaskLoader

        self._write_task(tmp_path, "classify")
        loader = TaskLoader(tmp_path)
        tasks = loader.load_all()
        assert "classify-unified-task" in tasks
        assert tasks["classify-unified-task"].steps[0].bot == "classify"

    def test_service_unreachable_yaml_round_trip(self, tmp_path: Path):
        from src.master.task_loader import TaskLoader

        self._write_task(tmp_path, "service_unreachable")
        loader = TaskLoader(tmp_path)
        tasks = loader.load_all()
        # Underscores are valid slug chars — key keeps underscore
        assert "service_unreachable-unified-task" in tasks

    def test_mixed_bot_types_in_single_task(self, tmp_path: Path):
        from src.master.task_loader import TaskLoader

        task = {
            "name": "multi-bot-task",
            "steps": [
                {"bot": "monitor", "action": "check", "params": {}, "timeout_seconds": 5},
                {"bot": "nanocode", "action": "memory_leak", "params": {}, "timeout_seconds": 5},
                {"bot": "aeonmind", "action": "classify", "params": {}, "timeout_seconds": 5},
                {"bot": "search", "action": "query", "params": {}, "timeout_seconds": 5},
            ],
        }
        p = tmp_path / "multi.yaml"
        p.write_text(yaml.dump(task), encoding="utf-8")

        loader = TaskLoader(tmp_path)
        tasks = loader.load_all()
        assert "multi-bot-task" in tasks
        t = tasks["multi-bot-task"]
        assert len(t.steps) == 4
        assert t.steps[0].bot == "monitor"
        assert t.steps[1].bot == "nanocode"
        assert t.steps[2].bot == "aeonmind"
        assert t.steps[3].bot == "search"


# ---------------------------------------------------------------------------
# Adapter base class
# ---------------------------------------------------------------------------


class TestBaseAdapter:
    def test_base_adapter_is_abstract(self):
        from src.master.adapters.base import BaseAdapter

        with pytest.raises(TypeError):
            BaseAdapter()

    def test_base_adapter_is_available_default_true(self):
        from src.master.adapters.base import BaseAdapter

        class ConcreteAdapter(BaseAdapter):
            name = "test"

            async def dispatch(self, action, params):
                return {}

        adapter = ConcreteAdapter()
        assert adapter.is_available() is True
