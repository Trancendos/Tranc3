"""Queries that interpolate caller-supplied text, and the guards that stop them.

Aikido raised "Potential SQL injection via string-based query concatenation"
(PR #1162) against two places. One finding was real, one was not, and the
proposed fix for the one that was not would have broken the endpoint it
touched. These tests pin all three facts so the distinction survives.

WHAT WAS REAL

`Dimensional/architecture/smart_storage.py` built two Cosmos DB queries by
f-string interpolation of a caller-supplied `prefix` / `path`. Cosmos DB's SQL
API is a query language, so closing the quote and appending a clause is
injection in the ordinary sense even though the store is not relational. Both
are now bound parameters.

WHAT WAS NOT

`workers/rate-limit-service/worker.py` interpolates COLUMN NAMES into an
UPDATE. The values were already bound. The names come from
`PolicyUpdate.model_dump()`, which can only return that model's own fields, so
no caller could ever reach the interpolation with anything else.

The proposed fix added `re.match(r"^[a-zA-Z0-9_]+$", str(k))` to a module that
does not import `re` -- a NameError on every successful policy update, i.e. a
fix that took a working endpoint down to defend against an unreachable attack.
It also used `re.match` with `$`, which accepts a trailing newline.

The guard kept here is neither: the permitted names are read from the model
itself, so the check cannot drift from the thing it is checking.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SMART_STORAGE = ROOT / "Dimensional" / "architecture" / "smart_storage.py"
RATE_LIMIT = ROOT / "workers" / "rate-limit-service" / "worker.py"


# --------------------------------------------------------------------------
# The finding that was real: Cosmos DB query construction
# --------------------------------------------------------------------------


def _cosmos_query_assignments() -> list[ast.Assign]:
    """Every `query = ...` assignment in smart_storage.py."""
    tree = ast.parse(SMART_STORAGE.read_text())
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "query" for t in node.targets
        ):
            out.append(node)
    return out


def test_smart_storage_has_query_assignments_to_check():
    """Guard the guard: if the queries move or are renamed, this file must change too."""
    assert _cosmos_query_assignments(), (
        "No `query = ...` assignments found in smart_storage.py. The queries this "
        "module protects have moved; re-point these tests rather than deleting them."
    )


def _interpolation_kind(value: ast.expr) -> str | None:
    """Name the interpolation form, or None if the value is a plain constant.

    Checked f-strings ONLY at first, which named the test after a guarantee it
    did not make: `"... '" + prefix + "'"`, `"...{}".format(prefix)` and
    `"...%s" % prefix` are the same injection and all three would have passed.
    Raised by cubic on PR #1207.
    """
    if isinstance(value, ast.JoinedStr):
        return "f-string"
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
        return "+ concatenation"
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Mod):
        return "% formatting"
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr in {"format", "join"}
    ):
        return f".{value.func.attr}()"
    return None


def test_no_cosmos_query_is_built_by_interpolation():
    """No Cosmos query is built by ANY interpolation form, not just f-strings."""
    offenders = [
        (node.lineno, kind)
        for node in _cosmos_query_assignments()
        if (kind := _interpolation_kind(node.value)) is not None
    ]
    assert not offenders, (
        "smart_storage.py builds a Cosmos DB query by interpolation:\n"
        + "\n".join(f"  line {line}: {kind}" for line, kind in offenders)
        + "\nCaller-supplied text interpolated into query syntax is injection; bind "
        "it with `parameters=[{'name': '@x', 'value': x}]` instead."
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("query = f\"SELECT * FROM c WHERE id = '{path}'\"", "f-string"),
        ('query = "SELECT * FROM c WHERE id = \'" + path + "\'"', "+ concatenation"),
        ('query = "SELECT * FROM c WHERE id = {}".format(path)', ".format()"),
        ('query = "SELECT * FROM c WHERE id = %s" % path', "% formatting"),
        ('query = "SELECT c.id FROM c"', None),
        ('query = "SELECT c.id FROM c WHERE STARTSWITH(c.id, @prefix)"', None),
    ],
)
def test_interpolation_detector_catches_every_form(source, expected):
    """Probe the detector itself: each form it claims to catch, and two it must not.

    A guard for injection that only recognises one syntax is the kind of control
    this estate keeps finding -- present, running, and blind to the case that
    matters.
    """
    assigned = ast.parse(source).body[0]
    assert isinstance(assigned, ast.Assign)
    assert _interpolation_kind(assigned.value) == expected


def test_parameterised_queries_pass_their_parameters():
    """A query carrying an @placeholder must also pass `parameters=`.

    Binding is two halves and only one of them is visible at the call site: a
    query text that says `@prefix` and a call that forwards no `parameters=`
    raises at runtime, not at review. The rule is deliberately conditional --
    `SELECT VALUE SUM(c.size) FROM c` is a constant with nothing to bind, and
    demanding `parameters=None` on it would be ceremony rather than a check.
    """
    tree = ast.parse(SMART_STORAGE.read_text())
    checked = 0

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Every string this function assigns to `query`.
        texts = [
            n.value.value
            for n in ast.walk(func)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "query" for t in n.targets)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        ]
        if not any("@" in text for text in texts):
            continue  # nothing to bind in this function

        for call in ast.walk(func):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
                continue
            if call.func.attr != "query_items":
                continue
            checked += 1
            assert "parameters" in {kw.arg for kw in call.keywords}, (
                f"query_items() at line {call.lineno} is in a function whose query "
                f"text carries an @placeholder, but forwards no `parameters=`. "
                "Cosmos DB will reject the query at runtime."
            )

    assert checked, (
        "No parameterised query_items() call was found to check. Either the "
        "bindings were removed or the code moved; re-point this test."
    )


# --------------------------------------------------------------------------
# The finding that was not: rate-limit-service column names
# --------------------------------------------------------------------------


def test_rate_limit_worker_does_not_use_re_without_importing_it():
    """The proposed fix called `re.match` in a module with no `import re`.

    This is the general form: any name used at module scope must be bound.
    Pinning it here because the failure mode is a 500 on the success path,
    which no test of the *rejection* path would ever reach.
    """
    tree = ast.parse(RATE_LIMIT.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.asname or a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(a.asname or a.name for a in node.names)

    used_modules = {
        node.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }
    builtins_and_locals = used_modules - imported
    assert "re" not in builtins_and_locals, (
        "worker.py uses `re.<something>` but never imports `re`. That is a "
        "NameError at runtime, not a lint nit."
    )


def test_permitted_columns_are_read_from_the_model_not_restated():
    """The allowlist must come from PolicyUpdate, so it cannot drift from it."""
    source = RATE_LIMIT.read_text()
    assert "set(PolicyUpdate.model_fields)" in source, (
        "The update_policy column guard should derive permitted names from "
        "PolicyUpdate.model_fields. A hand-restated list is a second source of "
        "truth that goes stale the first time the model gains a field."
    )


def test_column_guard_refuses_with_a_client_error_not_a_crash():
    """Refusal must be an HTTPException; a bare ValueError is a 500."""
    source = RATE_LIMIT.read_text()
    start = source.find("unexpected = set(updates)")
    assert start != -1, (
        "The update_policy column guard was not found in worker.py. If it was "
        "renamed or moved, re-point this test rather than deleting it."
    )
    # Bound the window at the raise itself, not at a fixed character count: a
    # guard that grows past an arbitrary 400 chars would silently stop being
    # checked. Raised by cubic on PR #1207.
    raise_at = source.find("raise HTTPException(", start)
    assert raise_at != -1, (
        "The column guard does not raise HTTPException at all. Raising anything "
        "else inside a FastAPI handler surfaces as 500."
    )
    guard = source[start : raise_at + 200]
    assert "HTTPException" in guard and "status_code=400" in guard, (
        "The column guard must raise HTTPException(400). Raising ValueError "
        "inside a FastAPI handler surfaces as 500 Internal Server Error, which "
        "reports a caller mistake as a server fault."
    )


# --------------------------------------------------------------------------
# Why `fullmatch`, not `match` + `$` -- the reason the proposed regex was wrong
# --------------------------------------------------------------------------


@pytest.mark.parametrize("candidate", ["capacity\n", "refill_rate\n", "description\n"])
def test_match_with_dollar_accepts_a_trailing_newline(candidate):
    """Python's `$` matches before a final newline. `re.match` therefore accepts it.

    This is not a hypothetical: it is why the proposed
    `re.match(r"^[a-zA-Z0-9_]+$", ...)` would have passed a name carrying a
    trailing newline. Recorded as an executable fact rather than a comment,
    because it is the single most repeated mistake in this estate's validators.
    """
    assert re.match(r"^[a-zA-Z0-9_]+$", candidate) is not None
    assert re.fullmatch(r"[a-zA-Z0-9_]+", candidate) is None
