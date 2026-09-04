"""The Imaginarium fan-out: does a brief actually reach the Locations it names?

The worker addressed six Locations in SERVICE_URLS, docker-compose supplied
all six URLs, and the fan-out called two of them. It also tested the image
leg's response for HTTP 202 against a service that answers 200, so that leg's
result was discarded on every call with no error recorded — the project
completed with an empty results block and looked healthy.

These tests run the fan-out against a stub estate and assert on what it sent
and what it stored, because both failures were invisible from the outside.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from tests._worker_import_utils import import_worker

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def imaginarium(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_SECRET", "test-secret-value-not-default")
    worker = import_worker("imaginarium_worker", REPO / "workers" / "imaginarium" / "worker.py")
    worker.DB_PATH = tmp_path / "imaginarium.db"
    worker.init_db()
    return worker


class _Response:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class _StubEstate:
    """Records every POST and answers with a per-URL scripted response."""

    def __init__(self, responses=None, default=None):
        self.calls: list[tuple[str, dict]] = []
        self._responses = responses or {}
        self._default = default or _Response(201, {"id": 1})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):  # noqa: A002 - httpx's signature
        self.calls.append((url, json or {}))
        for fragment, resp in self._responses.items():
            if fragment in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return self._default

    @property
    def urls(self) -> list[str]:
        return [u for u, _ in self.calls]


def _run(worker, stub, project_id, brief, project_type, title=""):
    import httpx

    original = httpx.AsyncClient
    httpx.AsyncClient = lambda *a, **k: stub  # noqa: ARG005
    try:
        asyncio.run(worker._fan_out_creation(project_id, brief, project_type, title))
    finally:
        httpx.AsyncClient = original


def _seed(worker, project_type="mixed") -> int:
    with worker.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects (title, brief, project_type, status, created_by, created_at) "
            "VALUES (?,?,?,?,?,?)",
            ("Brief", "a lighthouse at dusk", project_type, "pending", "test", 0.0),
        )
        conn.commit()
        return cur.lastrowid


def _row(worker, project_id) -> sqlite3.Row:
    with worker.get_conn() as conn:
        return conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()


class TestTheDroppedResult:
    def test_a_200_from_the_image_service_is_recorded(self, imaginarium):
        """Calibrated: restoring `status_code == 202` fails this.

        Sashas Photo Studio's /photo/generate answers 200. The old check
        matched only 202, so the image leg's result went nowhere and no
        error was recorded either.
        """
        stub = _StubEstate({"sashas": _Response(200, {"job_id": "abc", "source": "comfyui"})})
        pid = _seed(imaginarium, "game_assets")
        _run(imaginarium, stub, pid, "a lighthouse at dusk", "game_assets")

        results = json.loads(_row(imaginarium, pid)["results"])
        assert results["image"]["ok"] is True
        assert results["image"]["result"]["job_id"] == "abc"

    def test_a_202_is_still_recorded(self, imaginarium):
        """The old behaviour must keep working, not be traded for the new one."""
        stub = _StubEstate({"sashas": _Response(202, {"job_id": "queued"})})
        pid = _seed(imaginarium, "game_assets")
        _run(imaginarium, stub, pid, "brief", "game_assets")
        assert json.loads(_row(imaginarium, pid)["results"])["image"]["ok"] is True

    def test_a_2xx_with_no_json_body_is_still_a_success(self, imaginarium):
        """Calibrated: letting resp.json() raise out of _call_leg fails this.

        A 204, or a 200 with an empty body, is a service that did the work.
        Treating it as a failure would invent an outage.
        """
        stub = _StubEstate({"sashas": _Response(204, None)})
        pid = _seed(imaginarium, "game_assets")
        _run(imaginarium, stub, pid, "brief", "game_assets")
        image = json.loads(_row(imaginarium, pid)["results"])["image"]
        assert image["ok"] is True
        assert image["result"] == {}

    def test_a_non_2xx_is_recorded_as_a_failure_with_its_status(self, imaginarium):
        """Calibrated: recording only `ok` without the status fails this.

        A 401 and a 503 need different responses from an operator, so
        collapsing them into "the leg failed" throws away the only part that
        says which.
        """
        stub = _StubEstate({"fabulousa": _Response(401, None, text="unauthorised")})
        pid = _seed(imaginarium, "brand")
        _run(imaginarium, stub, pid, "brief", "brand")
        design = json.loads(_row(imaginarium, pid)["results"])["design"]
        assert design["ok"] is False
        assert design["status"] == 401


class TestEveryAddressedLocationIsCalled:
    def test_a_game_brief_reaches_tranceflow(self, imaginarium):
        """Calibrated: removing the game leg fails this.

        This is the finding in one line: `game_assets` used to produce an
        image and a design file, and no game.
        """
        stub = _StubEstate()
        pid = _seed(imaginarium, "game_assets")
        _run(imaginarium, stub, pid, "a platformer set in a lighthouse", "game_assets")
        assert any("tranceflow" in u for u in stub.urls)
        assert json.loads(_row(imaginarium, pid)["results"])["game"]["ok"] is True

    def test_a_mixed_brief_reaches_every_addressed_location(self, imaginarium):
        """Calibrated: dropping any leg from FAN_OUT_LEGS fails this.

        Every URL in SERVICE_URLS is an address the deployment configures.
        One that is never called is a promise compose keeps and the code
        does not.
        """
        stub = _StubEstate()
        pid = _seed(imaginarium, "mixed")
        _run(imaginarium, stub, pid, "brief", "mixed")
        called = {
            name
            for name, base in imaginarium.SERVICE_URLS.items()
            if any(base in u for u in stub.urls)
        }
        assert called == set(imaginarium.SERVICE_URLS)

    def test_the_studio_opens_a_workspace_for_every_project_type(self, imaginarium):
        """Calibrated: giving the workspace leg a non-empty `types` fails this."""
        for project_type in ("mixed", "brand", "music_visual", "game_assets", "video_image"):
            stub = _StubEstate()
            pid = _seed(imaginarium, project_type)
            _run(imaginarium, stub, pid, "brief", project_type)
            assert any("the-studio" in u for u in stub.urls), project_type

    def test_each_leg_sends_the_body_its_service_expects(self, imaginarium):
        """Calibrated: reusing one payload shape across legs fails this.

        TranceFlow's GameIn requires `title`; Warp Radio's PlaylistIn
        requires `name`. A single shared body would 422 at whichever service
        it did not fit.
        """
        stub = _StubEstate()
        pid = _seed(imaginarium, "mixed")
        _run(imaginarium, stub, pid, "brief text", "mixed", title="A Title")
        sent = {url: body for url, body in stub.calls}
        game = next(b for u, b in sent.items() if "tranceflow" in u)
        radio = next(b for u, b in sent.items() if "warp-radio" in u)
        assert game["title"] == "A Title"
        assert radio["name"] == "A Title"


class TestTheStatusTellsTheTruth:
    def test_every_leg_failing_is_not_a_completed_project(self, imaginarium):
        """Calibrated: hardcoding status='completed' fails this.

        The old code wrote 'completed' unconditionally. A brief whose every
        leg was refused looked identical to one that worked.
        """
        stub = _StubEstate(default=_Response(503, None, text="down"))
        pid = _seed(imaginarium, "mixed")
        _run(imaginarium, stub, pid, "brief", "mixed")
        assert _row(imaginarium, pid)["status"] == "failed"

    def test_some_legs_failing_is_partial(self, imaginarium):
        stub = _StubEstate({"sashas": _Response(503, None, text="down")})
        pid = _seed(imaginarium, "mixed")
        _run(imaginarium, stub, pid, "brief", "mixed")
        assert _row(imaginarium, pid)["status"] == "partial"

    def test_every_leg_succeeding_is_completed(self, imaginarium):
        stub = _StubEstate()
        pid = _seed(imaginarium, "mixed")
        _run(imaginarium, stub, pid, "brief", "mixed")
        assert _row(imaginarium, pid)["status"] == "completed"

    def test_a_transport_error_on_one_leg_does_not_end_the_brief(self, imaginarium):
        """Calibrated: letting the exception escape _call_leg fails this.

        One unreachable Location must not stop the other five, and the
        project must still be written rather than left pending forever.
        """
        stub = _StubEstate({"warp-radio": ConnectionError("no route to host")})
        pid = _seed(imaginarium, "mixed")
        _run(imaginarium, stub, pid, "brief", "mixed")
        row = _row(imaginarium, pid)
        results = json.loads(row["results"])
        assert row["status"] == "partial"
        assert results["soundtrack"]["ok"] is False
        assert "no route to host" in results["soundtrack"]["error"]
        assert results["image"]["ok"] is True
