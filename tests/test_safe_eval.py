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
    assert _safe_eval("{'a': 1, 'b': 2}", {}) == {'a': 1, 'b': 2}

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
    with pytest.raises(ValueError, match="Multiplication limit exceeded"):
        _safe_eval("'A' * 1001", {})
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
    assert _safe_eval("len([1, 2, 3])", {"len": len}) == 3
    assert _safe_eval("str(42)", {"str": str}) == "42"
    assert _safe_eval("int('42')", {"int": int}) == 42
    assert _safe_eval("float('3.14')", {"float": float}) == 3.14
    assert _safe_eval("bool(1)", {"bool": bool}) == True
    assert _safe_eval("max(1, 5)", {"max": max}) == 5
    assert _safe_eval("min(1, 5)", {"min": min}) == 1
    assert _safe_eval("abs(-5)", {"abs": abs}) == 5
    assert _safe_eval("sum([1, 2, 3])", {"sum": sum}) == 6
    assert _safe_eval("'hello'.upper()", {}) == "HELLO"
    assert _safe_eval("{'a': 1}.get('a')", {}) == 1
    assert _safe_eval("{'a': 1}.keys()", {}) == {'a': 1}.keys()

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
    with pytest.raises(ValueError, match="Multiplication limit exceeded"):
        _safe_eval("1001 * 'A'", {})
    with pytest.raises(ValueError, match="Multiplication limit exceeded"):
        _safe_eval("'A' * 1001", {})
    with pytest.raises(ValueError, match="Multiplication limit exceeded"):
        _safe_eval("[1] * 1001", {})
    with pytest.raises(ValueError, match="Multiplication limit exceeded"):
        _safe_eval("1001 * (1,)", {})

def test_safe_eval_kwargs():
    assert _safe_eval("dict(a=1, b=2)", {"dict": dict}) == {"a": 1, "b": 2}
