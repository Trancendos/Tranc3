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


def test_polars_backend_builds_a_timestamp_predicate(worker):
    """Reading the parameter is not enough -- it must reach the query."""
    assert "timestamp >= ?" in worker._METRIC_WINDOW, worker._METRIC_WINDOW
    assert "timestamp <= ?" in worker._METRIC_WINDOW, worker._METRIC_WINDOW
    source = ast.unparse(_function("_polars_aggregate"))
    assert "_METRIC_VALUES_SQL" in source and "_window(" in source, (
        "_polars_aggregate no longer runs the shared windowed statement. Reading "
        "`since`/`until` without putting them in the WHERE clause leaves the "
        "filter inert, which is the original defect."
    )


# --------------------------------------------------------------------------
# The property that keeps them from drifting apart again
# --------------------------------------------------------------------------


def test_both_backends_use_the_same_time_predicate(worker):
    """Not merely identical text in both paths -- literally the same string.

    The first version of this test compared the predicate text found in each
    function body. That caught a drift but could not prevent one: two copies of
    `timestamp >= ?` satisfy it, and two copies can be edited apart. Every
    statement is now built from one `_METRIC_WINDOW` constant, so the two paths
    cannot disagree without someone deleting the constant -- which this test
    also notices.
    """
    for sql in [worker._METRIC_VALUES_SQL, *worker._METRIC_SQL.values()]:
        assert sql.endswith(worker._METRIC_WINDOW), sql
    for sql in worker._TIMESERIES_SQL.values():
        assert worker._METRIC_WINDOW in sql, sql

    for func_name in ("_polars_aggregate", "get_metric", "metric_timeseries"):
        source = ast.unparse(_function(func_name))
        assert "_window(" in source, (
            f"{func_name} no longer resolves its bounds through _window(). "
            "get_metric prefers polars and falls back to SQL, so a window "
            "resolved differently in one path means the same request returns "
            "different numbers depending on which backend happens to serve it."
        )


def test_no_metric_query_is_assembled_by_interpolation():
    """The statements are fixed strings; only values are bound.

    The predicate used to be joined from a clause list and interpolated with an
    f-string. It was not injectable -- literal clauses, bound values -- but a
    reader (human or SAST) cannot tell that from the call site. Raised by
    Sourcery as a blocking finding on PR #1242.
    """
    for func_name in ("_polars_aggregate", "get_metric", "metric_timeseries"):
        tree = _function(func_name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "execute":
                statement = node.args[0] if node.args else None
                assert not isinstance(statement, ast.JoinedStr), (
                    f"{func_name} passes an f-string to execute(); metric queries "
                    "are fixed statements with bound parameters."
                )


def test_epoch_zero_is_not_treated_as_absent(worker):
    """`since=0.0` is a real timestamp; a truthiness test drops the filter.

    All three paths originally used `if since:`. At `since=0.0` -- midnight
    1970, a value a caller can legitimately send -- that is falsy, so the
    predicate was skipped and the window silently widened to everything. The
    distinction now lives in one place, `_window`, which is also why
    `metric_timeseries` can no longer keep the old form after the other two are
    fixed: there is only one form left.
    """
    source = ast.unparse(_function("_window"))
    assert "is not None" in source, source
    assert worker._window(0.0, None)[0] == 0.0, "since=0.0 was treated as absent"
    assert worker._window(None, 0.0)[1] == 0.0, "until=0.0 was treated as absent"
    assert worker._window(None, None) == (worker._EPOCH_FLOOR, worker._EPOCH_CEIL)


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


def _polars_result(module, *args):
    """The aggregate only; _polars_aggregate returns (result, samples)."""
    aggregated = module._polars_aggregate(*args)
    return None if aggregated is None else aggregated[0]


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
        polars_result = _polars_result(worker, "cpu", agg, since, until)
        sql_result = _sql_result(worker, name="cpu", agg=agg, since=since, until=until)
        assert polars_result == sql_result, (
            f"backends disagree for agg={agg} since={since} until={until}: "
            f"polars={polars_result}, sql={sql_result}"
        )

    def test_both_backends_return_the_same_response_shape(self, worker):
        """Same keys whichever backend wins, not just the same number.

        The SQL branch has always returned `samples`; the polars branch never
        did, so a caller reading it saw the field appear and disappear with
        whichever backend happened to serve the request. Making the polars
        branch return 0 for an empty `count` window widened that -- it started
        winning in a case where it previously fell through to SQL. Raised by
        CodeAnt on PR #1242. Agreeing on the number is not agreeing.
        """
        import unittest.mock as mock

        _seed(worker, self.ROWS)
        with mock.patch.object(worker, "_select_backend", return_value="polars"):
            via_polars = worker.get_metric(name="cpu", agg="count", since=500.0, until=None)
            with mock.patch.object(worker, "_polars_aggregate", return_value=None):
                via_sql = worker.get_metric(name="cpu", agg="count", since=500.0, until=None)

        assert set(via_polars) == set(via_sql), (
            f"response shape differs by backend: polars={sorted(via_polars)}, sql={sorted(via_sql)}"
        )
        assert via_polars["result"] == via_sql["result"]
        assert via_polars["samples"] == via_sql["samples"] == 0

    def test_the_window_actually_narrows(self, worker):
        """Guard against both backends agreeing by both ignoring the window."""
        _seed(worker, self.ROWS)
        unbounded = _polars_result(worker, "cpu", "sum", None, None)
        bounded = _polars_result(worker, "cpu", "sum", 200.0, 300.0)
        assert unbounded == 100.0, unbounded
        assert bounded == 50.0, (
            f"expected only the 20.0 and 30.0 rows in [200, 300], got sum={bounded} "
            "-- the time window is being ignored, which is the original defect."
        )

    def test_a_backend_that_ignored_the_window_would_be_caught(self, worker):
        """Probe: the comparison fails when one side drops the predicate."""
        _seed(worker, self.ROWS)
        windowed = _polars_result(worker, "cpu", "sum", 200.0, 300.0)
        unwindowed = _polars_result(worker, "cpu", "sum", None, None)
        assert windowed != unwindowed, (
            "windowed and unwindowed sums are equal on this fixture, so the "
            "comparison above could pass with a broken backend"
        )
