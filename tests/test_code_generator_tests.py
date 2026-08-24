from src.skills.code_generator import _generate_pytest_tests


def test_generate_pytest_tests_builtins():
    code = """
def func_int() -> int: pass
def func_str() -> str: pass
def func_list() -> list: pass
def func_none() -> None: pass
"""
    result = _generate_pytest_tests(code, "")
    assert "assert isinstance(result, int)" in result
    assert "assert isinstance(result, str)" in result
    assert "assert isinstance(result, list)" in result
    assert "assert result is None" in result


def test_generate_pytest_tests_generics():
    code = """
def func_list_gen() -> List[str]: pass
def func_dict_gen() -> Dict[str, int]: pass
def func_optional() -> Optional[int]: pass
"""
    result = _generate_pytest_tests(code, "")
    assert "assert isinstance(result, list)" in result
    assert "assert isinstance(result, dict)" in result
    assert "assert result is not None  # TODO: strengthen assertion" in result
