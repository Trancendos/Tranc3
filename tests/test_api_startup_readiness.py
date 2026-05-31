import asyncio
import importlib
import json
import os
import sys
from unittest.mock import MagicMock, patch


def _import_api_module():
    env = {
        "SECRET_KEY": "a" * 32,
        "JWT_SECRET": "b" * 32,
        "ENVIRONMENT": "development",
        "DATABASE_URL": "sqlite:///./test.db",
        "REDIS_URL": "redis://localhost:6379/0",
    }
    mock_cryptex = MagicMock()
    mock_cryptex.analyse_request.return_value = []
    mock_cryptex.is_blocked.return_value = False

    sys.modules.pop("api", None)

    with (
        patch.dict(os.environ, env, clear=False),
        patch("src.core.startup_validator.validate_startup") as validate_startup,
        patch("redis.from_url", return_value=MagicMock(ping=lambda: True)),
        patch("src.cryptex.threat_detector.get_cryptex", return_value=mock_cryptex),
    ):
        module = importlib.import_module("api")

    return module, validate_startup


def test_api_import_invokes_shared_startup_validator():
    module, validate_startup = _import_api_module()

    try:
        validate_startup.assert_called_once_with()
    finally:
        sys.modules.pop(module.__name__, None)


def test_ready_returns_503_until_bootstrap_is_complete():
    module, _ = _import_api_module()

    try:
        module._bootstrap_complete = False
        response = asyncio.run(module.ready())

        assert response.status_code == 503
        assert json.loads(response.body) == {
            "ready": False,
            "timestamp": json.loads(response.body)["timestamp"],
        }
    finally:
        sys.modules.pop(module.__name__, None)


def test_ready_returns_success_after_bootstrap_completes():
    module, _ = _import_api_module()

    try:
        module._bootstrap_complete = True
        response = asyncio.run(module.ready())

        assert response["ready"] is True
        assert "timestamp" in response
    finally:
        sys.modules.pop(module.__name__, None)
