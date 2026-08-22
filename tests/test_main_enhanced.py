import pytest
import asyncio
from unittest.mock import patch, MagicMock
from src.main_enhanced import TRANC3Enhanced


@pytest.fixture
def enhanced_app():
    return TRANC3Enhanced()


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
