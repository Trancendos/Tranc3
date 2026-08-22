import pytest
from unittest.mock import patch, MagicMock

import sys
sys.modules['torch'] = MagicMock()
sys.modules['torch.nn'] = MagicMock()
sys.modules['torch.nn.functional'] = MagicMock()

from src.main_enhanced import TRANC3Enhanced

@pytest.mark.asyncio
async def test_initialize_loads_all_subsystems():
    with patch('src.main_enhanced.logger') as mock_logger:
        enhanced = TRANC3Enhanced()

        # Mocking subsystems to avoid complex instantiations that might fail
        with patch.dict('sys.modules', {
            'src.mcp.tools': MagicMock(registry=MagicMock(_tools=[1, 2, 3])),
            'src.workflow.executor': MagicMock(event_bus="mock_event_bus", executor="mock_workflow_executor"),
            'src.deepmind.planning': MagicMock(planner="mock_planner"),
            'src.healing.health_monitor': MagicMock(health_monitor="mock_health_monitor"),
            'src.healing.nanocode_bots': MagicMock(dispatcher="mock_dispatcher"),
            'src.healing.self_repair': MagicMock(config_tuner="mock_config_tuner", repair_engine="mock_repair_engine"),
            'src.skills.enhanced_registry': MagicMock(registry=MagicMock(skills=[1, 2])),
            'src.skills.code_generator': MagicMock(code_generator="mock_code_generator"),
            'src.core.tranc3_inference': MagicMock(get_engine=MagicMock(return_value=MagicMock(status=MagicMock(return_value={"loaded": True, "device": "cpu"})))),
            'src.tensorflow_core.hybrid_engine': MagicMock(hybrid_engine="mock_hybrid_engine"),
            'src.bio_neural.consciousness_engine': MagicMock(ConsciousnessModel=MagicMock(return_value="mock_consciousness")),
            'src.evolution.self_improving_core': MagicMock(SelfEvolvingArchitecture=MagicMock(return_value="mock_evolution")),
            'src.holographic.memory_crystal': MagicMock(HolographicMemoryCrystal=MagicMock(return_value="mock_memory")),
            'src.quantum.quantum_core': MagicMock(QuantumNeuralCore=MagicMock(return_value="mock_quantum")),
        }):
            # Patch os.path.isdir to pass the skills directory check
            with patch('os.path.isdir', return_value=True):
                await enhanced.initialize()

            assert enhanced._initialized is True
            assert "mcp_registry" in enhanced._subsystems
            assert "workflow_executor" in enhanced._subsystems
            assert "event_bus" in enhanced._subsystems
            assert "planner" in enhanced._subsystems
            assert "health_monitor" in enhanced._subsystems
            assert "repair_engine" in enhanced._subsystems
            assert "config_tuner" in enhanced._subsystems
            assert "bot_dispatcher" in enhanced._subsystems
            assert "skill_registry" in enhanced._subsystems
            assert "code_generator" in enhanced._subsystems
            assert "tranc3_engine" in enhanced._subsystems
            assert "hybrid_engine" in enhanced._subsystems
            assert "quantum" in enhanced._subsystems
            assert "consciousness" in enhanced._subsystems
            assert "evolution" in enhanced._subsystems
            assert "memory" in enhanced._subsystems

@pytest.mark.asyncio
async def test_initialize_graceful_degradation():
    with patch('src.main_enhanced.logger') as mock_logger:
        enhanced = TRANC3Enhanced()

        # Force import errors on all subsystems
        with patch.dict('sys.modules', {
            'src.mcp.tools': None,
            'src.workflow.executor': None,
            'src.deepmind.planning': None,
            'src.healing.health_monitor': None,
            'src.healing.nanocode_bots': None,
            'src.healing.self_repair': None,
            'src.skills.enhanced_registry': None,
            'src.skills.code_generator': None,
            'src.core.tranc3_inference': None,
            'src.tensorflow_core.hybrid_engine': None,
            'src.bio_neural.consciousness_engine': None,
            'src.evolution.self_improving_core': None,
            'src.holographic.memory_crystal': None,
            'src.quantum.quantum_core': None,
        }):
            await enhanced.initialize()

            # It should still mark as initialized even if all subsystems failed to load
            assert enhanced._initialized is True

            # We should expect empty or very few subsystems
            assert len(enhanced._subsystems) == 0

            # Verify that warnings were logged for each subsystem
            warning_calls = [call.args[0] for call in mock_logger.warning.call_args_list]
            assert any("MCP registry init failed" in msg for msg in warning_calls)
            assert any("Workflow executor init failed" in msg for msg in warning_calls)
            assert any("DeepMind planner init failed" in msg for msg in warning_calls)
            assert any("Healing system init failed" in msg for msg in warning_calls)
            assert any("Skill registry init failed" in msg for msg in warning_calls)
            assert any("Code generator init failed" in msg for msg in warning_calls)
            assert any("TRANC3 engine init failed" in msg for msg in warning_calls)
            assert any("TF Hybrid engine init failed" in msg for msg in warning_calls)
            assert any("2060 core init failed" in msg for msg in warning_calls)

@pytest.mark.asyncio
async def test_initialize_tranc3_engine_not_loaded():
    with patch('src.main_enhanced.logger') as mock_logger:
        enhanced = TRANC3Enhanced()

        with patch.dict('sys.modules', {
            'src.mcp.tools': MagicMock(registry=MagicMock(_tools=[1, 2, 3])),
            'src.workflow.executor': MagicMock(event_bus="mock_event_bus", executor="mock_workflow_executor"),
            'src.deepmind.planning': MagicMock(planner="mock_planner"),
            'src.healing.health_monitor': MagicMock(health_monitor="mock_health_monitor"),
            'src.healing.nanocode_bots': MagicMock(dispatcher="mock_dispatcher"),
            'src.healing.self_repair': MagicMock(config_tuner="mock_config_tuner", repair_engine="mock_repair_engine"),
            'src.skills.enhanced_registry': MagicMock(registry=MagicMock(skills=[1, 2])),
            'src.skills.code_generator': MagicMock(code_generator="mock_code_generator"),
            # Simulating model not loaded
            'src.core.tranc3_inference': MagicMock(get_engine=MagicMock(return_value=MagicMock(status=MagicMock(return_value={"loaded": False})))),
            'src.tensorflow_core.hybrid_engine': MagicMock(hybrid_engine="mock_hybrid_engine"),
            'src.bio_neural.consciousness_engine': MagicMock(ConsciousnessModel=MagicMock(return_value="mock_consciousness")),
            'src.evolution.self_improving_core': MagicMock(SelfEvolvingArchitecture=MagicMock(return_value="mock_evolution")),
            'src.holographic.memory_crystal': MagicMock(HolographicMemoryCrystal=MagicMock(return_value="mock_memory")),
            'src.quantum.quantum_core': MagicMock(QuantumNeuralCore=MagicMock(return_value="mock_quantum")),
        }):
            with patch('os.path.isdir', return_value=True):
                await enhanced.initialize()

            assert enhanced._initialized is True
            assert "tranc3_engine" in enhanced._subsystems

            warning_calls = [call.args[0] for call in mock_logger.warning.call_args_list]
            assert any("TRANC3 model not trained yet" in msg for msg in warning_calls)
