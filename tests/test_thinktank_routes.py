"""Tests for Think Tank's /thinktank/deepmind/plan and /thinktank/status routes (src/quantum/routes.py)."""

import builtins
from unittest.mock import AsyncMock, patch

import pytest

from src.deepmind import planning
from src.quantum.routes import deepmind_plan, thinktank_status


@pytest.mark.asyncio
async def test_deepmind_plan_calls_strategic_planner_and_awaits_result():
    fake_plan = {"plan": ["step1", "step2"], "confidence": 0.8}
    with patch.object(planning, "StrategicPlanner") as MockPlanner:
        MockPlanner.return_value.plan_action = AsyncMock(return_value=fake_plan)

        result = await deepmind_plan({"problem": "reduce platform costs", "depth": 4})

    assert result["problem"] == "reduce platform costs"
    assert result["depth"] == 4
    assert result["plan"] == fake_plan
    MockPlanner.return_value.plan_action.assert_awaited_once_with(
        "reduce platform costs", state={}, constraints=[]
    )


@pytest.mark.asyncio
async def test_deepmind_plan_returns_error_on_exception():
    with patch.object(planning, "StrategicPlanner") as MockPlanner:
        MockPlanner.return_value.plan_action = AsyncMock(side_effect=RuntimeError("boom"))

        result = await deepmind_plan({"problem": "test"})

    assert result["plan"] is None
    assert "error" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deepmind_plan_end_to_end_real_planner():
    """No mocking — exercises the real StrategicPlanner/PlanningConfig wiring."""
    result = await deepmind_plan({"problem": "reduce platform costs", "depth": 2})
    assert result["problem"] == "reduce platform costs"
    assert result["depth"] == 2
    assert result["plan"] is not None
    assert "error" not in result


@pytest.mark.asyncio
async def test_thinktank_status_shape():
    result = await thinktank_status()
    assert result["service"] == "think-tank"
    assert set(result["modules"]) == {"quantum", "deepmind"}
    assert result["modules"]["quantum"]["quantum_core"] in ("available", "degraded")
    assert result["modules"]["deepmind"]["mcts"] in ("available", "degraded")


@pytest.mark.asyncio
async def test_thinktank_status_reports_degraded_on_import_failure(monkeypatch):
    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name in ("qiskit_aer", "src.deepmind.planning"):
            raise ImportError(f"blocked for test: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    result = await thinktank_status()

    assert result["modules"]["quantum"]["quantum_core"] == "degraded"
    assert isinstance(result["modules"]["quantum"]["note"], str)
    assert result["modules"]["quantum"]["note"]
    assert result["modules"]["deepmind"]["mcts"] == "degraded"
    assert isinstance(result["modules"]["deepmind"]["note"], str)
    assert result["modules"]["deepmind"]["note"]
