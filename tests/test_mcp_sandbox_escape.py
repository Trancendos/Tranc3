"""The MCP code sandbox must refuse reflection, and be shown refusing it.

Measured on main at 2026-10-06, before the fix these tests pin: a snippet run
through `execute_code` reached `subprocess.Popen` via the object subclass
graph. That is arbitrary command execution from inside a tool advertised as a
sandbox.

The reason this file exists rather than a one-line allowlist change is that the
proposed fix did not work. #1366 removed `dir`, `getattr` and `type` from
`_SAFE_BUILTINS` under the title "[CRITICAL] Fix sandbox escape vulnerability",
and the escape survives it untouched, because the shortest chain uses no
builtin at all:

    ().__class__.__mro__[-1].__subclasses__()

Both chains are asserted here. The second is the regression test that the
builtin removal alone would have passed while leaving the sandbox open.
"""

from __future__ import annotations

import asyncio

from src.mcp.tools import _SAFE_BUILTINS, _reflection_refusal

#: Reaches the object graph using the reflection builtins. This is the chain
#: #1366 identified, and removing those builtins does block it.
_BUILTIN_CHAIN = 'cls = type("x", (), {})\nbase = cls.__mro__[-1]\nbase.__subclasses__()'

#: REGRESSION: reaches the same graph with no builtin whatsoever -- attribute
#: access on a literal. This is what the builtin removal missed.
_BUILTIN_FREE_CHAIN = "().__class__.__mro__[-1].__subclasses__()"


def test_the_reflection_builtins_are_not_in_the_allowlist():
    """#1366's contribution, kept as the second layer rather than the only one."""
    for name in ("dir", "getattr", "type"):
        assert name not in _SAFE_BUILTINS, f"{name} reaches the object graph"


def test_the_builtin_chain_is_refused():
    refusal = _reflection_refusal(_BUILTIN_CHAIN)
    assert refusal is not None
    assert "__mro__" in refusal


def test_the_builtin_free_chain_is_refused():
    """REGRESSION: removing dir/getattr/type does not close this one.

    Measured against the allowlist with those three already removed: the chain
    still returned `subprocess.Popen` out of 572 subclasses. A fix that only
    edits the allowlist ships a sandbox-escape headline and an open sandbox.
    """
    refusal = _reflection_refusal(_BUILTIN_FREE_CHAIN)
    assert refusal is not None, "the chain needing no builtin must still be refused"
    # `ast.walk` is breadth-first, so the outermost attribute is reported
    # first -- `__subclasses__`, not the `__class__` the chain starts from.
    # Asserting the specific name here is what caught that; the property
    # that matters is that SOME dunder in the chain is named.
    assert "__subclasses__" in refusal, refusal


def test_a_dunder_name_is_refused_not_only_a_dunder_attribute():
    assert _reflection_refusal("x = __builtins__") is not None


def test_ordinary_snippets_are_untouched():
    """The gate must cost nothing to code that is not trying to escape."""
    for snippet in (
        "y = 1 + 2",
        "z = sorted([3, 1, 2])\nz",
        "total = sum(len(s) for s in ['ab', 'cde'])\ntotal",
        "d = {'k': 1}\nd['k'] + 1",
        "_private = 5\n_private",
    ):
        assert _reflection_refusal(snippet) is None, snippet


def test_unparseable_code_raises_rather_than_passing_through():
    """A snippet the gate cannot read is the caller's error, not an allowance."""
    try:
        _reflection_refusal("def (")
    except SyntaxError:
        return
    raise AssertionError("unparseable code must not be reported as clean")


def test_popen_is_not_reachable_through_the_handler():
    """End-to-end: the escape is refused by the tool, not merely by the helper."""
    from src.mcp.tools import SparkToolRegistry

    registry = SparkToolRegistry()
    result = asyncio.run(
        registry._handle_execute_code(
            {"__admin__": True, "code": _BUILTIN_FREE_CHAIN, "timeout_seconds": 5}
        )
    )
    assert "error" in result, result
    assert "reflection" in result["error"], result["error"]


def test_the_handler_still_runs_ordinary_code():
    from src.mcp.tools import SparkToolRegistry

    registry = SparkToolRegistry()
    result = asyncio.run(
        registry._handle_execute_code(
            {"__admin__": True, "code": "a = 6 * 7\na", "timeout_seconds": 5}
        )
    )
    assert result.get("error") is None, result
    assert result.get("return_value") == 42, result
