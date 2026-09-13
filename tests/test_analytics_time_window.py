"""The polars and SQL metric backends must answer the same question the same way.

`workers/analytics-service/worker.py` has two aggregation paths. `get_metric`
tries polars FIRST and returns its result if it produces one, falling back to
SQL only when polars is unavailable or raises.

`_polars_aggregate` accepted `since` and `until` and ignored both: its query
was `SELECT value FROM metrics WHERE name=?` with no time predicate. So
`/metrics/foo?since=X&until=Y` aggregated every timestamp on record whenever
polars won -- the same request answered differently depending on which backend
served it, with no error on either side. Raised by CodeAnt on PR #1207.

A divergence like this cannot be caught by testing one backend, so this file
holds the two backends against each other in two different ways:

* `TestBackendsAgreeOnTheSameRows` is behavioural. It writes known rows to a
  temporary SQLite file, runs BOTH backends over them with the same window, and
  compares the numbers. polars is not installed in this environment (it is a
  worker-level dependency), so a minimal stand-in supplies `pl.DataFrame`. That
  is not a shortcut around the real thing: the defect was in the SQL that selects
  the rows polars then aggregates, so the stub leaves the part that was broken
  fully under test and replaces only the arithmetic.

* The remaining tests are structural. They read the worker's AST and assert that
  each backend's predicate exists, is built from the parameter, and is spelled
  identically in both paths. These cannot observe a wrong number, but they fail
  on a drift that the behavioural test would only catch for the specific values
  it happens to use -- for example a `since:` truthiness check reappearing, which
  is wrong only at epoch zero.

An earlier version of this docstring claimed the whole file compared the backends
on the same rows when every test in it was AST-only. cubic caught that on PR
#1207; the behavioural half was written in response, rather than the sentence
being trimmed to fit.
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


@pytest.mark.parametrize("func_name", ["_polars_aggregate", "get_metric", "metric_timeseries"])
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


# --------------------------------------------------------------------------
# The behavioural half: both backends, same rows, compared
# --------------------------------------------------------------------------


class _StubSeries:
    """Just enough of a polars Series for _polars_aggregate's four aggregations."""

    def __init__(self, values):
        self._values = list(values)

    def mean(self):
        return sum(self._values) / len(self._values) if self._values else None

    def sum(self):
        return sum(self._values)

    def min(self):
        return min(self._values) if self._values else None

    def max(self):
        return max(self._values) if self._values else None


class _StubFrame:
    def __init__(self, data):
        self._data = {k: list(v) for k, v in data.items()}

    def __getitem__(self, key):
        return _StubSeries(self._data[key])

    def __len__(self):
        return len(next(iter(self._data.values()))) if self._data else 0


class _StubPolars:
    DataFrame = _StubFrame


@pytest.fixture()
def worker(tmp_path, monkeypatch):
    """Import the analytics worker against a temporary database.

    Imported by path because `workers/analytics-service` is not an importable
    package name (the hyphen), and ANALYTICS_DB_PATH is set before import so the
    module never touches the real /data path.
    """
    import importlib.util
    import sys

    monkeypatch.setenv("ANALYTICS_DB_PATH", str(tmp_path / "analytics.db"))
    monkeypatch.setitem(sys.modules, "polars", _StubPolars())

    spec = importlib.util.spec_from_file_location("_analytics_worker_under_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    # The worker creates its schema on the FastAPI startup event, which never
    # fires when the module is imported directly.
    module._init_db()
    return module


def _seed(module, rows):
    """rows: iterable of (name, value, timestamp)."""
    from datetime import datetime, timezone

    with module._db_conn() as c:
        for name, value, ts in rows:
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            c.execute(
                "INSERT INTO metrics (name, value, timestamp, date_str) VALUES (?, ?, ?, ?)",
                (name, value, ts, date_str),
            )
        c.commit()


def _sql_result(module, **kwargs):
    """get_metric's SQL answer, with the polars backend forced out of the way."""
    import unittest.mock as mock

    with mock.patch.object(module, "_polars_aggregate", return_value=None):
        return module.get_metric(**kwargs)["result"]


class TestBackendsAgreeOnTheSameRows:
    """The comparison the structural tests cannot make: actual numbers."""

    ROWS = [
        ("cpu", 10.0, 100.0),
        ("cpu", 20.0, 200.0),
        ("cpu", 30.0, 300.0),
        ("cpu", 40.0, 400.0),
        ("other", 999.0, 250.0),
    ]

    @pytest.mark.parametrize(
        "since,until",
        [
            (None, None),
            (200.0, None),
            (None, 300.0),
            (200.0, 300.0),
            (0.0, None),  # epoch zero: a real bound, not "unset"
            (500.0, None),  # window past every row
        ],
    )
    # `count` included deliberately: _polars_aggregate computes it through a
    # fallthrough branch (`float(len(df))`) that no structural test reaches, so
    # without it the one aggregation with its own code path was the one nothing
    # compared. Raised by cubic on PR #1207.
    @pytest.mark.parametrize("agg", ["avg", "sum", "min", "max", "count"])
    def test_polars_and_sql_return_the_same_number(self, worker, since, until, agg):
        _seed(worker, self.ROWS)
        polars_result = worker._polars_aggregate("cpu", agg, since, until)
        sql_result = _sql_result(worker, name="cpu", agg=agg, since=since, until=until)
        assert polars_result == sql_result, (
            f"backends disagree for agg={agg} since={since} until={until}: "
            f"polars={polars_result}, sql={sql_result}"
        )

    def test_the_window_actually_narrows(self, worker):
        """Guard against both backends agreeing by both ignoring the window."""
        _seed(worker, self.ROWS)
        unbounded = worker._polars_aggregate("cpu", "sum", None, None)
        bounded = worker._polars_aggregate("cpu", "sum", 200.0, 300.0)
        assert unbounded == 100.0, unbounded
        assert bounded == 50.0, (
            f"expected only the 20.0 and 30.0 rows in [200, 300], got sum={bounded} "
            "-- the time window is being ignored, which is the original defect."
        )

    def test_a_backend_that_ignored_the_window_would_be_caught(self, worker):
        """Probe: the comparison fails when one side drops the predicate."""
        _seed(worker, self.ROWS)
        windowed = worker._polars_aggregate("cpu", "sum", 200.0, 300.0)
        unwindowed = worker._polars_aggregate("cpu", "sum", None, None)
        assert windowed != unwindowed, (
            "windowed and unwindowed sums are equal on this fixture, so the "
            "comparison above could pass with a broken backend"
        )
