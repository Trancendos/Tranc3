# tests/test_relations_routes.py
# HTTP-level tests for src/relations/routes.py (the /relations API).

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.relations import registry as registry_module
from src.relations.registry import RelationsRegistry
from src.relations.routes import router as relations_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_registry = RelationsRegistry(db_path=tmp_path / "relations_routes_test.db")
    monkeypatch.setattr(registry_module, "_registry", test_registry)

    app = FastAPI()
    app.include_router(relations_router)
    with TestClient(app) as c:
        yield c
    test_registry.close()


def _override(user_id: str, role: str = "user"):
    def _dep():
        return {"sub": user_id, "role": role}

    return _dep


class TestReadRoutes:
    def test_feed_is_public(self, client):
        resp = client.get("/relations/feed")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_insights_is_public(self, client):
        resp = client.get("/relations/insights")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_pairwise_relationship_is_public(self, client):
        resp = client.get("/relations/Dorris Fontaine/Larry Lowhammer")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ai_a"] == "Dorris Fontaine"
        assert body["ai_b"] == "Larry Lowhammer"
        assert body["tier"] == "neutral"

    def test_ai_relationship_list_is_public(self, client):
        resp = client.get("/relations/Dorris Fontaine")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        # every *other* unique Lead AI — derive from PLATFORM_ENTITIES rather
        # than hardcoding, so a roster change doesn't silently break this.
        from src.entities.platform import PLATFORM_ENTITIES

        expected = len({e.lead_ai for e in PLATFORM_ENTITIES.values()}) - 1
        assert len(body) == expected

    def test_brochure_for_known_location(self, client):
        resp = client.get("/relations/locations/Royal Bank of Arcadia/brochure")
        assert resp.status_code == 200
        body = resp.json()
        assert body["location"] == "Royal Bank of Arcadia"
        assert body["current_resident"] == "Dorris Fontaine"

    def test_brochure_for_slash_location(self, client):
        resp = client.get("/relations/locations/ChronosSphere / ArcStream/brochure")
        assert resp.status_code == 200
        assert resp.json()["location"] == "ChronosSphere / ArcStream"

    def test_brochure_for_unknown_location_404s(self, client):
        resp = client.get("/relations/locations/Nonexistent Place/brochure")
        assert resp.status_code == 404


class TestRecordEventRoute:
    def test_requires_auth(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.post(
            "/relations/events",
            json={"actor_ai": "Dorris Fontaine", "event_type": "system", "summary": "x"},
        )
        assert resp.status_code in (401, 403)

    def test_non_admin_forbidden(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.post(
                "/relations/events",
                json={"actor_ai": "Dorris Fontaine", "event_type": "system", "summary": "x"},
            )
            assert resp.status_code == 403
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_can_record(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/relations/events",
                json={
                    "actor_ai": "Dorris Fontaine",
                    "event_type": "location_tag",
                    "location": "Royal Bank of Arcadia",
                    "sentiment": "positive",
                    "summary": "Checked in.",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["actor_ai"] == "Dorris Fontaine"
            assert body["location"] == "Royal Bank of Arcadia"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_invalid_event_type_rejected(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/relations/events",
                json={"actor_ai": "Dorris Fontaine", "event_type": "bogus", "summary": "x"},
            )
            assert resp.status_code == 422
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_invalid_sentiment_rejected(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/relations/events",
                json={
                    "actor_ai": "Dorris Fontaine",
                    "event_type": "system",
                    "sentiment": "furious",
                    "summary": "x",
                },
            )
            assert resp.status_code == 422
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_recorded_event_appears_in_feed(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            client.post(
                "/relations/events",
                json={
                    "actor_ai": "Dorris Fontaine",
                    "event_type": "ai_interaction",
                    "target_ai": "Larry Lowhammer",
                    "sentiment": "positive",
                    "summary": "Collaborated well.",
                },
            )
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

        feed = client.get("/relations/feed").json()
        assert len(feed) == 1
        assert feed[0]["summary"] == "Collaborated well."

        rel = client.get("/relations/Dorris Fontaine/Larry Lowhammer").json()
        assert rel["score"] > rel["baseline"]
