import pytest
from unittest.mock import patch, MagicMock

from src.dependencies import container, configure_services

def test_configure_services_registers_factories():
    # Reset container to ensure clean state
    container.reset()
    assert container._initialized is False

    # Mock config
    mock_config = MagicMock()
    mock_config.REDIS_URL = "redis://localhost:6379"
    mock_config.DATABASE_URL = "sqlite:///:memory:"

    # Run configure_services without args if necessary or patch it
    with patch("src.core.config.settings", mock_config):
        configure_services()

    # Assert services are registered
    expected_services = [
        "redis", "db", "feature_flags", "vector_store",
        "personality", "consciousness", "evolution", "quantum"
    ]

    for service in expected_services:
        assert container.has(service)

    assert container._initialized is True

def test_configure_services_error_handling():
    # Reset container
    container.reset()

    mock_config = MagicMock()
    mock_config.REDIS_URL = "redis://localhost:6379"
    mock_config.DATABASE_URL = "sqlite:///:memory:"

    with patch("src.core.config.settings", mock_config):
        configure_services()

    # We will simulate ImportError by patching sys.modules
    with patch.dict("sys.modules", {
        "src.personality.matrix": None,
        "src.bio_neural.consciousness_engine": None,
        "src.evolution.self_improving_core": None,
        "src.quantum.quantum_core": None,
    }):
        # Calling get() or the factory directly should return None for optional services
        assert container.get("personality") is None
        assert container.get("consciousness") is None
        assert container.get("evolution") is None
        assert container.get("quantum") is None
