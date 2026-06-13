import ast
from pathlib import Path

API_PATH = Path(__file__).resolve().parents[1] / "api.py"
API_TREE = ast.parse(API_PATH.read_text())


def _module_call_index(name: str) -> int:
    for index, node in enumerate(API_TREE.body):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == name:
                return index
    raise AssertionError(f"Module-level call to {name}() not found")


def _find_function(name: str) -> ast.AsyncFunctionDef:
    for node in API_TREE.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Async function {name} not found")


def test_api_import_invokes_shared_startup_validator():
    imports_validator = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "src.core.startup_validator"
        and any(alias.name == "validate_startup" for alias in node.names)
        for node in API_TREE.body
    )
    assert imports_validator
    assert _module_call_index("validate_startup") > _module_call_index("load_dotenv")


def test_lifespan_tracks_bootstrap_completion_state():
    module_sets_default = any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_bootstrap_complete" for target in node.targets)
        and isinstance(node.value, ast.Constant)
        and node.value.value is False
        for node in API_TREE.body
    )
    assert module_sets_default

    lifespan = _find_function("lifespan")
    states = []
    for node in lifespan.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_bootstrap_complete"
            for target in node.targets
        ):
            if isinstance(node.value, ast.Constant):
                states.append(node.value.value)

    assert states == [False, True, False]


def test_ready_returns_503_until_bootstrap_is_complete():
    ready = _find_function("ready")

    guard = ready.body[0]
    assert isinstance(guard, ast.If)
    assert isinstance(guard.test, ast.UnaryOp)
    assert isinstance(guard.test.op, ast.Not)
    assert isinstance(guard.test.operand, ast.Name)
    assert guard.test.operand.id == "_bootstrap_complete"

    guarded_return = guard.body[0]
    assert isinstance(guarded_return, ast.Return)
    assert isinstance(guarded_return.value, ast.Call)
    assert isinstance(guarded_return.value.func, ast.Name)
    assert guarded_return.value.func.id == "JSONResponse"

    status_code = next(
        keyword.value.value
        for keyword in guarded_return.value.keywords
        if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant)
    )
    assert status_code == 503

    success_return = ready.body[-1]
    assert isinstance(success_return, ast.Return)
    assert isinstance(success_return.value, ast.Dict)

    ready_values = [
        value.value
        for key, value in zip(success_return.value.keys, success_return.value.values)
        if isinstance(key, ast.Constant) and key.value == "ready" and isinstance(value, ast.Constant)
    ]
    assert ready_values == [True]
