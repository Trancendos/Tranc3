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
