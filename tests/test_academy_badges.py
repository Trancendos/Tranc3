# tests/test_academy_badges.py
# Tests for the-academy worker's badges/achievements feature
# (workers/the-academy/worker.py) — awarded on course/lesson progress.

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests._worker_import_utils import import_worker as _import_worker

_TRANC3_ROOT = Path(__file__).resolve().parent.parent

academy_mod = _import_worker(
    "the_academy_worker", _TRANC3_ROOT / "workers" / "the-academy" / "worker.py"
)


@pytest.fixture
def academy(tmp_path, monkeypatch):
    monkeypatch.setattr(academy_mod, "DB_PATH", tmp_path / "academy_test.db")
    academy_mod.init_db()
    return academy_mod


def _make_course_with_lessons(mod, n_lessons: int, category: str = "general") -> tuple[int, list]:
    now = time.time()
    with mod.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO courses (title, description, category, difficulty, created_by, "
            "created_at) VALUES (?,?,?,?,?,?)",
            ("Test Course", "desc", category, "beginner", "system", now),
        )
        conn.commit()
        course_id = cur.lastrowid
        lesson_ids = []
        for i in range(n_lessons):
            lcur = conn.execute(
                "INSERT INTO lessons (course_id, title, content, position, duration_min, "
                "lesson_type, created_at) VALUES (?,?,?,?,?,?,?)",
                (course_id, f"Lesson {i}", "content", i, 5, "text", now),
            )
            conn.commit()
            lesson_ids.append(lcur.lastrowid)
    return course_id, lesson_ids


def _enrol(mod, user_id: str, course_id: int) -> None:
    with mod.get_conn() as conn:
        conn.execute(
            "INSERT INTO enrolments (user_id, course_id, enrolled_at) VALUES (?,?,?)",
            (user_id, course_id, time.time()),
        )
        conn.commit()


class TestBadgeSeeding:
    def test_default_badges_seeded(self, academy):
        with academy.get_conn() as conn:
            codes = {r["code"] for r in conn.execute("SELECT code FROM badges").fetchall()}
        assert codes == {"first_steps", "dedicated_learner", "perfectionist", "well_rounded"}

    def test_seeding_is_idempotent_across_reinit(self, academy):
        academy.init_db()
        academy.init_db()
        with academy.get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM badges").fetchone()[0]
        assert count == 4


class TestFirstStepsBadge:
    def test_completing_first_course_awards_first_steps(self, academy):
        course_id, lesson_ids = _make_course_with_lessons(academy, n_lessons=1)
        _enrol(academy, "user-1", course_id)
        now = time.time()
        with academy.get_conn() as conn:
            conn.execute(
                "INSERT INTO progress (user_id, lesson_id, course_id, completed, completed_at, "
                "score) VALUES (?,?,?,1,?,?)",
                ("user-1", lesson_ids[0], course_id, now, 80),
            )
            conn.commit()
            conn.execute(
                "UPDATE enrolments SET completed_at=? WHERE user_id=? AND course_id=?",
                (now, "user-1", course_id),
            )
            conn.commit()
            newly_awarded = academy._check_and_award_badges(conn, "user-1", now)
        codes = {b["code"] for b in newly_awarded}
        assert "first_steps" in codes

    def test_badge_not_re_awarded_on_second_check(self, academy):
        course_id, lesson_ids = _make_course_with_lessons(academy, n_lessons=1)
        _enrol(academy, "user-1", course_id)
        now = time.time()
        with academy.get_conn() as conn:
            conn.execute(
                "UPDATE enrolments SET completed_at=? WHERE user_id=? AND course_id=?",
                (now, "user-1", course_id),
            )
            conn.commit()
            first = academy._check_and_award_badges(conn, "user-1", now)
            second = academy._check_and_award_badges(conn, "user-1", now)
        assert any(b["code"] == "first_steps" for b in first)
        assert second == []

    def test_pre_inserted_badge_does_not_crash_or_double_award(self, academy):
        """Simulates the concurrent-award race: a badge row already exists
        (inserted by a racing request) when _check_and_award_badges runs.
        INSERT OR IGNORE must not raise, and the badge must not be counted
        as newly awarded again."""
        course_id, _ = _make_course_with_lessons(academy, n_lessons=1)
        _enrol(academy, "user-1", course_id)
        now = time.time()
        with academy.get_conn() as conn:
            conn.execute(
                "UPDATE enrolments SET completed_at=? WHERE user_id=? AND course_id=?",
                (now, "user-1", course_id),
            )
            # Pre-insert the first_steps badge as if a concurrent request won
            # the race, but leave `already_earned`'s snapshot unaware of it by
            # inserting AFTER that snapshot would have been taken — emulated
            # here by inserting directly then calling the awarder.
            badge_id = conn.execute("SELECT id FROM badges WHERE code='first_steps'").fetchone()[
                "id"
            ]
            conn.execute(
                "INSERT INTO user_badges (user_id, badge_id, awarded_at, course_id) "
                "VALUES (?,?,?,NULL)",
                ("user-1", badge_id, now),
            )
            conn.commit()
            awarded = academy._check_and_award_badges(conn, "user-1", now)
        # first_steps was already present → not re-counted; no IntegrityError.
        assert all(b["code"] != "first_steps" for b in awarded)


class TestPerfectionistBadge:
    def test_perfect_score_awards_perfectionist_mid_course(self, academy):
        course_id, lesson_ids = _make_course_with_lessons(academy, n_lessons=3)
        _enrol(academy, "user-1", course_id)
        now = time.time()
        with academy.get_conn() as conn:
            conn.execute(
                "INSERT INTO progress (user_id, lesson_id, course_id, completed, completed_at, "
                "score) VALUES (?,?,?,1,?,?)",
                ("user-1", lesson_ids[0], course_id, now, 100),
            )
            conn.commit()
            newly_awarded = academy._check_and_award_badges(conn, "user-1", now)
        codes = {b["code"] for b in newly_awarded}
        assert "perfectionist" in codes
        # course isn't complete yet (only 1 of 3 lessons done) — first_steps
        # should NOT have been awarded alongside it.
        assert "first_steps" not in codes


class TestWellRoundedBadge:
    def test_three_distinct_categories_awards_well_rounded(self, academy):
        now = time.time()
        for i, category in enumerate(["finance", "security", "wellbeing"]):
            course_id, _ = _make_course_with_lessons(academy, n_lessons=1, category=category)
            _enrol(academy, "user-1", course_id)
            with academy.get_conn() as conn:
                conn.execute(
                    "UPDATE enrolments SET completed_at=? WHERE user_id=? AND course_id=?",
                    (now, "user-1", course_id),
                )
                conn.commit()
        with academy.get_conn() as conn:
            newly_awarded = academy._check_and_award_badges(conn, "user-1", now)
        codes = {b["code"] for b in newly_awarded}
        assert "well_rounded" in codes


class TestMarkProgressIntegration:
    def test_mark_progress_response_includes_newly_awarded_badges(self, academy):
        from fastapi.testclient import TestClient

        course_id, lesson_ids = _make_course_with_lessons(academy, n_lessons=1)
        _enrol(academy, "user-1", course_id)
        with TestClient(academy.app) as client:
            resp = client.post(
                "/progress",
                json={"user_id": "user-1", "lesson_id": lesson_ids[0], "score": 100},
                headers={"X-Internal-Secret": academy.INTERNAL_SECRET},
            )
        assert resp.status_code == 201
        body = resp.json()
        codes = {b["code"] for b in body["newly_awarded_badges"]}
        assert "first_steps" in codes
        assert "perfectionist" in codes

    def test_get_user_badges_endpoint(self, academy):
        from fastapi.testclient import TestClient

        course_id, lesson_ids = _make_course_with_lessons(academy, n_lessons=1)
        _enrol(academy, "user-1", course_id)
        with TestClient(academy.app) as client:
            client.post(
                "/progress",
                json={"user_id": "user-1", "lesson_id": lesson_ids[0], "score": 50},
                headers={"X-Internal-Secret": academy.INTERNAL_SECRET},
            )
            resp = client.get(
                "/users/user-1/badges", headers={"X-Internal-Secret": academy.INTERNAL_SECRET}
            )
        assert resp.status_code == 200
        codes = {b["code"] for b in resp.json()}
        assert "first_steps" in codes

    def test_list_badges_endpoint(self, academy):
        from fastapi.testclient import TestClient

        with TestClient(academy.app) as client:
            resp = client.get("/badges", headers={"X-Internal-Secret": academy.INTERNAL_SECRET})
        assert resp.status_code == 200
        assert len(resp.json()) == 4


class TestBadgeBackfill:
    def _complete_a_course(self, academy, user_id):
        course_id, _ = _make_course_with_lessons(academy, n_lessons=1)
        _enrol(academy, user_id, course_id)
        now = time.time()
        with academy.get_conn() as conn:
            conn.execute(
                "UPDATE enrolments SET completed_at=? WHERE user_id=? AND course_id=?",
                (now, user_id, course_id),
            )
            conn.commit()

    def test_reevaluate_awards_badges_for_pre_existing_completion(self, academy):
        from fastapi.testclient import TestClient

        # A learner completed a course before badges existed — no /progress
        # call ever ran the awarder, so they have no badges yet.
        self._complete_a_course(academy, "old-user")
        with academy.get_conn() as conn:
            existing = conn.execute(
                "SELECT COUNT(*) FROM user_badges WHERE user_id='old-user'"
            ).fetchone()[0]
        assert existing == 0

        with TestClient(academy.app) as client:
            resp = client.post(
                "/users/old-user/badges/reevaluate",
                headers={"X-Internal-Secret": academy.INTERNAL_SECRET},
            )
        assert resp.status_code == 200
        codes = {b["code"] for b in resp.json()["newly_awarded_badges"]}
        assert "first_steps" in codes

    def test_reevaluate_is_idempotent(self, academy):
        from fastapi.testclient import TestClient

        self._complete_a_course(academy, "old-user")
        with TestClient(academy.app) as client:
            first = client.post(
                "/users/old-user/badges/reevaluate",
                headers={"X-Internal-Secret": academy.INTERNAL_SECRET},
            ).json()
            second = client.post(
                "/users/old-user/badges/reevaluate",
                headers={"X-Internal-Secret": academy.INTERNAL_SECRET},
            ).json()
        assert first["newly_awarded_badges"]
        assert second["newly_awarded_badges"] == []

    def test_backfill_all_evaluates_every_learner(self, academy):
        from fastapi.testclient import TestClient

        self._complete_a_course(academy, "user-a")
        self._complete_a_course(academy, "user-b")
        with TestClient(academy.app) as client:
            resp = client.post(
                "/badges/backfill", headers={"X-Internal-Secret": academy.INTERNAL_SECRET}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["users_evaluated"] >= 2
        assert body["users_awarded"] == 2
        assert set(body["awarded_by_user"].keys()) == {"user-a", "user-b"}
