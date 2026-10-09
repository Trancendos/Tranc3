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

from src.mcp.tools import _DUNDER, _SAFE_BUILTINS, _reflection_refusal

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
    # The contract is that the refusal NAMES the offending construct, not that
    # it names a particular one. `ast.walk` is breadth-first, so the outermost
    # attribute is reported first -- `__subclasses__`, not the `__class__` the
    # chain starts from. Asserting the exact name is how that was found, and
    # pinning it would couple this test to walk order for no gain.
    assert _DUNDER in refusal, refusal


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


# ---------------------------------------------------------------------------
# Vectors raised in review on #1378, each measured before being closed.
#
# The PR originally claimed "no snippet may name a dunder". That was false, and
# the cases below are why: `str.format` resolves attribute access written
# inside the template, where no AST walk over names and attributes can see it.
# Measured on the branch before this fix: `"{0.__class__.__mro__}".format(())`
# passed the gate and the handler RETURNED `(<class 'tuple'>, <class 'object'>)`
# -- the object graph, reached by a snippet the gate had approved.
# ---------------------------------------------------------------------------

#: All three passed the gate before the fix. The second spells the dunder with
#: escapes to show the refusal is not matching the literal source text.
_FORMAT_CHAINS = (
    '"{0.__class__.__mro__}".format(())',
    '"{0.__class__}".format(())',
    '"{0.__class__}".format_map({0: ()})',
)


def test_format_templates_are_refused():
    """REGRESSION: the dunder lives in a string, invisible to the AST walk."""
    for chain in _FORMAT_CHAINS:
        refusal = _reflection_refusal(chain)
        assert refusal is not None, f"{chain!r} reached the object graph"


def test_a_dunder_replacement_field_is_refused_in_any_string():
    """A template built here and formatted elsewhere must not carry it out."""
    refusal = _reflection_refusal('template = "{0.__class__}"')
    assert refusal is not None
    assert "__class__" in refusal, refusal


def test_plain_formatting_is_refused_with_a_usable_alternative():
    """`.format` is refused wholesale, so the message has to say what to use."""
    refusal = _reflection_refusal('"{}".format(1)')
    assert refusal is not None
    assert "f-string" in refusal, refusal


def test_frame_attributes_are_refused():
    """Raised by sourcery: none of these is a dunder, so the dunder rule misses them.

    The specific chain reported (`gi_frame.f_back` up to the host's
    `f_builtins`) does not currently reach the host -- measured twice: a
    suspended generator's `f_back` is `None`. The attribute class is refused
    anyway, because "the chain happens to die one hop short" is not a boundary.
    """
    for chain in (
        "def f():\n    yield 1\n\ng = f()\ng.gi_frame.f_back",
        "import sys\n\nsys.exc_info()[2].tb_frame.f_builtins",
    ):
        refusal = _reflection_refusal(chain)
        assert refusal is not None, chain
        assert "frame attribute" in refusal, refusal


def test_strings_that_merely_look_like_templates_still_pass():
    """The gate must not refuse ordinary text that happens to use braces."""
    for snippet in ('s = "hello {name}"', 'f"{1 + 1}"', 'j = "{\\"a\\": 1}"'):
        assert _reflection_refusal(snippet) is None, snippet


def test_a_non_string_snippet_raises_rather_than_passing_through():
    """`ast.parse(None)` is a TypeError, which escaped the handler until #1378."""
    try:
        _reflection_refusal(None)  # type: ignore[arg-type]
    except TypeError:
        return
    raise AssertionError("a non-string snippet must not be reported as clean")


def test_a_pathologically_nested_snippet_raises_rather_than_passing_through():
    """Measured reproducer, not a hypothetical.

    Deep PARENTHESIS nesting is only a `SyntaxError` on CPython 3.11, so the
    obvious probe does not exercise this path. A long attribute chain does:
    `ast.parse("a" + ".b" * 5000)` exhausts the default 1000-frame limit.
    """
    try:
        _reflection_refusal("a" + ".b" * 5000)
    except RecursionError:
        return
    except SyntaxError:  # pragma: no cover - a stricter parser is also fine
        return
    raise AssertionError("a snippet the parser cannot read must not read as clean")


# ---------------------------------------------------------------------------
# The gate above only matters if reaching it requires authority. It did not.
#
# `tool_params` is the JSON-RPC request's own `arguments`, and
# `_handle_execute_code` decided admin by reading `__admin__` out of it. So the
# authorisation check's only input was the claim it existed to check. Measured
# end-to-end before the fix: `{"__admin__": true, "code": "a = 6*7\na"}` with no
# authenticated caller at all returned `{"return_value": 42}`, and the same call
# without the key was refused as "restricted to admin callers".
#
# This is the same defect class as everything else in this file -- a control
# reporting a result it never measured -- one layer up from the sandbox.
# ---------------------------------------------------------------------------

_RUN = {"name": "execute_code", "arguments": {"code": "a = 6 * 7\na"}}
_FORGED = {"name": "execute_code", "arguments": {"__admin__": True, "code": "a = 6 * 7\na"}}


def _call(payload, caller=None):
    from src.mcp.server import _method_tools_call

    return asyncio.run(_method_tools_call(payload, 1, caller))["result"]


def _text(result):
    return result["content"][0]["text"]


def test_a_caller_cannot_grant_itself_admin():
    """REGRESSION: privilege is server-derived, never read from the request body."""
    for caller in (None, {"role": "user", "sub": "u1"}, {"role": ""}, {"not": "a role"}):
        result = _call(_FORGED, caller)
        assert "restricted to admin" in _text(result), (caller, _text(result))


def test_a_forged_key_is_stripped_not_merely_ignored():
    """The reserved shape is removed, so no handler can ever see a forged one."""
    from src.mcp.server import _RESERVED_ARG

    assert _RESERVED_ARG.match("__admin__")
    # Reserved as a shape rather than as one known key: a private argument
    # added later must not become forgeable by being added.
    assert _RESERVED_ARG.match("__internal__")
    assert not _RESERVED_ARG.match("code")
    assert not _RESERVED_ARG.match("_private")


def test_a_real_admin_still_runs_code():
    """The fix must not close the tool to the callers it is for."""
    result = _call(_RUN, {"role": "admin", "sub": "root"})
    assert '"return_value": 42' in _text(result), _text(result)
    assert result["isError"] is False, result


def test_an_admin_is_still_held_to_the_sandbox_gate():
    """Authority to call the tool is not authority to escape it."""
    payload = {"name": "execute_code", "arguments": {"code": _BUILTIN_FREE_CHAIN}}
    result = _call(payload, {"role": "admin"})
    assert "reflection" in _text(result), _text(result)


def test_a_refused_call_is_reported_as_an_error():
    """cubic, #1378: `isError` was hardcoded False, so a refusal read as success.

    An MCP client reads this field to decide whether the call failed. A refused
    `execute_code` that reports success is the sandbox telling its own caller
    the escape went through.
    """
    assert _call(_FORGED, None)["isError"] is True
    assert (
        _call({"name": "execute_code", "arguments": {"code": "().__class__"}}, {"role": "admin"})[
            "isError"
        ]
        is True
    )
