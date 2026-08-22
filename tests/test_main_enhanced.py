"""Tests for src/main_enhanced.py (TRANC3Enhanced).

Combined from four PRs that each created this file from scratch to test a
different method, with no overlapping test names: #902 (initialize, after the
split into _init_* methods), #905 (start_background_services), #906
(get_system_health), #874 (call_mcp_tool) and #904 (execute_workflow).

#904 originally created tests/unit/test_main_enhanced.py. tests/ is a
package but tests/unit/ would not have been one, so that path collides with
this file's basename at collection time; its tests live here instead.

A fifth, #879, is deliberately not carried over. It assigned
sys.modules["torch"] = MagicMock() at module import time, which leaks into every
later test in the session rather than being scoped to its own test. Its
initialize() coverage is already served by test_initialize_calls_private_methods.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main_enhanced import TRANC3Enhanced


@pytest.fixture
def enhanced_app():
    return TRANC3Enhanced()


# ── initialize (#902) ────────────────────────────────────────────────────────


def test_initialize_calls_private_methods(enhanced_app):
    with (
        patch.object(enhanced_app, "_init_mcp") as mock_mcp,
        patch.object(enhanced_app, "_init_workflow") as mock_workflow,
        patch.object(enhanced_app, "_init_deepmind") as mock_deepmind,
        patch.object(enhanced_app, "_init_healing") as mock_healing,
        patch.object(enhanced_app, "_init_skills") as mock_skills,
        patch.object(enhanced_app, "_init_code_generator") as mock_code_generator,
        patch.object(enhanced_app, "_init_tranc3_engine") as mock_tranc3,
        patch.object(enhanced_app, "_init_hybrid_engine") as mock_hybrid,
        patch.object(enhanced_app, "_init_2060_systems") as mock_2060,
    ):
        asyncio.run(enhanced_app.initialize())

        mock_mcp.assert_called_once()
        mock_workflow.assert_called_once()
        mock_deepmind.assert_called_once()
        mock_healing.assert_called_once()
        mock_skills.assert_called_once()
        mock_code_generator.assert_called_once()
        mock_tranc3.assert_called_once()
        mock_hybrid.assert_called_once()
        mock_2060.assert_called_once()

        assert enhanced_app._initialized is True


def test_init_skills(enhanced_app):
    # This module actually exists and loads fine during pytest
    with patch("src.skills.enhanced_registry.registry", MagicMock()) as mock_registry:
        enhanced_app._init_skills()
        assert enhanced_app._subsystems["skill_registry"] == mock_registry


# ── start_background_services (#905) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_background_services_all_enabled():
    app = TRANC3Enhanced()
    app.config["healing"] = {"auto_repair": True}

    mock_monitor = MagicMock()
    app._subsystems["health_monitor"] = mock_monitor

    mock_tuner = MagicMock()
    app._subsystems["config_tuner"] = mock_tuner

    with patch("src.main_enhanced.asyncio.create_task") as mock_create_task:
        with patch.object(
            app, "_tuning_loop", MagicMock(return_value="mock_coro_tuning")
        ) as mock_tuning_loop:
            mock_monitor.run_continuous.return_value = "mock_coro_monitor"

            await app.start_background_services()

            assert mock_create_task.call_count == 2
            mock_monitor.run_continuous.assert_called_once()
            mock_tuning_loop.assert_called_once_with(mock_tuner)

            mock_create_task.assert_any_call("mock_coro_monitor")
            mock_create_task.assert_any_call("mock_coro_tuning")


@pytest.mark.asyncio
async def test_start_background_services_auto_repair_false():
    app = TRANC3Enhanced()
    app.config["healing"] = {"auto_repair": False}

    mock_monitor = MagicMock()
    app._subsystems["health_monitor"] = mock_monitor

    mock_tuner = MagicMock()
    app._subsystems["config_tuner"] = mock_tuner

    with patch("src.main_enhanced.asyncio.create_task") as mock_create_task:
        with patch.object(
            app, "_tuning_loop", MagicMock(return_value="mock_coro_tuning")
        ) as mock_tuning_loop:
            await app.start_background_services()

            assert mock_create_task.call_count == 1
            mock_monitor.run_continuous.assert_not_called()
            mock_tuning_loop.assert_called_once_with(mock_tuner)
            mock_create_task.assert_any_call("mock_coro_tuning")


@pytest.mark.asyncio
async def test_start_background_services_missing_subsystems():
    app = TRANC3Enhanced()
    app.config["healing"] = {"auto_repair": True}

    with patch("src.main_enhanced.asyncio.create_task") as mock_create_task:
        with patch.object(app, "_tuning_loop") as mock_tuning_loop:
            await app.start_background_services()

            assert mock_create_task.call_count == 0
            mock_tuning_loop.assert_not_called()


# ── get_system_health (#906) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_system_health():
    class MockMonitor:
        def get_dashboard(self):
            return {"cpu": "ok"}

    class MockEvolution:
        def get_stats(self):
            return {"generations": 5}

    class MockSkillRegistry:
        def get_stats(self):
            return {"skills": 10}

    class MockBotDispatcher:
        def get_bot_stats(self):
            return {"active_bots": 3}

    system = TRANC3Enhanced()
    system._subsystems = {
        "health_monitor": MockMonitor(),
        "evolution": MockEvolution(),
        "skill_registry": MockSkillRegistry(),
        "bot_dispatcher": MockBotDispatcher(),
    }
    system._initialized = True

    health = await system.get_system_health()

    assert health["services"] == {"cpu": "ok"}
    assert health["evolution"] == {"generations": 5}
    assert health["skills"] == {"skills": 10}
    assert health["bots"] == {"active_bots": 3}
    assert "health_monitor" in health["subsystems_active"]
    assert health["initialized"] is True


@pytest.mark.asyncio
async def test_get_system_health_empty():
    system = TRANC3Enhanced()
    system._subsystems = {}
    system._initialized = False

    health = await system.get_system_health()

    assert health["services"] == {}
    assert health["evolution"] == {}
    assert health["skills"] == {}
    assert health["bots"] == {}
    assert health["subsystems_active"] == []
    assert health["initialized"] is False


# ── call_mcp_tool (#874) ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_mcp_tool_missing_registry():
    app = TRANC3Enhanced()
    app._subsystems = {}
    result = await app.call_mcp_tool("some_tool")
    assert result == {"error": "MCP registry not available"}


@pytest.mark.asyncio
async def test_call_mcp_tool_missing_tool():
    app = TRANC3Enhanced()
    mock_registry = MagicMock()
    mock_registry.get.return_value = None
    app._subsystems = {"mcp_registry": mock_registry}

    result = await app.call_mcp_tool("missing_tool")

    assert result == {"error": "Tool 'missing_tool' not found"}
    mock_registry.get.assert_called_once_with("missing_tool")


@pytest.mark.asyncio
async def test_call_mcp_tool_success():
    app = TRANC3Enhanced()

    mock_tool = MagicMock()
    mock_tool.handler = AsyncMock(return_value={"status": "success", "data": "test"})

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool
    app._subsystems = {"mcp_registry": mock_registry}

    params = {"key": "value"}
    result = await app.call_mcp_tool("working_tool", params)

    assert result == {"status": "success", "data": "test"}
    mock_registry.get.assert_called_once_with("working_tool")
    mock_tool.handler.assert_called_once_with(params)


@pytest.mark.asyncio
async def test_call_mcp_tool_default_params():
    app = TRANC3Enhanced()

    mock_tool = MagicMock()
    mock_tool.handler = AsyncMock(return_value={"status": "success"})

    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool
    app._subsystems = {"mcp_registry": mock_registry}

    result = await app.call_mcp_tool("working_tool")

    assert result == {"status": "success"}
    mock_registry.get.assert_called_once_with("working_tool")
    mock_tool.handler.assert_called_once_with({})


# ── execute_workflow (#904) ──────────────────────────────────────────────────


class _StubWorkflowState:
    def __init__(self, execution_id, status, node_outputs, error=None):
        self.execution_id = execution_id
        self.status = status
        self.node_outputs = node_outputs
        self.error = error


class _StubWorkflowExecutor:
    def __init__(self):
        self.last_workflow = None
        self.last_inputs = None

    async def execute(self, workflow, inputs):
        self.last_workflow = workflow
        self.last_inputs = inputs
        return _StubWorkflowState("exec-123", "completed", {"node1": "output1"})


_WORKFLOW_DEF = {
    "name": "test_workflow",
    "steps": [{"step_id": "step1", "name": "Step 1", "action": "test_action"}],
}


@pytest.mark.asyncio
async def test_execute_workflow_missing_executor():
    app = TRANC3Enhanced()
    result = await app.execute_workflow({"test": "definition"}, {"test": "input"})
    assert result == {"error": "Workflow executor not available"}


@pytest.mark.asyncio
async def test_execute_workflow_success():
    app = TRANC3Enhanced()
    executor = _StubWorkflowExecutor()
    app._subsystems["workflow_executor"] = executor

    result = await app.execute_workflow(_WORKFLOW_DEF, {"test": "input"})

    assert result == {
        "execution_id": "exec-123",
        "status": "completed",
        "outputs": {"node1": "output1"},
        "error": None,
    }
    assert executor.last_inputs == {"test": "input"}
    # The dict is parsed into a WorkflowDefinition before it reaches the executor.
    assert executor.last_workflow.name == "test_workflow"


@pytest.mark.asyncio
async def test_execute_workflow_defaults_inputs_to_empty_dict():
    app = TRANC3Enhanced()
    executor = _StubWorkflowExecutor()
    app._subsystems["workflow_executor"] = executor

    result = await app.execute_workflow(_WORKFLOW_DEF)

    assert result["status"] == "completed"
    assert executor.last_inputs == {}
