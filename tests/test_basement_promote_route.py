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

from src.basement import routes as basement_routes


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(basement_routes.router)
    with TestClient(app) as c:
        yield c
    c.app.dependency_overrides.clear()


def _authenticate_as(monkeypatch, role: str) -> None:
    """Stand in for the bearer-token check with a caller of the given role.

    The guard calls `get_current_user` as a module global rather than declaring
    it as a FastAPI dependency, because the service-secret path has to be able
    to answer before the bearer check runs and refuses. Patching the global is
    therefore the equivalent of the usual `dependency_overrides` idiom, and it
    leaves the guard's own branching under test rather than replaced.
    """

    async def _dep(credentials=None):
        return {"sub": "u1", "role": role}

    monkeypatch.setattr(basement_routes, "get_current_user", _dep)


class TestPromoteGuard:
    def test_unauthenticated_is_refused(self, client):
        assert client.post("/basement/promote").status_code in (401, 403)

    def test_ordinary_user_is_refused(self, client, monkeypatch):
        """Reading the evidence store is open to any authenticated caller;
        authoring Library articles from it is not."""
        _authenticate_as(monkeypatch, "user")
        resp = client.post("/basement/promote")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin role required"

    def test_admin_is_allowed(self, client, monkeypatch):
        _authenticate_as(monkeypatch, "admin")
        assert client.post("/basement/promote", params={"dry_run": True}).status_code == 200

    def test_the_internal_secret_authenticates_a_service_caller(self, client, monkeypatch):
        """ChronosSphere has no user session, so without this it posts as nobody.

        The seeded daily job would otherwise run, be recorded as a run, and
        promote nothing -- a schedule that reports activity and produces none.
        """
        monkeypatch.setattr(basement_routes, "_INTERNAL_SECRET", "s3cret")
        resp = client.post(
            "/basement/promote",
            params={"dry_run": True},
            headers={"X-Internal-Secret": "s3cret"},
        )
        assert resp.status_code == 200

    def test_a_wrong_internal_secret_is_refused(self, client, monkeypatch):
        monkeypatch.setattr(basement_routes, "_INTERNAL_SECRET", "s3cret")
        resp = client.post("/basement/promote", headers={"X-Internal-Secret": "wrong"})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Forbidden"

    def test_an_unconfigured_secret_is_not_a_bypass(self, client, monkeypatch):
        """The property that separates this guard from the estate's others.

        Routes that check `if _INTERNAL_SECRET and ...` treat an unset secret as
        "no check". Here the header is an alternative to an ADMIN credential, so
        that reading would make an empty environment variable a password-less
        admin bypass. Unset must mean the path is closed, not open.
        """
        monkeypatch.setattr(basement_routes, "_INTERNAL_SECRET", "")
        resp = client.post("/basement/promote", headers={"X-Internal-Secret": ""})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Service authentication is not configured"


class TestPromoteBehaviour:
    def test_dry_run_reports_without_writing(self, client, monkeypatch):
        seen: dict = {}

        def _fake(limit: int, dry_run: bool):
            seen.update(limit=limit, dry_run=dry_run)
            return {"scanned": 3, "patterns": 1, "promoted": 0, "skipped": 1, "details": []}

        monkeypatch.setattr(basement_routes, "promote_patterns", _fake)
        _authenticate_as(monkeypatch, "admin")

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
        _authenticate_as(monkeypatch, "admin")

        assert client.post("/basement/promote").status_code == 200
        assert seen == {"limit": 500, "dry_run": False}

    @pytest.mark.parametrize("limit", [0, 5001])
    def test_limit_is_bounded(self, client, monkeypatch, limit):
        """An unbounded scan over the evidence store is a denial-of-service
        against the Library, so the bound is validated rather than advisory."""
        _authenticate_as(monkeypatch, "admin")
        assert client.post("/basement/promote", params={"limit": limit}).status_code == 422

    def test_real_promotion_path_runs_end_to_end(self, client, monkeypatch):
        """Promotion itself is not stubbed: the route reaches the real module.

        A test that only ever saw a stub would pass just as happily if the
        import were wrong -- which is the failure being closed here."""
        _authenticate_as(monkeypatch, "admin")
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


class TestConcurrentPromotion:
    """Two callers racing on the same evidence must produce one draft.

    The earlier dedup made promotion idempotent for a *retry* -- a second call
    after the first finished. It did not make it safe for a *race*: check and
    create were separate steps, so two admins clicking at the same moment could
    both find no matching tag and both author a draft. The commit that added
    the dedup claimed "a retry or a second admin cannot raise a duplicate";
    the second half of that was not true, and this is what makes it true.

    The barrier is the point of the test: it forces both threads to complete
    their duplicate check before either is allowed to write, which is precisely
    the interleaving that defeats an unlocked check-then-create. Without the
    lock this test fails, deterministically rather than flakily.
    """

    def test_two_racing_promotions_create_one_draft(self, monkeypatch):
        import threading

        from src.basement import promotion as promo

        pattern = promo.Pattern(kind="cluster", signature="boom", occurrences=3, tests=["t"])

        class RacingLibrary:
            def __init__(self):
                self.created = []
                self._tags = set()
                self._guard = threading.Lock()
                # Released once both threads have run their duplicate check.
                self.both_checked = threading.Barrier(2, timeout=5)

            def by_tag(self, tag, limit=50):
                present = tag in self._tags
                try:
                    self.both_checked.wait()
                except threading.BrokenBarrierError:  # pragma: no cover - timing guard
                    pass
                return [object()] if present else []

            def create(self, **kw):
                with self._guard:
                    self.created.append(kw)
                    self._tags.update(kw.get("tags", []))
                return type("A", (), {"id": f"art-{len(self.created)}"})()

        library = RacingLibrary()
        monkeypatch.setattr(promo, "_failure_records", lambda records: ["r"])
        monkeypatch.setattr(promo, "cluster_failures", lambda f: [pattern])
        monkeypatch.setattr(promo, "regression_patterns", lambda f: [])

        import src.library.knowledge_base as kb

        monkeypatch.setattr(kb, "get_library", lambda: library)

        import src.basement.archive as archive

        monkeypatch.setattr(
            archive, "get_basement", lambda: type("B", (), {"recent": lambda *a, **k: ["r"]})()
        )

        # The barrier requires both duplicate checks to happen before either
        # write. Under the lock the second thread cannot reach its check until
        # the first has finished writing, so the barrier would deadlock -- the
        # timeout breaks it and the second caller then sees the existing tag.
        results: list = []
        threads = [
            threading.Thread(target=lambda: results.append(promo.promote())) for _ in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert len(library.created) == 1, "the race produced a duplicate Library draft"
        assert sum(r["promoted"] for r in results) == 1


class TestTheLockIsNeverLeaked:
    def test_a_failing_create_still_releases_the_lock(self, monkeypatch):
        """The critical section became a `with` block precisely so a raise in
        `create()` cannot strand the lock. If it did, every later promotion in
        the process would block forever -- a deadlock that only appears after
        an unrelated Library failure."""
        from src.basement import promotion as promo

        pattern = promo.Pattern(kind="cluster", signature="boom", occurrences=3, tests=["t"])

        class FailingLibrary:
            def by_tag(self, tag, limit=50):
                return []

            def create(self, **kw):
                raise RuntimeError("library write failed")

        monkeypatch.setattr(promo, "_failure_records", lambda records: ["r"])
        monkeypatch.setattr(promo, "cluster_failures", lambda f: [pattern])
        monkeypatch.setattr(promo, "regression_patterns", lambda f: [])

        import src.library.knowledge_base as kb

        monkeypatch.setattr(kb, "get_library", lambda: FailingLibrary())

        import src.basement.archive as archive

        monkeypatch.setattr(
            archive, "get_basement", lambda: type("B", (), {"recent": lambda *a, **k: ["r"]})()
        )

        result = promo.promote()
        assert result["skipped"] == 1 and result["promoted"] == 0
        # The real assertion: the lock is free afterwards.
        assert promo._PROMOTION_LOCK.acquire(timeout=2), "the lock was leaked by a failed create"
        promo._PROMOTION_LOCK.release()
