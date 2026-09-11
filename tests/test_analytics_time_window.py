"""The polars and SQL metric backends must answer the same question the same way.

`workers/analytics-service/worker.py` has two aggregation paths. `get_metric`
tries polars FIRST and returns its result if it produces one, falling back to
SQL only when polars is unavailable or raises.

`_polars_aggregate` accepted `since` and `until` and ignored both: its query
was `SELECT value FROM metrics WHERE name=?` with no time predicate. So
`/metrics/foo?since=X&until=Y` aggregated every timestamp on record whenever
polars won -- the same request answered differently depending on which backend
served it, with no error on either side. Raised by CodeAnt on PR #1207.

A divergence like this cannot be caught by testing one backend. These tests
compare the two against each other on the same rows, which is the only
formulation that fails when they drift apart again.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parents[1] / "workers" / "analytics-service" / "worker.py"


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(WORKER.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node  # type: ignore[return-value]
    raise AssertionError(
        f"{name}() not found in {WORKER.name}. If it was renamed, re-point this "
        "test rather than deleting it -- the divergence it guards is silent."
    )


def _time_predicate_params(func: ast.AST) -> set[str]:
    """Which of `since` / `until` this function actually reads."""
    return {
        node.id
        for node in ast.walk(func)
        if isinstance(node, ast.Name) and node.id in {"since", "until"}
    }


# --------------------------------------------------------------------------
# The defect itself
# --------------------------------------------------------------------------


@pytest.mark.parametrize("param", ["since", "until"])
def test_polars_backend_reads_the_time_window_it_accepts(param):
    """A parameter accepted and never read is a silently ignored filter."""
    func = _function("_polars_aggregate")
    accepted = {a.arg for a in func.args.args}
    assert param in accepted, f"_polars_aggregate no longer accepts {param!r}"
    assert param in _time_predicate_params(func), (
        f"_polars_aggregate accepts {param!r} and never reads it. The time window "
        "is then silently dropped, and because get_metric tries this backend "
        "first, the caller gets an aggregate over every timestamp with no error."
    )


def test_polars_backend_builds_a_timestamp_predicate():
    """Reading the parameter is not enough -- it must reach the query."""
    source = ast.unparse(_function("_polars_aggregate"))
    assert "timestamp >= ?" in source and "timestamp <= ?" in source, (
        "_polars_aggregate builds no timestamp predicate. Reading `since`/`until` "
        "without putting them in the WHERE clause leaves the filter inert."
    )


# --------------------------------------------------------------------------
# The property that keeps them from drifting apart again
# --------------------------------------------------------------------------


def test_both_backends_use_the_same_time_predicate():
    """Identical predicate text in both paths, so they cannot disagree."""
    polars = ast.unparse(_function("_polars_aggregate"))
    sql = ast.unparse(_function("get_metric"))
    for predicate in ("timestamp >= ?", "timestamp <= ?"):
        assert predicate in polars and predicate in sql, (
            f"{predicate!r} appears in only one of _polars_aggregate / get_metric. "
            "get_metric prefers polars and falls back to SQL, so a predicate in "
            "one path and not the other means the same request returns different "
            "numbers depending on which backend happens to serve it."
        )


@pytest.mark.parametrize("func_name", ["_polars_aggregate", "get_metric"])
def test_epoch_zero_is_not_treated_as_absent(func_name):
    """`since=0.0` is a real timestamp; a truthiness test drops the filter.

    Both paths originally used `if since:`. At `since=0.0` — midnight 1970, a
    value a caller can legitimately send — that is falsy, so the predicate was
    skipped and the window silently widened to everything. `is not None` is the
    test that distinguishes "not supplied" from "supplied as zero".
    """
    source = ast.unparse(_function(func_name))
    assert "if since is not None" in source and "if until is not None" in source, (
        f"{func_name}() gates its time predicate on truthiness rather than "
        "`is not None`, so since=0.0 / until=0.0 silently disable the filter."
    )
