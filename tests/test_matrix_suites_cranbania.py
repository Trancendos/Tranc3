# tests/test_matrix_suites_cranbania.py
# Matrix Suites Stage 7.4: src/compliance/matrix_suites_cranbania.py ensures each suite
# has an open CranBania review card (tags substituting for a "lane" CranBania's board
# schema doesn't have — see the module's own docstring). Uses a fake httpx.AsyncClient
# (same pattern as tests/test_resonate_escalation.py) rather than a live CranBania.

from __future__ import annotations

from datetime import date, timedelta

import pytest
import yaml

from src.compliance.matrix_suites_cranbania import (
    SyncSummary,
    _sla_response_hours,
    sync_suite_review_cards,
)

TODAY = date.today()
FUTURE_DATE = (TODAY + timedelta(days=10)).isoformat()
PAST_DATE = (TODAY - timedelta(days=3)).isoformat()

FIXTURE = {
    "meta": {},
    "suites": [
        {
            "suite_id": "SUITE-FIN",
            "name": "Financial Suite",
            "pillar": "Commercial / Financial",
            "steward_ai": "Dorris Fontaine",
            "steward_location": "Royal Bank of Arcadia",
            "review_cadence": "monthly",
            "next_review": FUTURE_DATE,
            "observatory_events": "governance.suite.financial.*",
        },
        {
            "suite_id": "SUITE-SEC",
            "name": "Security Suite",
            "pillar": "Security",
            "steward_ai": "Renik",
            "steward_location": "Cryptex",
            "review_cadence": "monthly",
            "next_review": PAST_DATE,
            "observatory_events": "governance.suite.security.*",
        },
    ],
}


def _write_fixture(tmp_path) -> str:
    p = tmp_path / "matrix_suites.yaml"
    p.write_text(yaml.safe_dump(FIXTURE), encoding="utf-8")
    return str(p)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("error", request=None, response=self)


class _FakeAsyncClient:
    """Records calls; GET /api/cards returns a configurable card list, POST
    /api/cards echoes back a created card (or raises, per test config)."""

    def __init__(self, existing_cards=None, fail_list=False, fail_create_for=None):
        self._existing_cards = existing_cards or []
        self._fail_list = fail_list
        self._fail_create_for = fail_create_for or set()
        self.get_calls = []
        self.post_calls = []
        self.captured_base_url = None
        self.captured_headers = None

    def __call__(self, *args, **kwargs):
        self.captured_base_url = kwargs.get("base_url")
        self.captured_headers = kwargs.get("headers")
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, path, **kwargs):
        self.get_calls.append(path)
        if self._fail_list:
            return _FakeResponse(500, {})
        return _FakeResponse(200, {"cards": self._existing_cards})

    async def post(self, path, json=None, **kwargs):
        self.post_calls.append((path, json))
        suite_id = json["tags"][1]
        if suite_id in self._fail_create_for:
            return _FakeResponse(500, {})
        return _FakeResponse(201, {"card": {"id": f"card-{suite_id}", **json}})


def _install_fake_client(monkeypatch, **kwargs):
    import httpx

    fake = _FakeAsyncClient(**kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    return fake


class TestSlaResponseHours:
    def test_future_review_computes_positive_hours(self):
        from src.compliance.matrix_suites import SuiteHealth

        health = SuiteHealth(
            suite_id="x",
            name="X",
            pillar="",
            steward_ai="",
            steward_location="",
            review_cadence="",
            next_review=FUTURE_DATE,
            overdue=False,
            days_overdue=0,
            event_prefix="",
            matrix_count=0,
            next_review_valid=True,
        )
        hours = _sla_response_hours(health, today=TODAY)
        assert hours == 10 * 24

    def test_overdue_review_clamps_to_one_hour(self):
        from src.compliance.matrix_suites import SuiteHealth

        health = SuiteHealth(
            suite_id="x",
            name="X",
            pillar="",
            steward_ai="",
            steward_location="",
            review_cadence="",
            next_review=PAST_DATE,
            overdue=True,
            days_overdue=3,
            event_prefix="",
            matrix_count=0,
            next_review_valid=True,
        )
        hours = _sla_response_hours(health, today=TODAY)
        assert hours == 1  # clamped, never negative/zero


class TestSyncSuiteReviewCards:
    @pytest.mark.asyncio
    async def test_creates_cards_for_suites_with_no_open_card(self, tmp_path, monkeypatch):
        fake = _install_fake_client(monkeypatch, existing_cards=[])
        path = _write_fixture(tmp_path)

        summary = await sync_suite_review_cards(
            matrix_suites_path=path, cranbania_url="http://cranbania:8071", api_key="k"
        )

        assert isinstance(summary, SyncSummary)
        assert summary.created == 2
        assert summary.errors == 0
        created_suite_ids = {json["tags"][1] for _, json in fake.post_calls}
        assert created_suite_ids == {"SUITE-FIN", "SUITE-SEC"}

    @pytest.mark.asyncio
    async def test_skips_suite_with_existing_open_card(self, tmp_path, monkeypatch):
        existing = [
            {"id": "c1", "tags": ["matrix-suite", "SUITE-FIN"], "columnId": "review"},
        ]
        fake = _install_fake_client(monkeypatch, existing_cards=existing)
        path = _write_fixture(tmp_path)

        summary = await sync_suite_review_cards(matrix_suites_path=path)

        assert summary.created == 1  # only SUITE-SEC
        assert summary.skipped == 1
        created_suite_ids = {json["tags"][1] for _, json in fake.post_calls}
        assert created_suite_ids == {"SUITE-SEC"}

    @pytest.mark.asyncio
    async def test_done_card_does_not_block_a_fresh_cycle(self, tmp_path, monkeypatch):
        """A suite whose current review was completed (card moved to Done)
        must get a NEW card next sync — that's a new cadence cycle, not a
        re-notification of the closed one."""
        existing = [
            {"id": "c1", "tags": ["matrix-suite", "SUITE-FIN"], "columnId": "done"},
        ]
        fake = _install_fake_client(monkeypatch, existing_cards=existing)
        path = _write_fixture(tmp_path)

        summary = await sync_suite_review_cards(matrix_suites_path=path)

        assert summary.created == 2
        created_suite_ids = {json["tags"][1] for _, json in fake.post_calls}
        assert "SUITE-FIN" in created_suite_ids

    @pytest.mark.asyncio
    async def test_suite_with_invalid_next_review_is_skipped_not_errored(
        self, tmp_path, monkeypatch
    ):
        broken = dict(FIXTURE)
        broken["suites"] = [dict(FIXTURE["suites"][0], next_review="not-a-date")]
        p = tmp_path / "matrix_suites.yaml"
        p.write_text(yaml.safe_dump(broken), encoding="utf-8")

        fake = _install_fake_client(monkeypatch, existing_cards=[])
        summary = await sync_suite_review_cards(matrix_suites_path=str(p))

        assert summary.created == 0
        assert summary.skipped == 1
        assert summary.errors == 0
        assert fake.post_calls == []

    @pytest.mark.asyncio
    async def test_list_failure_marks_every_suite_as_error(self, tmp_path, monkeypatch):
        _install_fake_client(monkeypatch, fail_list=True)
        path = _write_fixture(tmp_path)

        summary = await sync_suite_review_cards(matrix_suites_path=path)

        assert summary.errors == 2
        assert summary.created == 0

    @pytest.mark.asyncio
    async def test_create_failure_for_one_suite_does_not_block_the_other(
        self, tmp_path, monkeypatch
    ):
        _install_fake_client(monkeypatch, existing_cards=[], fail_create_for={"SUITE-FIN"})
        path = _write_fixture(tmp_path)

        summary = await sync_suite_review_cards(matrix_suites_path=path)

        assert summary.created == 1
        assert summary.errors == 1
        error_ids = {r.suite_id for r in summary.results if r.action == "error"}
        assert error_ids == {"SUITE-FIN"}

    @pytest.mark.asyncio
    async def test_falls_back_to_env_vars_when_args_omitted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CRANBANIA_URL", "http://cranbania-custom:9999")
        monkeypatch.setenv("CRANBANIA_API_KEY", "env-key")
        fake = _install_fake_client(monkeypatch, existing_cards=[])
        path = _write_fixture(tmp_path)

        await sync_suite_review_cards(matrix_suites_path=path)

        assert fake.captured_base_url == "http://cranbania-custom:9999"
        assert fake.captured_headers == {"Authorization": "Bearer env-key"}

    @pytest.mark.asyncio
    async def test_no_auth_header_when_api_key_blank(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CRANBANIA_API_KEY", raising=False)
        fake = _install_fake_client(monkeypatch, existing_cards=[])
        path = _write_fixture(tmp_path)

        await sync_suite_review_cards(matrix_suites_path=path, api_key="")

        assert fake.captured_headers == {}
