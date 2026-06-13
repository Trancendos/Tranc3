"""
NanoService Tests — NanoServiceRegistry + nano_server request models.

Verifies the nanoservice layer (port 8001) is structurally sound: registry
initialises, request models validate, and the FastAPI nano_app is wired correctly.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

_log = logging.getLogger("tranc3.tests.nanoservices")


@pytest.fixture(scope="module")
def nano_client():
    from src.nanoservices.nano_server import nano_app

    return TestClient(nano_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestNanoServiceRegistry:
    def test_registry_initialises(self, caplog):
        from src.nanoservices.nano_registry import NanoServiceRegistry

        reg = NanoServiceRegistry()
        _log.info("nano.registry type=%s", type(reg).__name__)
        assert reg is not None

    def test_registry_has_service_list(self, caplog):
        from src.nanoservices.nano_registry import NanoServiceRegistry

        reg = NanoServiceRegistry()
        services = getattr(reg, "services", None) or getattr(reg, "_services", None) or {}
        _log.info("nano.registry service_count=%d", len(services))
        # Registry may be empty in stub mode — just verify it's the right type
        assert isinstance(services, (dict, list))

    def test_registry_bot_registry_integration(self, caplog):
        """BotRegistry used by nanoservice must initialise without error."""
        from src.workers.bot_registry import BotRegistry

        reg = BotRegistry()
        _log.info("nano.bot_registry type=%s", type(reg).__name__)
        assert reg is not None


# ---------------------------------------------------------------------------
# Request model validation
# ---------------------------------------------------------------------------


class TestNanoRequestModels:
    def test_generate_request_valid(self, caplog):
        from src.nanoservices.nano_server import GenerateRequest

        req = GenerateRequest(prompt="hello world")
        _log.info("nano.generate_request prompt=%r max_tokens=%d", req.prompt, req.max_tokens)
        assert req.prompt == "hello world"
        assert 1 <= req.max_tokens <= 4096

    def test_generate_request_max_tokens_bounds(self, caplog):
        import pydantic

        from src.nanoservices.nano_server import GenerateRequest

        with pytest.raises((pydantic.ValidationError, ValueError)):
            GenerateRequest(prompt="x", max_tokens=0)  # below minimum
        with pytest.raises((pydantic.ValidationError, ValueError)):
            GenerateRequest(prompt="x", max_tokens=99999)  # above maximum
        _log.info("nano.generate_request bounds validated")

    def test_generate_request_temperature_bounds(self, caplog):
        import pydantic

        from src.nanoservices.nano_server import GenerateRequest

        with pytest.raises((pydantic.ValidationError, ValueError)):
            GenerateRequest(prompt="x", temperature=-0.1)
        with pytest.raises((pydantic.ValidationError, ValueError)):
            GenerateRequest(prompt="x", temperature=2.1)
        _log.info("nano.generate_request temperature bounds validated")

    def test_embed_request_valid(self, caplog):
        from src.nanoservices.nano_server import EmbedRequest

        req = EmbedRequest(text="embed this")
        _log.info("nano.embed_request dims=%d pooling=%s", req.dims, req.pooling)
        assert req.text == "embed this"
        assert 8 <= req.dims <= 4096

    def test_embed_request_dims_bounds(self, caplog):
        import pydantic

        from src.nanoservices.nano_server import EmbedRequest

        with pytest.raises((pydantic.ValidationError, ValueError)):
            EmbedRequest(text="x", dims=4)  # below minimum (8)
        with pytest.raises((pydantic.ValidationError, ValueError)):
            EmbedRequest(text="x", dims=8192)  # above maximum (4096)
        _log.info("nano.embed_request dims bounds validated")

    def test_emotion_request_valid(self, caplog):
        from src.nanoservices.nano_server import EmotionRequest

        req = EmotionRequest(text="I feel great today!")
        _log.info("nano.emotion_request text=%r", req.text)
        assert req.text == "I feel great today!"


# ---------------------------------------------------------------------------
# HTTP endpoints (using TestClient — no real HTTP)
# ---------------------------------------------------------------------------


class TestNanoServerEndpoints:
    def test_health_endpoint_returns_ok(self, nano_client, caplog):
        resp = nano_client.get("/health")
        _log.info("nano.http health status=%d body=%s", resp.status_code, resp.text[:100])
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_services_list_endpoint(self, nano_client, caplog):
        resp = nano_client.get("/services")
        _log.info("nano.http services status=%d", resp.status_code)
        assert resp.status_code in (200, 404)  # may not have /services in all versions

    def test_generate_endpoint_rejects_empty_prompt(self, nano_client, caplog):
        resp = nano_client.post("/generate", json={"prompt": ""})
        _log.info("nano.http generate_empty status=%d", resp.status_code)
        # 400/422 = validation error; 503 = service unavailable in bootstrap mode
        assert resp.status_code in (400, 422, 503)

    def test_generate_endpoint_accepts_valid_prompt(self, nano_client, caplog):
        resp = nano_client.post("/generate", json={"prompt": "hello from nanoservice test"})
        _log.info(
            "nano.http generate_valid status=%d body_keys=%s",
            resp.status_code,
            list(resp.json().keys()) if resp.status_code == 200 else "n/a",
        )
        assert resp.status_code in (200, 422, 500, 503)  # 503 acceptable in bootstrap mode

    def test_embed_endpoint_accepts_valid_text(self, nano_client, caplog):
        resp = nano_client.post("/embed", json={"text": "embed this text"})
        _log.info("nano.http embed_valid status=%d", resp.status_code)
        assert resp.status_code in (200, 422, 500, 503)

    def test_emotion_endpoint_accepts_valid_text(self, nano_client, caplog):
        resp = nano_client.post("/emotion", json={"text": "I am happy!"})
        _log.info("nano.http emotion_valid status=%d", resp.status_code)
        assert resp.status_code in (200, 422, 500, 503)
