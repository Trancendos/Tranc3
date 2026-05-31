"""
Root conftest.py — shared fixtures, logging config, and environment setup.

Sets SECRET_KEY before any test module is collected so test_api.py's module-level
guard has a value. All test files get structured logging via pytest's caplog.
"""

from __future__ import annotations

import json
import logging
import os
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

# ── Worker SQLite DB paths ───────────────────────────────────────────────────
# Some workers default their SQLite path to `/data/<name>.db` (a volume mount in
# production). Tests import these worker modules directly, which instantiates the
# DB at import time — and `/data` is not writable in CI/dev. Point each
# env-configurable path at a writable temp dir so collection never fails.
_WORKER_DATA_DIR = os.environ.get("TRANC3_TEST_DATA_DIR") or tempfile.mkdtemp(
    prefix="tranc3-test-data-"
)
os.environ["TRANC3_TEST_DATA_DIR"] = _WORKER_DATA_DIR
for _var, _fname in (
    ("USERS_DB_PATH", "users.db"),
    ("AUTH_DATABASE_PATH", "auth.db"),
):
    os.environ[_var] = os.environ.get(_var) or os.path.join(_WORKER_DATA_DIR, _fname)

# STORAGE_ROOT defaults to /mnt/data/tranc3 (a NAS mount in production) which is
# not writable in CI/dev. Point it at the writable temp dir for tests.
os.environ["STORAGE_ROOT"] = os.environ.get("STORAGE_ROOT") or os.path.join(
    _WORKER_DATA_DIR, "storage"
)

# ── Configure root test logger ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-8s] %(name)s -- %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
_log = logging.getLogger("tranc3.tests")


# ── JSON test-result log ──────────────────────────────────────────────────────


class _TestResultLogger:
    """Appends one JSON line per test to logs/test_results.jsonl."""

    def __init__(self, path: str = "logs/test_results.jsonl") -> None:
        os.makedirs("logs", exist_ok=True)
        self._path = path

    def record(self, name: str, outcome: str, duration_ms: float, reason: str = "") -> None:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "test": name,
            "outcome": outcome,
            "duration_ms": round(duration_ms, 2),
            "reason": reason,
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
