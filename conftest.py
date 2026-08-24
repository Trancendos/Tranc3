"""
Root conftest.py — shared fixtures, logging config, and environment setup.

Sets SECRET_KEY before any test module is collected so test_api.py's module-level
guard has a value. All test files get structured logging via pytest's caplog.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time

import pytest

# ── Set critical env vars before any test module is imported ─────────────────
# Use `or` fallback (not setdefault) so that CI passing empty strings is safe.
for _var, _default in (
    ("SECRET_KEY", "tranc3-test-secret-key-do-not-use-in-production"),
    ("JWT_SECRET", "tranc3-test-jwt-secret-do-not-use-in-production"),
    ("DATABASE_URL", "sqlite:///./test.db"),
    ("REDIS_URL", "redis://localhost:6379/0"),
    ("MASTER_KEY_SEED", "tranc3-test-master-key-seed-do-not-use-in-prod"),
    ("INTERNAL_SECRET", "tranc3-test-internal-secret-do-not-use-in-prod"),
):
    os.environ[_var] = os.environ.get(_var) or _default

# ── Disable non-essential observability instrumentation for tests ───────────
# src.observability.worker_setup.instrument_worker() registers Prometheus
# metrics into prometheus_client's process-wide default CollectorRegistry,
# which persists across the whole pytest process — unlike the FastAPI `app`
# instances it's guarding against re-instrumenting. Any worker re-imported
# fresh more than once in the same process (a common test-harness pattern,
# e.g. tests/_worker_import_utils.import_worker) hits
# "ValueError: Duplicated timeseries in CollectorRegistry" on the second
# import. OTel's OTLP exporter also spends the whole run retrying a
# nonexistent otel-collector:4317. Neither is needed for unit tests.
os.environ["PROMETHEUS_ENABLED"] = os.environ.get("PROMETHEUS_ENABLED") or "false"
os.environ["OTEL_ENABLED"] = os.environ.get("OTEL_ENABLED") or "false"

# ── Redirect worker SQLite databases to a writable temp dir ──────────────────
# Several workers default their DB path to "/data/..." (the production Docker
# volume mount). That directory does not exist / is not writable in CI or local
# test runs, so module-level `db = SomeDatabase()` instantiation would crash at
# import time. Point every known worker DB-path env var at a per-run temp dir.
_WORKER_DATA_DIR = os.environ.get("TRANC3_TEST_DATA_DIR") or tempfile.mkdtemp(
    prefix="tranc3-test-data-"
)
os.makedirs(_WORKER_DATA_DIR, exist_ok=True)
os.environ.setdefault("TRANC3_TEST_DATA_DIR", _WORKER_DATA_DIR)

for _db_var, _db_file in (
    ("AUTH_DATABASE_PATH", "auth.db"),
    ("USERS_DATABASE_PATH", "users.db"),
    ("BENCHMARK_DB_PATH", "benchmark.db"),
    ("GATEWAY_DB_PATH", "gateway.db"),
    ("INFINITY_ADMIN_DB_PATH", "infinity_admin.db"),
    ("INFINITY_ONE_DB_PATH", "infinity_one.db"),
    ("INFINITY_PORTAL_DB_PATH", "infinity_portal.db"),
    ("LANGCHAIN_DB_PATH", "langchain.db"),
    ("LEDGER_DB_PATH", "ledger.db"),
    ("MODEL_ROUTER_DB_PATH", "model_router.db"),
    ("SENTINEL_DB_PATH", "sentinel.db"),
    ("TOPOLOGY_DB_PATH", "topology.db"),
    ("VAULT_DB_PATH", "vault.db"),
    ("WORKFLOW_DB_PATH", "workflow.db"),
    ("GBRAIN_DB_PATH", "gbrain.db"),
    ("KNOWLEDGE_DB_PATH", "knowledge.db"),
):
    os.environ[_db_var] = os.environ.get(_db_var) or os.path.join(_WORKER_DATA_DIR, _db_file)

# ── Configure root test logger ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-8s] %(name)s -- %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
_log = logging.getLogger("tranc3.tests")


# ── JSON test-result log ──────────────────────────────────────────────────────


def _current_commit() -> str:
    """The commit under test, for correlating results across runs.

    Without this, "flaky" cannot be distinguished from "fixed": a test that
    failed yesterday and passes today looks identical to one that alternates
    on the same code. scripts/test_intelligence.py only calls a test flaky
    when it disagrees with itself at a SINGLE commit, which needs this field.

    CI provides the SHA in the environment; locally we ask git. Unknown is a
    valid answer -- it degrades flaky detection to a weaker signal rather than
    producing a false one.
    """
    for var in ("GITHUB_SHA", "FORGEJO_SHA", "CI_COMMIT_SHA"):
        sha = os.environ.get(var, "").strip()
        if sha:
            return sha[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()[:12]
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


class _TestResultLogger:
    """Appends one JSON line per test to logs/test_results.jsonl."""

    def __init__(self, path: str = "logs/test_results.jsonl") -> None:
        os.makedirs("logs", exist_ok=True)
        self._path = path
        # Resolved once: a subprocess per test would dominate the runtime of
        # the fast suites, and the commit cannot change mid-session anyway.
        self._commit = _current_commit()
        self._run_id = f"{int(time.time())}-{os.getpid()}"

    def record(self, name: str, outcome: str, duration_ms: float, reason: str = "") -> None:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "test": name,
            "outcome": outcome,
            "duration_ms": round(duration_ms, 2),
            "reason": reason,
            "commit": self._commit,
            "run_id": self._run_id,
        }
        with open(self._path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        _log.debug("test_result %s=%s (%.1fms)", name, outcome, duration_ms)


_result_logger = _TestResultLogger()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        duration_ms = (rep.duration or 0) * 1000
        _result_logger.record(
            name=item.nodeid,
            outcome=rep.outcome,  # passed / failed / skipped
            duration_ms=duration_ms,
            reason=str(rep.longrepr) if rep.failed else "",
        )


# ── Guard: shared auth env vars must not be mutated mid-session ──────────────
# Several modules capture these into a module-level constant at *their* import
# time (e.g. src/compliance/waivers_routes.py's _INTERNAL_SECRET). If one test
# module reassigns the env var without restoring it, whether any other module
# saw the real value comes down to collection order — which produces failures
# that reproduce only in a full-suite run and pass in isolation, the most
# expensive kind to debug. tests/test_vrar3d_viewer.py did exactly this and
# broke every authenticated waiver route for a whole run.
#
# This fails the offending test loudly and names the variable, instead of
# letting the damage surface as an unrelated 403 several hundred tests later.
# Use monkeypatch.setenv (auto-restoring) or read the existing value; if a
# module genuinely must reassign one of these, save and restore it the way
# tests/test_analytics_service.py does.
# Scoped to the module, not the test: a module-scoped fixture that overrides one
# of these for its own tests and restores afterwards (as
# tests/test_analytics_service.py does, deliberately and with a comment
# explaining why) is legitimate and must not trip this. What is never
# legitimate is a module *finishing* with the value still changed, because from
# that point on every later import sees the wrong one.
_GUARDED_ENV_VARS = ("INTERNAL_SECRET", "SECRET_KEY", "JWT_SECRET", "MASTER_KEY_SEED")
_env_baseline = {name: os.environ.get(name) for name in _GUARDED_ENV_VARS}


@pytest.fixture(scope="module", autouse=True)
def _assert_shared_env_unchanged(request):
    yield
    drifted = [
        f"{name}: {_env_baseline[name]!r} -> {os.environ.get(name)!r}"
        for name in _GUARDED_ENV_VARS
        if os.environ.get(name) != _env_baseline[name]
    ]
    if drifted:
        # Restore before failing so the rest of the run is not also poisoned.
        for name in _GUARDED_ENV_VARS:
            if _env_baseline[name] is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = _env_baseline[name]
        raise AssertionError(
            f"{getattr(request.module, '__name__', '?')} left a shared auth env var "
            "changed. Later-imported modules capture these into module-level "
            "constants, so this makes unrelated tests fail depending on collection "
            "order:\n  " + "\n  ".join(drifted) + "\nUse monkeypatch.setenv, or "
            "save/restore around the change."
        )


# ── Shared sample data fixtures ───────────────────────────────────────────────


@pytest.fixture(scope="session")
def sample_workflow_definitions():
    """Pre-built WorkflowDefinition instances for use across all test suites."""
    from src.workflow.builder import WorkflowBuilder
    from src.workflow.nodes import NodeType

    results = {}

    # Minimal single-node workflow
    b = WorkflowBuilder("sample-single-output")
    b.add_node(NodeType.OUTPUT, "out", config={"keys": ["result"]}, node_id="out")
    results["single_output"] = b.build()

    # Two-node linear chain
    b = WorkflowBuilder("sample-linear")
    t = b.add_node(NodeType.TRIGGER, "start", config={}, node_id="trigger")
    o = b.add_node(NodeType.OUTPUT, "end", config={}, node_id="output")
    b.connect(t, o)
    results["linear"] = b.build()

    # Three-node with SparkToolNode
    b = WorkflowBuilder("sample-spark-pipeline")
    t = b.add_node(NodeType.TRIGGER, "start", config={}, node_id="trigger")
    s = b.add_node(
        NodeType.SPARK_TOOL,
        "call",
        config={"tool_name": "get_system_health", "args": {"subsystems": []}},
        node_id="spark",
    )
    o = b.add_node(NodeType.OUTPUT, "end", config={}, node_id="output")
    b.connect(t, s).connect(s, o)
    results["spark_pipeline"] = b.build()

    return results


@pytest.fixture(scope="session")
def sample_spark_tools():
    """Reusable SparkTool definitions for tests that need live tool instances."""
    from src.mcp.tools import SparkTool

    async def echo(params):
        return {"echo": params.get("text", ""), "ts": time.time()}

    async def add(params):
        return {"result": params.get("a", 0) + params.get("b", 0)}

    async def fail(params):
        raise RuntimeError("deliberate test failure")

    return {
        "echo": SparkTool(
            name="test_echo",
            description="Echo input text",
            input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
            handler=echo,
            category="test",
        ),
        "add": SparkTool(
            name="test_add",
            description="Add two numbers",
            input_schema={
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
            },
            handler=add,
            category="test",
        ),
        "fail": SparkTool(
            name="test_fail",
            description="Always raises an error",
            input_schema={"type": "object", "properties": {}},
            handler=fail,
            category="test",
        ),
    }


@pytest.fixture(scope="session")
def sample_error_payloads():
    """Malicious / edge-case payloads for penetration and validation tests."""
    null = chr(0)
    return {
        "sql_injection": ["' OR '1'='1", "'; DROP TABLE users;--", "1; SELECT * FROM secrets"],
        "path_traversal": ["../../../etc/passwd", "..\\..\\windows\\system32", "%2e%2e%2f"],
        "xss": [
            "<script>alert(1)</script>",
            '"><img src=x onerror=alert(1)>',
            "javascript:alert(1)",
        ],
        "command_injection": ["; ls -la", "| cat /etc/passwd", "`id`", "$(whoami)"],
        "null_bytes": [null + "admin", "test" + null + "injection", null * 3],
        "oversized": ["A" * 100_001, "B" * 1_000_000],
        "unicode_tricks": ["​", "�", "‮" + "txt.exe", "admin​"],
        "json_injection": ['{"__proto__": {"admin": true}}', '{"constructor": {"prototype": {}}}'],
        "empty": ["", "   ", "\t\n"],
    }


@pytest.fixture(scope="session")
def spark_registry():
    """A clean SparkToolRegistry for integration tests."""
    from src.mcp.tools import SparkToolRegistry

    return SparkToolRegistry()


@pytest.fixture(scope="session")
def grid_executor():
    """A fresh WorkflowExecutor."""
    from src.workflow.executor import WorkflowExecutor

    return WorkflowExecutor()
