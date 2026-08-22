from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main_enhanced import TRANC3Enhanced


@pytest.fixture
def enhanced_orchestrator():
    config = {
        "mcp": {"enabled": False},
        "workflow": {"max_concurrent": 1},
        "deepmind": {"mcts_simulations": 10},
        "healing": {"check_interval_sec": 60, "auto_repair": False},
        "skills": {"semantic_search": False},
        "tensorflow": {"enabled": False, "prefer_torch": True},
    }
    return TRANC3Enhanced(config=config)

@pytest.mark.asyncio
async def test_think_with_tranc3_engine(enhanced_orchestrator):
    # Setup mocks
    mock_engine = AsyncMock()
    mock_engine.generate.return_value = {
        "response": "Hello world",
        "model": "tranc3-local",
        "tokens": 2,
        "trained": True,
    }
    enhanced_orchestrator._subsystems["tranc3_engine"] = mock_engine

    mock_planner = AsyncMock()
    mock_planner.plan_action.return_value = {"steps": ["step 1"]}
    enhanced_orchestrator._subsystems["planner"] = mock_planner

    mock_skill = MagicMock()
    mock_skill.skill.name = "test-skill"
    mock_registry = AsyncMock()
    mock_registry.search.return_value = [mock_skill]

    mock_bundle = MagicMock()
    mock_bundle.name = "test-bundle"
    mock_registry.detect_and_load_bundle.return_value = mock_bundle

    enhanced_orchestrator._subsystems["skill_registry"] = mock_registry

    mock_consciousness = MagicMock()
    mock_consciousness.simulate_consciousness_stream.return_value = {"average_phi": 0.5}
    enhanced_orchestrator._subsystems["consciousness"] = mock_consciousness

    mock_evolution = MagicMock()
    mock_evolution.generation = 1
    enhanced_orchestrator._subsystems["evolution"] = mock_evolution

    # Execute
    result = await enhanced_orchestrator.think("Test prompt")

    # Verify tranc3_engine
    assert result["prompt"] == "Test prompt"
    assert result["response"] == "Hello world"
    assert result["model"] == "tranc3-local"
    assert result["tokens"] == 2
    mock_engine.generate.assert_called_once_with(
        prompt="Test prompt",
        personality="tranc3-base",
        system_prompt=None,
        max_new_tokens=256,
        temperature=0.8,
        context={},
    )

    # Verify planner
    assert result["plan"] == {"steps": ["step 1"]}
    mock_planner.plan_action.assert_called_once_with(
        goal="Test prompt",
        state={},
        constraints=["zero-cost", "gdpr-compliant", "self-healing"],
    )

    # Verify skill registry
    assert result["matched_skills"] == ["test-skill"]
    assert result["triggered_bundle"] == "test-bundle"
    mock_registry.search.assert_called_once_with("Test prompt", top_k=5)
    mock_registry.detect_and_load_bundle.assert_called_once_with("Test prompt")

    # Verify consciousness
    assert result["consciousness_phi"] == 0.5
    mock_consciousness.simulate_consciousness_stream.assert_called_once()

    # Verify evolution
    assert result["evolution_gen"] == 1
    mock_evolution.evolve.assert_called_once_with(num_generations=1)

@pytest.mark.asyncio
async def test_think_without_tranc3_engine(enhanced_orchestrator):
    # Execute
    result = await enhanced_orchestrator.think("Test prompt")

    # Verify
    assert result["response"] == "TRANC3 language engine not initialised. Run `python train.py` then restart."
    assert result["model"] == "none"

@pytest.mark.asyncio
async def test_think_untrained_model(enhanced_orchestrator):
    mock_engine = AsyncMock()
    mock_engine.generate.return_value = {
        "response": "Fallback",
        "model": "tranc3-local",
        "tokens": 1,
        "trained": False,
        "action_required": "python train.py"
    }
    enhanced_orchestrator._subsystems["tranc3_engine"] = mock_engine

    result = await enhanced_orchestrator.think("Test prompt")

    assert result["warning"] == "Fallback"
    assert result["action_required"] == "python train.py"

@pytest.mark.asyncio
async def test_think_planner_error(enhanced_orchestrator):
    mock_planner = AsyncMock()
    mock_planner.plan_action.side_effect = Exception("Planner failed")
    enhanced_orchestrator._subsystems["planner"] = mock_planner

    # Should not raise exception
    result = await enhanced_orchestrator.think("Test prompt")
    assert "plan" not in result

@pytest.mark.asyncio
async def test_think_skill_error(enhanced_orchestrator):
    mock_registry = AsyncMock()
    mock_registry.search.side_effect = Exception("Skill failed")
    enhanced_orchestrator._subsystems["skill_registry"] = mock_registry

    # Should not raise exception
    result = await enhanced_orchestrator.think("Test prompt")
    assert "matched_skills" not in result
    assert "triggered_bundle" not in result

@pytest.mark.asyncio
async def test_think_consciousness_error(enhanced_orchestrator):
    mock_consciousness = MagicMock()
    mock_consciousness.simulate_consciousness_stream.side_effect = Exception("Consciousness failed")
    enhanced_orchestrator._subsystems["consciousness"] = mock_consciousness

    # Should not raise exception
    result = await enhanced_orchestrator.think("Test prompt")
    assert "consciousness_phi" not in result

@pytest.mark.asyncio
async def test_think_evolution_error(enhanced_orchestrator):
    mock_evolution = MagicMock()
    mock_evolution.evolve.side_effect = Exception("Evolution failed")
    enhanced_orchestrator._subsystems["evolution"] = mock_evolution

    # Should not raise exception
    result = await enhanced_orchestrator.think("Test prompt")
    assert "evolution_gen" not in result

@patch("src.main_enhanced.torch", None)
def test_encode_without_torch(enhanced_orchestrator):
    encoded = enhanced_orchestrator._encode("Test string")
    assert isinstance(encoded, list)
    assert len(encoded) == len("Test string")

@patch("src.main_enhanced.torch")
def test_encode_with_torch(mock_torch, enhanced_orchestrator):
    # Mocking torch so we don't actually need it
    mock_tensor = MagicMock()
    mock_tensor.__len__.return_value = 768

    # Mock behavior of padding, unsqueeze etc
    mock_tensor.unsqueeze.return_value = "mock_tensor"
    mock_tensor.__getitem__.return_value = mock_tensor

    mock_torch.tensor.return_value = mock_tensor
    mock_torch.float32 = "float32"

    encoded = enhanced_orchestrator._encode("Test string")
    assert encoded == "mock_tensor"
