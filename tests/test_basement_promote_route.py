"""HTTP-level tests for POST /basement/promote.

This route is the only entry point to `src/basement/promotion.py`, which
implements the Basement -> Library leg of the learning pipeline and, until it
was wired, was called by nothing at all. Adding an untested route to reach
previously unreachable code would only move the gap rather than close it, so
the guard and both promotion modes are exercised here.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.basement import routes as basement_routes


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(basement_routes.router)
    with TestClient(app) as c:
        yield c
    c.app.dependency_overrides.clear()


def _as(role: str):
    def _dep():
        return {"sub": "u1", "role": role}

    return _dep


class TestPromoteGuard:
    def test_unauthenticated_is_refused(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        assert client.post("/basement/promote").status_code in (401, 403)

    def test_ordinary_user_is_refused(self, client):
        """Reading the evidence store is open to any authenticated caller;
        authoring Library articles from it is not."""
        client.app.dependency_overrides[get_current_user] = _as("user")
        resp = client.post("/basement/promote")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin role required"

    def test_admin_is_allowed(self, client):
        client.app.dependency_overrides[get_current_user] = _as("admin")
        assert client.post("/basement/promote", params={"dry_run": True}).status_code == 200


class TestPromoteBehaviour:
    def test_dry_run_reports_without_writing(self, client, monkeypatch):
        seen: dict = {}

        def _fake(limit: int, dry_run: bool):
            seen.update(limit=limit, dry_run=dry_run)
            return {"scanned": 3, "patterns": 1, "promoted": 0, "skipped": 1, "details": []}

        monkeypatch.setattr(basement_routes, "promote_patterns", _fake)
        client.app.dependency_overrides[get_current_user] = _as("admin")

        resp = client.post("/basement/promote", params={"dry_run": True, "limit": 42})
        assert resp.status_code == 200
        assert seen == {"limit": 42, "dry_run": True}
        assert resp.json()["promoted"] == 0

    def test_defaults_are_passed_through(self, client, monkeypatch):
        seen: dict = {}
        monkeypatch.setattr(
            basement_routes,
            "promote_patterns",
            lambda limit, dry_run: seen.update(limit=limit, dry_run=dry_run) or {"promoted": 0},
        )
        client.app.dependency_overrides[get_current_user] = _as("admin")

        assert client.post("/basement/promote").status_code == 200
        assert seen == {"limit": 500, "dry_run": False}

    @pytest.mark.parametrize("limit", [0, 5001])
    def test_limit_is_bounded(self, client, limit):
        """An unbounded scan over the evidence store is a denial-of-service
        against the Library, so the bound is validated rather than advisory."""
        client.app.dependency_overrides[get_current_user] = _as("admin")
        assert client.post("/basement/promote", params={"limit": limit}).status_code == 422

    def test_real_promotion_path_runs_end_to_end(self, client):
        """No monkeypatching: proves the route reaches the actual module.

        A test that only ever sees a stub would pass just as happily if the
        import were wrong -- which is the failure being closed here."""
        client.app.dependency_overrides[get_current_user] = _as("admin")
        body = client.post("/basement/promote", params={"dry_run": True}).json()
        assert {"scanned", "failures", "patterns", "promoted", "skipped"} <= set(body)


class TestPromotionIdempotency:
    """Promotion must not raise a second draft from the same evidence.

    Exposing promotion over HTTP made the write path retryable -- a client
    retry, an impatient second click, or two admins acting on the same alert.
    Duplicate drafts are worse than none: the queue is a proposal list an admin
    reads, and a list that repeats itself is one they stop reading.
    """

    def test_the_key_is_stable_for_the_same_signature(self):
        from src.basement.promotion import promotion_key

        assert promotion_key("boom: timeout in x") == promotion_key("boom: timeout in x")

    def test_different_signatures_get_different_keys(self):
        from src.basement.promotion import promotion_key

        assert promotion_key("regression:test_a") != promotion_key("regression:test_b")

    def test_the_key_is_carried_on_the_article(self):
        """The tag is the dedup index, so rendering must actually emit it."""
        from src.basement.promotion import Pattern, promotion_key, render_article

        p = Pattern(kind="cluster", signature="boom", occurrences=3, tests=["t"])
        _, _, tags = render_article(p)
        assert promotion_key("boom") in tags

    def test_a_second_run_over_the_same_evidence_creates_nothing(self, monkeypatch):
        """The behaviour that matters, exercised end to end against a fake
        Library that records every create."""
        from src.basement import promotion as promo

        pattern = promo.Pattern(kind="cluster", signature="boom", occurrences=3, tests=["t"])

        class FakeLibrary:
            def __init__(self):
                self.created = []
                self._tags = set()

            def by_tag(self, tag, limit=50):
                return [object()] if tag in self._tags else []

            def create(self, **kw):
                self.created.append(kw)
                self._tags.update(kw.get("tags", []))
                return type("A", (), {"id": f"art-{len(self.created)}"})()

        library = FakeLibrary()
        monkeypatch.setattr(promo, "_failure_records", lambda records: ["r"])
        monkeypatch.setattr(promo, "cluster_failures", lambda f: [pattern])
        monkeypatch.setattr(promo, "regression_patterns", lambda f: [])

        import src.library.knowledge_base as kb

        monkeypatch.setattr(kb, "get_library", lambda: library)

        import src.basement.archive as archive

        monkeypatch.setattr(
            archive, "get_basement", lambda: type("B", (), {"recent": lambda *a, **k: ["r"]})()
        )

        first = promo.promote()
        second = promo.promote()

        assert first["promoted"] == 1
        assert second["promoted"] == 0
        assert second["duplicates"] == 1
        assert len(library.created) == 1

    def test_a_failing_duplicate_check_does_not_fall_through_to_a_write(self, monkeypatch):
        """The fail-safe branch, and the reason the dedup lookup is guarded.

        If `by_tag` raises -- a corrupt index, a Library mid-restart -- the
        answer to "has this already been promoted?" is unknown, not "no".
        Treating unknown as no would create exactly the duplicate the check
        exists to prevent, and it would do so precisely when the Library is
        already unhealthy. The pattern is skipped and counted instead.
        """
        from src.basement import promotion as promo

        pattern = promo.Pattern(kind="cluster", signature="boom", occurrences=3, tests=["t"])

        class BrokenLookup:
            def __init__(self):
                self.created = []

            def by_tag(self, tag, limit=50):
                raise RuntimeError("tag index unavailable")

            def create(self, **kw):  # pragma: no cover - must never be reached
                self.created.append(kw)
                raise AssertionError("wrote a draft despite an unknown duplicate state")

        library = BrokenLookup()
        monkeypatch.setattr(promo, "_failure_records", lambda records: ["r"])
        monkeypatch.setattr(promo, "cluster_failures", lambda f: [pattern])
        monkeypatch.setattr(promo, "regression_patterns", lambda f: [])

        import src.library.knowledge_base as kb

        monkeypatch.setattr(kb, "get_library", lambda: library)

        import src.basement.archive as archive

        monkeypatch.setattr(
            archive, "get_basement", lambda: type("B", (), {"recent": lambda *a, **k: ["r"]})()
        )

        result = promo.promote()

        assert result["promoted"] == 0
        assert result["skipped"] == 1
        assert result["duplicates"] == 0
        assert library.created == []
