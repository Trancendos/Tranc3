"""
test_router.py — Route-level tests for gateway-service.
All upstream HTTP calls are mocked; no real workers required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "gateway-service"


def test_health_version(client):
    resp = client.get("/health")
    assert resp.json()["version"] == "0.8.0"


# ---------------------------------------------------------------------------
# /stats
# ---------------------------------------------------------------------------


def test_stats_returns_upstream_count(client):
    with patch("router.fetch_all_stats", new_callable=AsyncMock, return_value={}):
        resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "upstream_workers" in body
    assert "circuit_breakers" in body


# ---------------------------------------------------------------------------
# /api/overview
# ---------------------------------------------------------------------------


MOCK_ALL_STATS = {
    "vault": {"status": "ok", "active_secrets": 5, "audit_entries": 10, "open_leaks": 0},
    "topology": {"status": "ok", "current_mode": "FULL", "total_nodes": 3, "healthy_nodes": 3},
    "ledger": {"status": "ok", "chain_valid": True, "total_entries": 42},
    "model_router": {"status": "ok", "total_models": 4},
    "workflow": {"status": "ok", "total_workflows": 7},
    "benchmark": {"status": "ok", "total_suites": 2},
    "langchain": {"status": "ok", "prompt_templates": 6},
    "deepagents": {"status": "ok", "agents": {"active": 1, "total": 3}},
}


def test_api_overview_operational(client):
    with patch("router.get_cached_or_fetch", new_callable=AsyncMock, return_value=MOCK_ALL_STATS):
        resp = client.get("/api/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"]["status"] == "operational"
    assert body["services"]["total"] == 8
    assert body["services"]["healthy"] == 8


def test_api_overview_degraded(client):
    degraded = {k: {"status": "unreachable"} for k in MOCK_ALL_STATS}
    degraded["vault"] = {"status": "ok"}
    degraded["topology"] = {"status": "ok"}
    degraded["ledger"] = {"status": "ok"}
    with patch("router.get_cached_or_fetch", new_callable=AsyncMock, return_value=degraded):
        resp = client.get("/api/overview")
    assert resp.json()["platform"]["status"] == "degraded"


def test_api_overview_critical(client):
    critical = {k: {"status": "unreachable"} for k in MOCK_ALL_STATS}
    with patch("router.get_cached_or_fetch", new_callable=AsyncMock, return_value=critical):
        resp = client.get("/api/overview")
    assert resp.json()["platform"]["status"] == "critical"


# ---------------------------------------------------------------------------
# /api/agents
# ---------------------------------------------------------------------------


def test_api_agents(client):
    with (
        patch("router.fetch_worker", new_callable=AsyncMock, return_value={"total": 2}),
        patch("router.fetch_worker_list", new_callable=AsyncMock, return_value=[{"id": "a1"}]),
    ):
        resp = client.get("/api/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert "agents" in body
    assert "total_agents" in body


# ---------------------------------------------------------------------------
# /api/models
# ---------------------------------------------------------------------------


def test_api_models(client):
    with (
        patch("router.fetch_worker", new_callable=AsyncMock, return_value={"total_models": 3}),
        patch("router.fetch_worker_list", new_callable=AsyncMock, return_value=[{"name": "gpt-4"}]),
    ):
        resp = client.get("/api/models")
    assert resp.status_code == 200
    assert resp.json()["total_models"] == 1


# ---------------------------------------------------------------------------
# /api/workflows
# ---------------------------------------------------------------------------


def test_api_workflows(client):
    with (
        patch("router.fetch_worker", new_callable=AsyncMock, return_value={}),
        patch("router.fetch_worker_list", new_callable=AsyncMock, return_value=[]),
    ):
        resp = client.get("/api/workflows")
    assert resp.status_code == 200
    assert resp.json()["total_workflows"] == 0


# ---------------------------------------------------------------------------
# /api/security
# ---------------------------------------------------------------------------


def test_api_security(client):
    with (
        patch("router.fetch_worker", new_callable=AsyncMock, return_value={}),
        patch("router.fetch_worker_list", new_callable=AsyncMock, return_value=[]),
    ):
        resp = client.get("/api/security")
    assert resp.status_code == 200
    assert "vault" in resp.json()
    assert "ledger" in resp.json()


# ---------------------------------------------------------------------------
# /api/audit
# ---------------------------------------------------------------------------


def test_api_audit(client):
    with patch("router.fetch_worker_list", new_callable=AsyncMock, return_value=[]):
        resp = client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert "ledger" in body
    assert "vault_audit" in body


# ---------------------------------------------------------------------------
# /events/history
# ---------------------------------------------------------------------------


def test_event_history(client):
    resp = client.get("/events/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# /api/access/audit
# ---------------------------------------------------------------------------


def test_access_audit(client):
    resp = client.get("/api/access/audit")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# /api/access/check
# ---------------------------------------------------------------------------


def test_access_check_anonymous(client):
    resp = client.get("/api/access/check?endpoint=/api/overview&method=GET")
    assert resp.status_code == 200
    body = resp.json()
    assert "overall" in body


# ---------------------------------------------------------------------------
# /api/sentinel/status
# ---------------------------------------------------------------------------


def test_sentinel_status(client):
    resp = client.get("/api/sentinel/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "running" in body
    assert "backend" in body


# ---------------------------------------------------------------------------
# POST /api/workflows — upstream error handling
# ---------------------------------------------------------------------------


def test_create_workflow_upstream_error(client):
    import httpx as _httpx
    with patch("router.httpx.AsyncClient") as mock_client_cls:
        instance = mock_client_cls.return_value.__aenter__.return_value
        instance.post = AsyncMock(side_effect=_httpx.ConnectError("down"))
        resp = client.post(
            "/api/workflows",
            json={"name": "my-wf", "steps": [{"id": "step1", "type": "noop"}]},
        )
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/workflows/{id}/run — invalid id
# ---------------------------------------------------------------------------


def test_run_workflow_invalid_id(client):
    resp = client.post("/api/workflows/bad id!/run")
    assert resp.status_code == 400
