"""Security regressions for Marketplace catalogue mutation.

Run: pytest -q tests/test_apimarket_security.py
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.auth.facade import create_token
from src.apimarket.routes import router


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-for-apimarket-regression")
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def headers(role):
    return {"Authorization": f"Bearer {create_token('test-id', 'test-user', role=role)}"}


def test_anonymous_cannot_register_connector(client):
    response = client.post("/apimarket/connectors", json={
        "name": "External", "slug": "external-test", "base_url": "https://example.com"
    })
    assert response.status_code == 401


def test_normal_user_cannot_register_connector(client):
    response = client.post("/apimarket/connectors", headers=headers("user"), json={
        "name": "External", "slug": "external-test", "base_url": "https://example.com"
    })
    assert response.status_code == 403


def test_anonymous_cannot_add_endpoint(client):
    response = client.post("/apimarket/connectors/not-real/endpoints", json={"path": "/chat"})
    assert response.status_code == 401


def test_admin_cannot_register_private_or_local_url(client):
    for url in ("http://127.0.0.1:8000", "http://169.254.169.254/latest",
                "https://localhost/", "file:///etc/passwd", "https://user:pass@example.com/"):
        response = client.post("/apimarket/connectors", headers=headers("admin"), json={
            "name": "Bad", "slug": "bad-test", "base_url": url
        })
        assert response.status_code == 422, (url, response.text)


def test_admin_registers_approved_https_provider(client):
    response = client.post("/apimarket/connectors", headers=headers("admin"), json={
        "name": "External", "slug": "test-provider-20261024", "base_url": "https://api.example.com",
        "auth_type": "api_key", "tags": ["ai", "model-provider"],
    })
    assert response.status_code == 200, response.text
    assert response.json()["slug"] == "test-provider-20261024"
