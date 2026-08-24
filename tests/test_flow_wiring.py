"""Tests for three Location flows that were built but connected to nothing.

Each of these Locations already existed, was composed, and answered health
checks. What was missing was the caller. These tests exercise the callers, not
the Locations -- a test that only asserts the Location still exists would
reproduce the exact blind spot that let the flows read as finished.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

from tests._worker_import_utils import import_worker

REPO = Path(__file__).resolve().parent.parent
REPORTER = REPO / "scripts" / "report_tests_to_chaos_party.py"


# ---------------------------------------------------------------------------
# A stub Chaos Party
# ---------------------------------------------------------------------------


class _StubChaosParty(BaseHTTPRequestHandler):
    """Records posted batches; `status_code` is patched per test."""

    status_code = 201
    received: list[dict] = []

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's API
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).received.append({"path": self.path, "body": body, "headers": dict(self.headers)})
        payload = json.dumps({"inserted": len(body.get("runs", []))}).encode()
        self.send_response(type(self).status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence the test log
        return


@pytest.fixture
def chaos_party():
    _StubChaosParty.received = []
    _StubChaosParty.status_code = 201
    server = HTTPServer(("127.0.0.1", 0), _StubChaosParty)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, _StubChaosParty
    finally:
        server.shutdown()
        server.server_close()


def _results_file(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "test_results.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _run_reporter(results: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **env}
    full_env.pop("CHAOS_PARTY_URL", None)
    full_env.pop("INTERNAL_SECRET", None)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(REPORTER), "--results", str(results)],
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )


# ---------------------------------------------------------------------------
# FLOW-042: CI reports its test run to The Chaos Party
# ---------------------------------------------------------------------------


ROWS = [
    {"test": "tests/a.py::test_one", "outcome": "passed", "duration_ms": 12.5, "commit": "abc"},
    {"test": "tests/a.py::test_two", "outcome": "failed", "duration_ms": 3, "reason": "boom"},
    {"test": "tests/b.py::test_three", "outcome": "xfailed", "duration_ms": 1},
]


def test_reporter_posts_every_result(tmp_path, chaos_party):
    server, stub = chaos_party
    url = f"http://127.0.0.1:{server.server_port}"
    proc = _run_reporter(
        _results_file(tmp_path, ROWS), {"CHAOS_PARTY_URL": url, "INTERNAL_SECRET": "s3cret"}
    )

    assert proc.returncode == 0, proc.stderr
    assert len(stub.received) == 1
    posted = stub.received[0]
    assert posted["path"] == "/runs/batch"
    assert posted["headers"]["X-Internal-Secret"] == "s3cret"

    runs = posted["body"]["runs"]
    assert [r["name"] for r in runs] == [r["test"] for r in ROWS]
    # xfailed is an expected failure, not a pass: reporting it as "passed"
    # would let a known-broken test look healthy in the trend data.
    assert [r["status"] for r in runs] == ["passed", "failed", "skipped"]
    assert runs[1]["error_msg"] == "boom"
    assert runs[0]["metadata"]["commit"] == "abc"


def test_reporter_is_silent_when_no_endpoint_is_configured(tmp_path, chaos_party):
    _, stub = chaos_party
    proc = _run_reporter(_results_file(tmp_path, ROWS), {})

    assert proc.returncode == 0
    assert stub.received == []
    assert "not set" in proc.stdout


def test_reporter_refuses_to_post_without_a_secret(tmp_path, chaos_party):
    server, stub = chaos_party
    proc = _run_reporter(
        _results_file(tmp_path, ROWS),
        {"CHAOS_PARTY_URL": f"http://127.0.0.1:{server.server_port}"},
    )

    # Exit 2, not 0: the endpoint is configured, so silence here would be
    # indistinguishable from a successful report.
    assert proc.returncode == 2
    assert stub.received == []


def test_reporter_fails_when_a_configured_endpoint_rejects_the_batch(tmp_path, chaos_party):
    server, stub = chaos_party
    stub.status_code = 500
    proc = _run_reporter(
        _results_file(tmp_path, ROWS),
        {"CHAOS_PARTY_URL": f"http://127.0.0.1:{server.server_port}", "INTERNAL_SECRET": "s"},
    )

    # This is the property that stops the step becoming decoration: once
    # someone has configured the endpoint, a failed post fails the step.
    assert proc.returncode == 1
    assert "Failed to report" in proc.stderr


def test_ci_invokes_the_reporter():
    """The script is only a flow if something runs it."""
    workflow = yaml.safe_load((REPO / ".github" / "workflows" / "test.yml").read_text())
    steps = workflow["jobs"]["test"]["steps"]
    reporting = [s for s in steps if "report_tests_to_chaos_party.py" in str(s.get("run", ""))]
    assert len(reporting) == 1
    step = reporting[0]
    # `if: always()` matters: a failing suite is the run most worth reporting.
    assert step.get("if") == "always()"
    assert "CHAOS_PARTY_URL" in step["env"]


# ---------------------------------------------------------------------------
# FLOW-031: the Imaginarium fans out to Fabulousa
# ---------------------------------------------------------------------------


def test_imaginarium_knows_where_fabulousa_is():
    worker = import_worker("imaginarium_worker", REPO / "workers" / "imaginarium" / "worker.py")
    assert "fabulousa" in worker.SERVICE_URLS
    assert "fabulousa-service:8048" in worker.SERVICE_URLS["fabulousa"]


def test_compose_gives_imaginarium_the_fabulousa_url():
    compose = yaml.safe_load((REPO / "docker-compose.production.yml").read_text())
    env = compose["services"]["imaginarium"]["environment"]
    assert any(str(e).startswith("FABULOUSA_URL=") for e in env)


# ---------------------------------------------------------------------------
# FLOW-022: ChronosSphere schedules the Basement -> Library promotion
# ---------------------------------------------------------------------------


@pytest.fixture
def cron_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("CRON_DB_PATH", str(tmp_path / "cron.db"))
    monkeypatch.setenv("INTERNAL_SECRET", "test-secret-value-not-default")
    worker = import_worker("cron_service_worker", REPO / "workers" / "cron-service" / "worker.py")
    worker.DB_PATH = tmp_path / "cron.db"
    worker.init_db()
    return worker


def _jobs(worker) -> dict[str, sqlite3.Row]:
    with worker.get_conn() as conn:
        rows = conn.execute("SELECT * FROM jobs").fetchall()
    return {row["id"]: row for row in rows}


def test_promotion_job_is_seeded(cron_worker):
    cron_worker.seed_default_jobs()
    job = _jobs(cron_worker)["basement-library-promotion"]

    assert job["enabled"] == 1
    assert job["method"] == "POST"
    assert "/basement/promote" in job["url"]
    # A schedule the parser cannot read is a job that never fires.
    assert len(job["schedule"].split()) == 5


def test_the_seeded_request_matches_the_endpoint_contract(cron_worker):
    """`/basement/promote` reads its arguments from the query string.

    Sending them as a JSON body is not a loud failure -- FastAPI just applies
    the defaults -- so a limit set here would silently not apply.
    """
    cron_worker.seed_default_jobs()
    job = _jobs(cron_worker)["basement-library-promotion"]

    assert "limit=500" in job["url"] and "dry_run=false" in job["url"]
    assert json.loads(job["payload"]) == {}


def test_the_job_carries_a_credential_reference_and_not_a_secret(cron_worker):
    """The jobs table is an operator-readable schedule, not a secret store."""
    cron_worker.seed_default_jobs()
    headers = json.loads(_jobs(cron_worker)["basement-library-promotion"]["headers"])

    assert headers["X-Internal-Secret"] == "${INTERNAL_SECRET}"


def test_a_changed_deployment_address_reaches_an_already_seeded_row(cron_worker):
    """`INSERT OR IGNORE` alone would freeze the URL at first-run values."""
    cron_worker.seed_default_jobs()
    with cron_worker.get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET url='http://gone:8000/basement/promote', enabled=0 "
            "WHERE id='basement-library-promotion'"
        )
        conn.commit()

    cron_worker.seed_default_jobs()  # restart

    job = _jobs(cron_worker)["basement-library-promotion"]
    assert "gone" not in job["url"]
    # The operator's decision to switch it off is not deployment-owned.
    assert job["enabled"] == 0


def test_an_unset_credential_raises_instead_of_posting_unauthenticated(cron_worker, monkeypatch):
    """The failure mode this whole flow exists to avoid.

    An unauthenticated POST would come back 401 and be recorded as an HTTP
    failure, which reads like the Basement is broken. A missing environment
    variable should say that it is missing.
    """
    monkeypatch.delenv("INTERNAL_SECRET", raising=False)
    with pytest.raises(cron_worker.MissingCredential) as exc:
        cron_worker._resolve_header_references({"X-Internal-Secret": "${INTERNAL_SECRET}"})
    assert "INTERNAL_SECRET" in str(exc.value)


def test_a_configured_credential_is_substituted(cron_worker, monkeypatch):
    monkeypatch.setenv("INTERNAL_SECRET", "s3cret")
    resolved = cron_worker._resolve_header_references(
        {"X-Internal-Secret": "${INTERNAL_SECRET}", "Accept": "application/json"}
    )
    assert resolved == {"X-Internal-Secret": "s3cret", "Accept": "application/json"}


def test_disabling_the_seeded_job_survives_a_restart(cron_worker):
    """The documented way to switch a standing job off."""
    cron_worker.seed_default_jobs()
    with cron_worker.get_conn() as conn:
        conn.execute("UPDATE jobs SET enabled=0 WHERE id='basement-library-promotion'")
        conn.commit()

    cron_worker.seed_default_jobs()  # restart

    assert _jobs(cron_worker)["basement-library-promotion"]["enabled"] == 0


def test_deleting_the_seeded_job_lets_it_return(cron_worker):
    """Deletion means "remove this row", not "the platform should stop"."""
    cron_worker.seed_default_jobs()
    with cron_worker.get_conn() as conn:
        conn.execute("DELETE FROM jobs WHERE id='basement-library-promotion'")
        conn.commit()
    assert "basement-library-promotion" not in _jobs(cron_worker)

    cron_worker.seed_default_jobs()

    assert "basement-library-promotion" in _jobs(cron_worker)


def test_seeding_twice_does_not_duplicate(cron_worker):
    cron_worker.seed_default_jobs()
    cron_worker.seed_default_jobs()
    with cron_worker.get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE id='basement-library-promotion'"
        ).fetchone()[0]
    assert count == 1


def test_imaginarium_project_queries_are_literal_and_filter_correctly():
    """Four filter combinations, four literal queries, exercised against real SQLite.

    Removing the f-string only matters if the replacement still filters. This
    seeds a table and checks each combination returns the right rows, so a
    mis-copied WHERE clause in the lookup fails here rather than silently
    returning everything.
    """
    worker = import_worker("imaginarium_worker", REPO / "workers" / "imaginarium" / "worker.py")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, status TEXT, project_type TEXT)")
    conn.executemany(
        "INSERT INTO projects (status, project_type) VALUES (?,?)",
        [
            ("pending", "brand"),
            ("completed", "brand"),
            ("pending", "mixed"),
        ],
    )

    cases = {
        (None, None): 3,
        ("pending", None): 2,
        (None, "brand"): 2,
        ("pending", "brand"): 1,
    }
    for (status, project_type), expected in cases.items():
        count_sql, rows_sql, params = worker._project_queries(status, project_type)
        assert "{" not in count_sql and "{" not in rows_sql
        assert conn.execute(count_sql, params).fetchone()[0] == expected
        rows = conn.execute(rows_sql, [*params, 50, 0]).fetchall()
        assert len(rows) == expected

    conn.close()


def test_reporter_rejects_a_non_http_endpoint(tmp_path, chaos_party):
    """`urlopen` honours file: and ftp: too; CHAOS_PARTY_URL is not a literal."""
    _, stub = chaos_party
    target = tmp_path / "secret.txt"
    target.write_text("do not read me", encoding="utf-8")

    proc = _run_reporter(
        _results_file(tmp_path, ROWS),
        {"CHAOS_PARTY_URL": f"file://{target}", "INTERNAL_SECRET": "s"},
    )

    assert proc.returncode == 2
    assert "http(s)" in proc.stderr
    assert stub.received == []


def test_reporter_accepts_https():
    """The guard must not reject the scheme the deployed worker actually uses."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("chaos_reporter", REPORTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.batch_endpoint("https://chaos.example/") == "https://chaos.example/runs/batch"
    assert module.batch_endpoint("http://chaos-party:8079") == "http://chaos-party:8079/runs/batch"
    for bad in ("file:///etc/passwd", "ftp://host/x", "chaos-party:8079", ""):
        with pytest.raises(ValueError):
            module.batch_endpoint(bad)
