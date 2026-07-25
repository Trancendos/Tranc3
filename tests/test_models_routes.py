# tests/test_models_routes.py
# HTTP-level tests for src/models/routes.py (the /models API).

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.models import benchmark as benchmark_module
from src.models import governance as governance_module
from src.models.benchmark import BenchmarkRegistry
from src.models.governance import ModelGovernanceRegistry
from src.models.routes import router as models_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_benchmarks = BenchmarkRegistry(db_path=tmp_path / "bench.db")
    test_governance = ModelGovernanceRegistry(
        db_path=tmp_path / "gov.db", benchmark_registry=test_benchmarks
    )
    monkeypatch.setattr(benchmark_module, "_registry", test_benchmarks)
    monkeypatch.setattr(governance_module, "_registry", test_governance)

    app = FastAPI()
    app.include_router(models_router)
    with TestClient(app) as c:
        yield c
    test_benchmarks.close()
    test_governance.close()


def _override(user_id: str, role: str = "user"):
    def _dep():
        return {"sub": user_id, "role": role}

    return _dep


def _as_admin(client):
    client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")


def _as_user(client):
    client.app.dependency_overrides[get_current_user] = _override("u1", role="user")


def _clear_auth(client):
    client.app.dependency_overrides.pop(get_current_user, None)


class TestMatrixReadRoutes:
    def test_get_matrix_is_public(self, client):
        resp = client.get("/models/matrix")
        assert resp.status_code == 200
        assert resp.json()["total_ais"] == 50

    def test_get_ai_model_specialized(self, client):
        resp = client.get("/models/matrix/George Porter")
        assert resp.status_code == 200
        body = resp.json()
        assert body["effective_model"] == "Tranc3-Crypto"
        assert body["specialized"] is True

    def test_get_ai_model_unspecialized(self, client):
        resp = client.get("/models/matrix/Zimik")
        assert resp.status_code == 200
        body = resp.json()
        assert body["effective_model"] == "Tranc3"
        assert body["specialized"] is False

    def test_get_variants(self, client):
        resp = client.get("/models/variants")
        assert resp.status_code == 200
        names = {v["specialized_name"] for v in resp.json()}
        assert "T2ance-CODE" in names
        assert "Tranc3-Crypto" in names


class TestBenchmarkRoutes:
    def test_record_requires_admin(self, client):
        _as_user(client)
        try:
            resp = client.post(
                "/models/benchmark",
                json={"model_name": "T2ance-CODE", "skill_domain": "Coder", "score": 80.0},
            )
            assert resp.status_code == 403
        finally:
            _clear_auth(client)

    def test_record_requires_auth_at_all(self, client):
        resp = client.post(
            "/models/benchmark",
            json={"model_name": "T2ance-CODE", "skill_domain": "Coder", "score": 80.0},
        )
        assert resp.status_code in (401, 403)

    def test_admin_can_record_and_read_history(self, client):
        _as_admin(client)
        try:
            resp = client.post(
                "/models/benchmark",
                json={
                    "model_name": "T2ance-CODE",
                    "skill_domain": "Coder",
                    "score": 80.0,
                    "notes": "scan #1",
                },
            )
            assert resp.status_code == 200
            assert resp.json()["score"] == 80.0
        finally:
            _clear_auth(client)

        history_resp = client.get("/models/benchmark/T2ance-CODE")
        assert history_resp.status_code == 200
        assert len(history_resp.json()) == 1


class TestGovernanceRoutes:
    def _record_two_scans(self, client, model="T2ance-CODE", skill="Coder"):
        _as_admin(client)
        try:
            for score in (60.0, 90.0):
                resp = client.post(
                    "/models/benchmark",
                    json={"model_name": model, "skill_domain": skill, "score": score},
                )
                assert resp.status_code == 200
        finally:
            _clear_auth(client)

    def test_submit_proposal_requires_admin(self, client):
        self._record_two_scans(client)
        _as_user(client)
        try:
            resp = client.post(
                "/models/proposals", json={"model_name": "T2ance-CODE", "skill_domain": "Coder"}
            )
            assert resp.status_code == 403
        finally:
            _clear_auth(client)

    def test_submit_proposal_without_history_is_422(self, client):
        _as_admin(client)
        try:
            resp = client.post(
                "/models/proposals",
                json={"model_name": "Nonexistent", "skill_domain": "Nothing"},
            )
            assert resp.status_code == 422
        finally:
            _clear_auth(client)

    def test_full_pipeline_through_http(self, client):
        self._record_two_scans(client)
        _as_admin(client)
        try:
            submit_resp = client.post(
                "/models/proposals", json={"model_name": "T2ance-CODE", "skill_domain": "Coder"}
            )
            assert submit_resp.status_code == 200
            proposal_id = submit_resp.json()["id"]
            assert submit_resp.json()["stage"] == "prime_review"

            prime_resp = client.post(
                f"/models/proposals/{proposal_id}/prime-review",
                json={"reviewer": "Dorris Fontaine", "notes": "solid"},
            )
            assert prime_resp.status_code == 200
            assert prime_resp.json()["stage"] == "cornelius_review"

            cornelius_resp = client.post(
                f"/models/proposals/{proposal_id}/cornelius-review",
                json={"notes": "real skill gain"},
            )
            assert cornelius_resp.status_code == 200
            assert cornelius_resp.json()["stage"] == "human_review"

            human_resp = client.post(
                f"/models/proposals/{proposal_id}/human-decision",
                json={"approved": True, "notes": "approved"},
            )
            assert human_resp.status_code == 200
            assert human_resp.json()["stage"] == "approved"
        finally:
            _clear_auth(client)

        # Read routes stay public and reflect the final state.
        get_resp = client.get(f"/models/proposals/{proposal_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["stage"] == "approved"

        list_resp = client.get("/models/proposals", params={"stage": "approved"})
        assert list_resp.status_code == 200
        assert any(p["id"] == proposal_id for p in list_resp.json())

    def test_wrong_stage_transition_is_409(self, client):
        self._record_two_scans(client)
        _as_admin(client)
        try:
            submit_resp = client.post(
                "/models/proposals", json={"model_name": "T2ance-CODE", "skill_domain": "Coder"}
            )
            proposal_id = submit_resp.json()["id"]
            # Skip straight to cornelius-review without a prime-review first.
            resp = client.post(f"/models/proposals/{proposal_id}/cornelius-review", json={})
            assert resp.status_code == 409
        finally:
            _clear_auth(client)

    def test_unknown_proposal_is_404(self, client):
        _as_admin(client)
        try:
            resp = client.post(
                "/models/proposals/999999/prime-review",
                json={"reviewer": "Dorris Fontaine"},
            )
            assert resp.status_code == 404
        finally:
            _clear_auth(client)

    def test_invalid_stage_filter_is_422(self, client):
        resp = client.get("/models/proposals", params={"stage": "not-a-real-stage"})
        assert resp.status_code == 422
