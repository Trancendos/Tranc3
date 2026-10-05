"""Each spelling of an import-time exit, driven against the check.

`scripts/check_importable_scripts.py` exists because one module-level
`sys.exit(1)` took the whole pytest run down with INTERNALERROR. Its first
version drew the import-time boundary in four wrong places at once, and each
mistake let that same defect back through in a different spelling — a class
body, a decorator, an inverted `__name__` test, `raise SystemExit`. Three
reviewers found them; none of the cases below existed as a test.

So every case here is a mutation: a file the check must reject, or one it must
accept. A guard whose own boundary is untested is the thing it guards against.
"""

import ast
import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_importable_scripts", REPO / "scripts" / "check_importable_scripts.py"
)
check = importlib.util.module_from_spec(_spec)
sys.modules["check_importable_scripts"] = check
_spec.loader.exec_module(check)


def _exits(source: str, tmp_path: Path) -> list:
    script = tmp_path / "subject.py"
    script.write_text(textwrap.dedent(source), encoding="utf-8")
    return check._module_level_exits(script)


# --- what runs on import, and so must be rejected --------------------------


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("import sys\nsys.exit(1)\n", id="module body"),
        pytest.param(
            "import sys\ntry:\n    import yaml\nexcept ImportError:\n    sys.exit(1)\n",
            id="except branch (the original defect)",
        ),
        pytest.param(
            "import sys\n\n\nclass Guard:\n    sys.exit(1)\n",
            id="class body",
        ),
        pytest.param(
            "import sys\n\n\n@sys.exit\ndef f():\n    pass\n",
            id="decorator",
        ),
        pytest.param(
            "import sys\n\n\ndef f(value=sys.exit(1)):\n    pass\n",
            id="default argument",
        ),
        pytest.param(
            'import sys\n\nif __name__ != "__main__":\n    sys.exit(1)\n',
            id="inverted __name__ test",
        ),
        pytest.param(
            'import sys\n\nif __name__ == "__main__":\n    f()\nelse:\n    sys.exit(1)\n',
            id="else branch of the main guard",
        ),
        pytest.param("raise SystemExit(1)\n", id="raise SystemExit"),
        pytest.param(
            "def main():\n    return 0\n\n\nraise SystemExit(main())\n",
            id="raise SystemExit(main()) — this repo's idiom",
        ),
        pytest.param("import os\n\nos._exit(1)\n", id="os._exit"),
        pytest.param("quit()\n", id="quit"),
        pytest.param(
            "import sys\n\nfor _ in range(1):\n    sys.exit(1)\n",
            id="inside a loop",
        ),
        pytest.param(
            "import sys\n\nwith open(__file__) as fh:\n    sys.exit(1)\n",
            id="inside a with block",
        ),
    ],
)
def test_an_import_time_exit_is_reported(source, tmp_path):
    assert _exits(source, tmp_path), "this terminates the interpreter on import"


# --- what does not run on import, and so must be accepted ------------------


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            'import sys\n\n\ndef main():\n    return 0\n\n\nif __name__ == "__main__":\n'
            "    sys.exit(main())\n",
            id="the main guard itself",
        ),
        pytest.param(
            "import sys\n\n\ndef main():\n    sys.exit(1)\n",
            id="a function body",
        ),
        pytest.param(
            "import sys\n\n\nclass C:\n    def m(self):\n        sys.exit(1)\n",
            id="a method body",
        ),
        pytest.param(
            "import sys\n\nif sys.version_info >= (3, 8):\n\n    def f():\n        sys.exit(1)\n",
            id="a deferred body nested in a module-level if",
        ),
        pytest.param(
            'raise ValueError("not a termination")\n',
            id="raising something that is not SystemExit",
        ),
    ],
)
def test_a_deferred_exit_is_not_reported(source, tmp_path):
    assert _exits(source, tmp_path) == [], "this only runs when called"


# --- discovery -------------------------------------------------------------


def test_a_normal_module_import_is_discovered():
    """The first version matched only path loading, missing six test files."""
    tree = ast.parse("from scripts.check_docs_estate import main\n")
    assert check._imports_in(tree) == {"check_docs_estate.py"}


def test_a_from_scripts_import_of_several_names_is_discovered():
    tree = ast.parse("from scripts import check_lab_languages, lab_capability_report\n")
    assert check._imports_in(tree) == {
        "check_lab_languages.py",
        "lab_capability_report.py",
    }


def test_a_path_loaded_script_is_discovered():
    tree = ast.parse('spec_from_file_location("x", ROOT / "scripts" / "estate_lint.py")\n')
    assert check._loaded_paths_in(tree) == {"estate_lint.py"}


def test_a_path_named_only_in_prose_is_not_discovered():
    """Reading text rather than syntax pulled unrelated scripts into scope."""
    tree = ast.parse('"""See scripts/estate_lint.py for details."""\n')
    assert check._loaded_paths_in(tree) == set()
    assert check._imports_in(tree) == set()


def test_an_unrelated_py_constant_is_not_attributed_to_scripts():
    tree = ast.parse('open("data/fixture.py")\n')
    assert check._loaded_paths_in(tree) == set()


# --- the suite as committed ------------------------------------------------


def test_the_real_suite_is_in_scope_and_clean():
    """The check must have something to check; an empty scope is a defect."""
    importers = check._scripts_imported_by_tests()
    assert importers, "no test appears to import any script"
    assert check.main() == 0


def test_the_discovered_scope_includes_both_import_routes():
    importers = check._scripts_imported_by_tests()
    assert "estate_lint.py" in importers, "the path-loaded route"
    assert "check_docs_estate.py" in importers, "the normal-import route"
