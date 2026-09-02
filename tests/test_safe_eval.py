import pytest

from src.workflow.nodes.base import _safe_eval


def test_safe_eval_literals():
    assert _safe_eval("1", {}) == 1
    assert _safe_eval("3.14", {}) == 3.14
    assert _safe_eval("'string'", {}) == "string"
    assert _safe_eval("True", {}) is True
    assert _safe_eval("False", {}) is False
    assert _safe_eval("None", {}) is None


def test_safe_eval_data_structures():
    assert _safe_eval("[1, 2, 3]", {}) == [1, 2, 3]
    assert _safe_eval("(1, 2, 3)", {}) == (1, 2, 3)
    assert _safe_eval("{'a': 1, 'b': 2}", {}) == {"a": 1, "b": 2}


def test_safe_eval_variables():
    assert _safe_eval("a", {"a": 42}) == 42
    assert _safe_eval("my_list", {"my_list": [1, 2, 3]}) == [1, 2, 3]
    with pytest.raises(ValueError, match="Unknown variable"):
        _safe_eval("unknown_var", {})


def test_safe_eval_unary_ops():
    assert _safe_eval("-5", {}) == -5
    assert _safe_eval("+5", {}) == 5
    assert _safe_eval("not True", {}) is False
    assert _safe_eval("~5", {}) == ~5


def test_safe_eval_binary_ops():
    assert _safe_eval("1 + 2", {}) == 3
    assert _safe_eval("10 - 5", {}) == 5
    assert _safe_eval("3 * 4", {}) == 12
    assert _safe_eval("10 / 2", {}) == 5.0
    assert _safe_eval("10 % 3", {}) == 1
    assert _safe_eval("2 ** 3", {}) == 8
    assert _safe_eval("10 // 3", {}) == 3


def test_safe_eval_binary_ops_limits():
    # The repetition ceiling bounds the *result*, not the repeat count, so
    # "'A' * 1001" is legitimate while anything over the size ceiling is not.
    # The earlier per-operand limit rejected the former and still let chaining
    # through, which is the case test_chained_multiplication... now covers.
    assert len(_safe_eval("'A' * 1001", {})) == 1001
    with pytest.raises(ValueError, match="maximum allowed size"):
        _safe_eval("'A' * 1000001", {})
    with pytest.raises(ValueError, match="Power operation limit exceeded"):
        _safe_eval("1001 ** 2", {})
    with pytest.raises(ValueError, match="Power operation limit exceeded"):
        _safe_eval("2 ** 1001", {})


def test_safe_eval_comparisons():
    assert _safe_eval("1 == 1", {}) is True
    assert _safe_eval("1 != 2", {}) is True
    assert _safe_eval("1 < 2", {}) is True
    assert _safe_eval("2 <= 2", {}) is True
    assert _safe_eval("2 > 1", {}) is True
    assert _safe_eval("2 >= 2", {}) is True
    assert _safe_eval("'a' in ['a', 'b']", {}) is True
    assert _safe_eval("'c' not in ['a', 'b']", {}) is True
    with pytest.raises(ValueError, match="Multiple comparisons not supported"):
        _safe_eval("1 < 2 < 3", {})


def test_safe_eval_bool_ops():
    assert _safe_eval("True and True", {}) is True
    assert _safe_eval("True and False", {}) is False
    assert _safe_eval("True or False", {}) is True
    assert _safe_eval("False or False", {}) is False


def test_safe_eval_subscript():
    assert _safe_eval("a[0]", {"a": [10, 20]}) == 10
    assert _safe_eval("d['key']", {"d": {"key": "value"}}) == "value"


def test_safe_eval_attribute():
    class Dummy:
        public = 42
        _private = "secret"

    assert _safe_eval("obj.public", {"obj": Dummy()}) == 42
    with pytest.raises(ValueError, match="Access to private attribute '_private' is denied"):
        _safe_eval("obj._private", {"obj": Dummy()})
    with pytest.raises(ValueError, match="Attribute 'missing' not found"):
        _safe_eval("obj.missing", {"obj": Dummy()})


def test_safe_eval_call():
    # The namespace deliberately stays empty. Injecting {"len": len} here would
    # pass while production still failed: ConditionNode and TransformNode build
    # the namespace from workflow inputs only and never add a builtin, so a
    # test that supplies one proves nothing about the call path that runs.
    assert _safe_eval("len([1, 2, 3])", {}) == 3
    assert _safe_eval("str(42)", {}) == "42"
    assert _safe_eval("int('42')", {}) == 42
    assert _safe_eval("float('3.14')", {}) == 3.14
    assert _safe_eval("bool(1)", {}) is True
    assert _safe_eval("max(1, 5)", {}) == 5
    assert _safe_eval("min(1, 5)", {}) == 1
    assert _safe_eval("abs(-5)", {}) == 5
    assert _safe_eval("sum([1, 2, 3])", {}) == 6
    assert _safe_eval("sorted([3, 1, 2])", {}) == [1, 2, 3]
    assert _safe_eval("round(1.567, 1)", {}) == 1.6
    assert _safe_eval("any([False, True])", {}) is True
    assert _safe_eval("all([True, True])", {}) is True
    assert _safe_eval("'hello'.upper()", {}) == "HELLO"
    assert _safe_eval("{'a': 1}.get('a')", {}) == 1
    assert _safe_eval("{'a': 1}.keys()", {}) == {"a": 1}.keys()


def test_safe_eval_call_restrictions():
    import os

    with pytest.raises(ValueError, match="Method call on non-standard type is denied"):
        _safe_eval("os.system('ls')", {"os": os})
    with pytest.raises(ValueError, match="Function call is denied"):
        _safe_eval("func()", {"func": lambda: 1})


def test_safe_eval_unsupported():
    with pytest.raises(ValueError, match="Unsupported node type"):
        _safe_eval("lambda x: x", {})
    with pytest.raises(ValueError, match="Unsupported node type"):
        _safe_eval("[x for x in [1,2,3]]", {})


def test_safe_eval_dos_multiplication():
    """The ceiling applies with the count on either side of the operator."""
    for expr in (
        "1000001 * 'A'",
        "'A' * 1000001",
        "[1] * 1000001",
        "1000001 * (1,)",
    ):
        with pytest.raises(ValueError, match="maximum allowed size"):
            _safe_eval(expr, {})


def test_safe_eval_kwargs():
    assert _safe_eval("dict(a=1, b=2)", {}) == {"a": 1, "b": 2}


# ── Regression coverage for defects found while reviewing this evaluator ──────


class _Holder:
    """Stands in for any non-JSON object a caller may place in the namespace."""

    def __init__(self) -> None:
        # Deliberately not shaped like a credential: detect-secrets scans this
        # file, and the test needs a private-ish value, not a secret-looking one.
        self.internal_note = "operator-only-value"


def test_format_cannot_traverse_private_attributes():
    """str.format runs its own getattr, bypassing the dunder-attribute rule.

    The AST walker refuses `obj.__dict__`, but "{0.__dict__}".format(obj) does
    that traversal inside CPython where the walker cannot see it, so the guard
    has to deny the method itself.
    """
    ns = {"holder": _Holder(), "name": "bob"}
    for expr in (
        "'{0.__class__}'.format(name)",
        "'{0.__dict__}'.format(holder)",
        "'{0.internal_note}'.format(holder)",
    ):
        with pytest.raises(ValueError, match="unrestricted attribute access"):
            _safe_eval(expr, ns)


def test_format_map_is_denied_too():
    with pytest.raises(ValueError, match="unrestricted attribute access"):
        _safe_eval("'{a}'.format_map({'a': 1})", {})


def test_chained_multiplication_cannot_exceed_the_size_ceiling():
    """Guarding only the repeat count is bypassed by chaining.

    Each step below repeats by 1000 — under any per-operand limit — while the
    sequence itself grows to 100 MB. The ceiling has to bound the result.
    """
    with pytest.raises(ValueError, match="maximum allowed size"):
        _safe_eval("'a' * 1000 * 1000 * 100", {})


def test_single_oversized_repetition_is_rejected_before_allocating():
    with pytest.raises(ValueError, match="maximum allowed size"):
        _safe_eval("'a' * 2000000", {})


def test_modest_repetition_still_works():
    assert len(_safe_eval("'a' * 100", {})) == 100


def test_oversized_integer_results_are_rejected():
    """Huge integers are refused, whichever guard reaches them first."""
    with pytest.raises(ValueError, match="Power operation limit exceeded"):
        _safe_eval("2 ** 100000", {})
    # Each factor is ~9,955 bits — individually fine, and the power guard has
    # nothing to object to. Only a ceiling on the running result stops the
    # product, which reaches ~119,000 bits.
    huge = " * ".join(["(999 ** 999)"] * 12)
    with pytest.raises(ValueError, match="maximum allowed size"):
        _safe_eval(huge, {})


def test_builtins_are_reachable_from_the_production_namespace():
    """The namespace ConditionNode actually builds, with no builtin injected."""
    inputs = {"items": [1, 2, 3], "label": "grid"}
    ns = {"inputs": inputs, "context": {}, **inputs}
    assert _safe_eval("len(items) == 3", ns) is True
    assert _safe_eval("label.upper()", ns) == "GRID"
    assert _safe_eval("max(items)", ns) == 3


def test_type_constructors_do_not_open_an_escape():
    """Naming str/dict/list exposes the type objects; calls through them stay shut."""
    ns = {"name": "bob"}
    for expr in (
        "str.join('-', ['a', 'b'])",
        "dict.fromkeys([1, 2])",
        "list.append([], 1)",
        "int.from_bytes(b'ab', 'big')",
        "str.encode(name)",
    ):
        with pytest.raises(ValueError):
            _safe_eval(expr, ns)


# ── Findings from Sourcery's review of this evaluator ─────────────────────────


def test_dict_unpacking_is_merged_not_dropped():
    """`{**mapping}` used to evaluate to {} — silent data loss, not an error.

    A TransformNode merging its inputs returned an empty dict and reported
    success, so the workflow carried on with the data gone.
    """
    ns = {"data": {"a": 1, "b": 2}, "extra": {"c": 3}}
    assert _safe_eval("{**data}", ns) == {"a": 1, "b": 2}
    assert _safe_eval("{**data, 'd': 4}", ns) == {"a": 1, "b": 2, "d": 4}
    assert _safe_eval("{**data, **extra}", ns) == {"a": 1, "b": 2, "c": 3}
    # A later key wins, matching Python's own semantics.
    assert _safe_eval("{**data, 'a': 9}", ns) == {"a": 9, "b": 2}


def test_keyword_unpacking_is_merged_not_dropped():
    """`dict(**values)` used to call the function with the arguments missing."""
    ns = {"values": {"x": 9, "y": 8}}
    assert _safe_eval("dict(**values)", ns) == {"x": 9, "y": 8}
    assert _safe_eval("dict(z=1, **values)", ns) == {"z": 1, "x": 9, "y": 8}


def test_unpacking_a_non_mapping_is_refused():
    ns = {"n": 5, "items": [1, 2]}
    for expr in ("{**n}", "dict(**n)", "{**items}"):
        with pytest.raises(ValueError, match="Only a mapping can be unpacked"):
            _safe_eval(expr, ns)


def test_expression_length_is_bounded():
    """A literal is only as big as the text spelling it out, so the text is capped."""
    huge_literal = "[" + ",".join(["1"] * 300000) + "]"
    with pytest.raises(ValueError, match="maximum allowed length"):
        _safe_eval(huge_literal, {})


def test_collection_literals_are_size_guarded(monkeypatch):
    """The ceiling applies to collections too, not only to repetition.

    The ceiling is lowered here rather than building a million-entry literal:
    the guard is what's under test, not the machine's memory. Without this the
    check would be unreachable in a test and could rot unnoticed.
    """
    import src.workflow.nodes.base as base

    monkeypatch.setattr(base, "_MAX_SEQ_LEN", 3)
    for expr in ("[1, 2, 3, 4]", "(1, 2, 3, 4)", "{'a': 1, 'b': 2, 'c': 3, 'd': 4}"):
        with pytest.raises(ValueError, match="maximum allowed size"):
            _safe_eval(expr, {})
    # A merge that overflows the ceiling is caught the same way.
    ns = {"x": {"a": 1, "b": 2}, "y": {"c": 3, "d": 4}}
    with pytest.raises(ValueError, match="maximum allowed size"):
        _safe_eval("{**x, **y}", ns)
    # And anything within the ceiling still evaluates.
    assert _safe_eval("[1, 2]", {}) == [1, 2]


# ── Findings from CodeRabbit's review of this evaluator ───────────────────────


def test_boolean_operators_return_the_operand_not_a_bool():
    """`all()`/`any()` collapsed and/or to True or False.

    Python returns the operand that decided the expression, and workflow
    transforms depend on it: "x or default" is the ordinary way to supply a
    fallback, and it evaluated to True whichever side won — a silently wrong
    value that a TransformNode passed downstream as data.
    """
    ns = {"data": {"name": "bob"}, "empty": {}, "n": 0, "items": [1, 2]}
    assert _safe_eval("data.get('name') or 'unknown'", ns) == "bob"
    assert _safe_eval("empty.get('name') or 'unknown'", ns) == "unknown"
    assert _safe_eval("data.get('name') and 'yes'", ns) == "yes"
    assert _safe_eval("n or 42", ns) == 42
    assert _safe_eval("n and 42", ns) == 0
    assert _safe_eval("1 and 2 and 3", ns) == 3
    assert _safe_eval("0 or '' or 'last'", ns) == "last"
    # Still usable as a condition, which is what ConditionNode does with it.
    assert bool(_safe_eval("items and 'has'", ns)) is True


def test_boolean_operators_short_circuit():
    """The operand after a decided result is never evaluated.

    `missing` is not in the namespace, so evaluating it would raise. That it
    does not proves the right-hand side was skipped.
    """
    # The operands are chosen so bool-coercion cannot masquerade as a pass:
    # all()/any() would return False/True here, and "" != False, "keep" != True.
    ns = {"truthy": "keep", "falsy": ""}
    assert _safe_eval("falsy and missing", ns) == ""
    assert _safe_eval("truthy or missing", ns) == "keep"
    with pytest.raises(ValueError, match="Unknown variable: missing"):
        _safe_eval("truthy and missing", ns)


def test_mutating_methods_cannot_change_workflow_state():
    """`inputs` and `context` enter the namespace by reference.

    An expression could call context.clear(), wiping execution_id and
    workflow_id from a running workflow, or inputs.pop(k) to remove data
    before downstream nodes saw it — reachable from an unauthenticated
    POST /grid/workflows.
    """
    context = {"execution_id": "abc", "workflow_id": "wf1"}
    inputs = {"a": 1, "b": 2, "rows": [1, 2]}
    ns = {"inputs": inputs, "context": context, **inputs}
    for expr in (
        "context.clear()",
        "inputs.pop('a')",
        "inputs.update({'z': 9})",
        "inputs.setdefault('q', 1)",
        "rows.append(3)",
        "rows.sort()",
        # Nested, which copying the namespace would not have covered.
        "inputs['rows'].clear()",
    ):
        with pytest.raises(ValueError, match="mutates its receiver"):
            _safe_eval(expr, ns)
    assert context == {"execution_id": "abc", "workflow_id": "wf1"}
    assert inputs == {"a": 1, "b": 2, "rows": [1, 2]}


def test_read_only_collection_methods_still_work():
    ns = {"inputs": {"a": 1, "b": 2}, "rows": [3, 1, 2]}
    assert _safe_eval("inputs.get('a')", ns) == 1
    assert _safe_eval("list(inputs.keys())", ns) == ["a", "b"]
    assert _safe_eval("sorted(rows)", ns) == [1, 2, 3]
    assert _safe_eval("len(rows)", ns) == 3
    assert _safe_eval("rows.count(1)", ns) == 1
    assert _safe_eval("rows.index(1)", ns) == 1


# ── Findings from cubic's review of this evaluator ───────────────────────────


def test_duplicate_keyword_across_explicit_and_unpacked_is_refused():
    """Python raises for `f(z=1, **{'z': 2})`; a plain update() silently kept one.

    The evaluator was giving a different answer from the same expression
    outside it — the caller could not tell which value the function received.
    """
    with pytest.raises(ValueError, match="multiple values for keyword argument 'z'"):
        _safe_eval("dict(z=1, **values)", {"values": {"z": 2}})
    # Collisions between two unpacked mappings count too.
    with pytest.raises(ValueError, match="multiple values for keyword argument 'k'"):
        _safe_eval("dict(**a, **b)", {"a": {"k": 1}, "b": {"k": 2}})
    # Non-colliding names are unaffected.
    assert _safe_eval("dict(z=1, **values)", {"values": {"y": 2}}) == {"z": 1, "y": 2}


def test_call_results_are_size_guarded(monkeypatch):
    """A permitted builtin could return more than the ceiling allows.

    Namespace values are not bounded by _MAX_EXPR_CHARS — they arrive in the
    request body — so `list(s)` over a long input string built an unbounded
    list even though every other path was guarded.
    """
    import src.workflow.nodes.base as base

    monkeypatch.setattr(base, "_MAX_SEQ_LEN", 10)
    for expr, ns in (
        ("list(s)", {"s": "a" * 50}),
        ("sorted(xs)", {"xs": list(range(50))}),
        ("dict(**big)", {"big": {str(i): i for i in range(50)}}),
    ):
        with pytest.raises(ValueError, match="maximum allowed size"):
            _safe_eval(expr, ns)
    # Within the ceiling, calls behave normally.
    assert _safe_eval("list(s)", {"s": "abc"}) == ["a", "b", "c"]


def test_non_dict_mappings_are_deliberately_refused_for_unpacking():
    """Widening this to collections.abc.Mapping would run the operand's own code.

    dict.update() on a non-dict mapping calls that object's keys() and
    __getitem__, so accepting arbitrary Mapping implementations would hand
    execution back to the operand — the opposite of what this evaluator is
    for. Workflow namespaces are built from JSON-decoded input, so every real
    mapping reaching here is already a plain dict.
    """
    import collections.abc

    class CustomMapping(collections.abc.Mapping):
        def __getitem__(self, key):  # pragma: no cover - must never be called
            raise AssertionError("operand code must not run during unpacking")

        def __iter__(self):  # pragma: no cover - must never be called
            raise AssertionError("operand code must not run during unpacking")

        def __len__(self):
            return 0

    with pytest.raises(ValueError, match="Only a mapping can be unpacked"):
        _safe_eval("{**m}", {"m": CustomMapping()})
    with pytest.raises(ValueError, match="Only a mapping can be unpacked"):
        _safe_eval("dict(**m)", {"m": CustomMapping()})
