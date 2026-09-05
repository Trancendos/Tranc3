"""Tests for scripts/check_test_env_isolation.py.

Each case is a fault that was injected against the real tree to confirm the
check fires, then restored. Synthetic modules under `tmp_path` keep the suite
from depending on which test files happen to exist today.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_test_env_isolation.py"

CONFTEST_SRC = '_GUARDED_ENV_VARS = ("INTERNAL_SECRET", "SECRET_KEY", "JWT_SECRET")\n'


def _load():
    """Load the checker by path; it is a script, not an installed module."""
    spec = importlib.util.spec_from_file_location("_tei", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_tei"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def checker(tmp_path, monkeypatch):
    """The checker pointed at a synthetic tree under tmp_path."""

    def _build(modules: dict[str, str], conftest: str = CONFTEST_SRC):
        tests = tmp_path / "tests"
        tests.mkdir(exist_ok=True)
        for name, body in modules.items():
            (tests / name).write_text(body, encoding="utf-8")
        conf = tmp_path / "conftest.py"
        conf.write_text(conftest, encoding="utf-8")

        module = _load()
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(module, "TEST_ROOT", tests)
        monkeypatch.setattr(module, "CONFTEST", conf)
        return module

    return _build


def test_passes_on_a_clean_module(checker):
    module = checker({"test_ok.py": "import os\n\n\ndef test_x():\n    assert os\n"})
    assert module.main() == 0


def test_fails_on_a_module_level_assignment(checker):
    """The real defect: `os.environ["SECRET_KEY"] = ...` at import time."""
    module = checker({"test_bad.py": 'import os\n\nos.environ["SECRET_KEY"] = "x"\n'})
    assert module.main() == 1


def test_setdefault_is_not_a_violation(checker):
    """conftest sets these before collection, so setdefault is a no-op.

    Twenty real modules use it correctly. Flagging them would make this check
    noise, and a noisy check gets weakened rather than obeyed.

    Reviewed and deliberately kept. A review asked for setdefault to be flagged
    on the grounds that conftest permits an absent baseline. It does not:
    conftest.py runs `os.environ[var] = os.environ.get(var) or default` for all
    four guarded vars, unconditionally, before any test module is collected, so
    the value is always present and non-empty and setdefault is PROVABLY a
    no-op -- not merely usually safe.
    """
    module = checker({"test_ok.py": 'import os\n\nos.environ.setdefault("SECRET_KEY", "x")\n'})
    assert module.main() == 0


def test_fails_on_a_module_level_pop(checker):
    """Removing a guarded var is as damaging as overwriting it."""
    module = checker({"test_bad.py": 'import os\n\nos.environ.pop("JWT_SECRET", None)\n'})
    assert module.main() == 1


def test_the_same_write_inside_a_fixture_is_allowed(checker):
    """The documented, correct pattern must not be reported."""
    body = (
        "import os\n\nimport pytest\n\n\n"
        '@pytest.fixture(scope="module", autouse=True)\n'
        "def _shared_env():\n"
        '    prior = os.environ.get("SECRET_KEY")\n'
        '    os.environ["SECRET_KEY"] = "module-specific"\n'  # pragma: allowlist secret
        "    try:\n        yield\n    finally:\n"
        '        os.environ["SECRET_KEY"] = prior\n'
    )
    module = checker({"test_ok.py": body})
    assert module.main() == 0


def test_an_unguarded_variable_is_ignored(checker):
    """Only the vars conftest actually guards are in scope."""
    module = checker({"test_ok.py": 'import os\n\nos.environ["SOME_OTHER"] = "x"\n'})
    assert module.main() == 0


def test_the_guarded_list_is_read_from_conftest_not_hardcoded(checker):
    """Adding a var to conftest must extend this check with no edit here."""
    module = checker(
        {"test_bad.py": 'import os\n\nos.environ["NEW_GUARDED"] = "x"\n'},
        conftest='_GUARDED_ENV_VARS = ("NEW_GUARDED",)\n',
    )
    assert module.main() == 1


def test_fails_closed_when_conftest_has_no_guarded_list(checker):
    """A check that cannot tell what is guarded must not report success."""
    module = checker({"test_ok.py": "import os\n"}, conftest="X = 1\n")
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 1


def test_fails_closed_on_a_test_file_it_cannot_parse(checker):
    """An unparseable module is a file it did not verify, so it is a failure."""
    module = checker({"test_broken.py": "def (((\n"})
    assert module.main() == 1


# ── forms the first version of this check could not see ──────────────────────


def test_fails_on_a_write_inside_a_module_level_if(checker):
    """`if ...:` at module level runs during collection exactly like a bare line.

    The first version iterated only `tree.body`, so this was invisible.
    """
    body = 'import os\n\nif os.getenv("CI"):\n    os.environ["SECRET_KEY"] = "x"\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_fails_on_a_write_inside_a_module_level_try(checker):
    """Same gap, reached through `try`/`except` instead of `if`."""
    body = 'import os\n\ntry:\n    os.environ["SECRET_KEY"] = "x"\nexcept KeyError:\n    pass\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_fails_on_a_write_inside_a_module_level_loop(checker):
    """And through a `for` body."""
    body = 'import os\n\nfor _ in range(1):\n    os.environ["JWT_SECRET"] = "x"\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_fails_on_a_write_in_a_class_body(checker):
    """A class body executes at import time; a method body does not."""
    body = 'import os\n\n\nclass Config:\n    os.environ["SECRET_KEY"] = "x"\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_a_write_inside_a_method_is_still_allowed(checker):
    """The `def` boundary is what separates import time from call time."""
    body = (
        'import os\n\n\nclass Thing:\n    def run(self):\n        os.environ["SECRET_KEY"] = "x"\n'
    )
    module = checker({"test_ok.py": body})
    assert module.main() == 0


def test_fails_on_a_module_level_del(checker):
    """`del os.environ[...]` removes a shared value during collection."""
    module = checker({"test_bad.py": 'import os\n\ndel os.environ["SECRET_KEY"]\n'})
    assert module.main() == 1


def test_fails_on_a_mutating_call_used_in_an_assignment(checker):
    """`_ = os.environ.pop(...)` mutates as much as the bare call does.

    Only `ast.Expr` statements were inspected, so binding the result hid it.
    """
    module = checker({"test_bad.py": 'import os\n\n_ = os.environ.pop("SECRET_KEY")\n'})
    assert module.main() == 1


def test_fails_on_an_augmented_assignment(checker):
    """`os.environ["SECRET_KEY"] += "x"` changes a value already set."""
    module = checker({"test_bad.py": 'import os\n\nos.environ["SECRET_KEY"] += "x"\n'})
    assert module.main() == 1


def test_fails_on_clear(checker):
    """`clear()` takes the guarded vars out along with everything else."""
    module = checker({"test_bad.py": "import os\n\nos.environ.clear()\n"})
    assert module.main() == 1


def test_fails_on_an_update_that_sets_a_guarded_key(checker):
    module = checker({"test_bad.py": 'import os\n\nos.environ.update({"SECRET_KEY": "x"})\n'})
    assert module.main() == 1


def test_an_update_of_only_unguarded_literal_keys_is_allowed(checker):
    """Flagging every `update()` reported work the check had not done.

    A literal mapping whose keys are all literal and unguarded is provably
    safe, and a check that rejects it is noise.
    """
    module = checker({"test_ok.py": 'import os\n\nos.environ.update({"TZ": "UTC"})\n'})
    assert module.main() == 0


def test_an_update_from_a_variable_is_flagged(checker):
    """A mapping the reader cannot see through cannot be shown safe."""
    body = 'import os\n\nEXTRA = {"SECRET_KEY": "x"}\nos.environ.update(EXTRA)\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_an_update_with_a_double_star_spread_is_flagged(checker):
    body = 'import os\n\nEXTRA = {"SECRET_KEY": "x"}\nos.environ.update(**EXTRA)\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_an_aliased_os_import_does_not_bypass_the_check(checker):
    """`import os as o` was a one-line way around the whole gate."""
    module = checker({"test_bad.py": 'import os as o\n\no.environ["SECRET_KEY"] = "x"\n'})
    assert module.main() == 1


def test_an_aliased_environ_import_does_not_bypass_the_check(checker):
    """So was `from os import environ as env`."""
    body = 'from os import environ as env\n\nenv.pop("JWT_SECRET", None)\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_a_local_alias_of_os_environ_does_not_bypass_the_check(checker):
    body = 'import os\n\nenv = os.environ\nenv["SECRET_KEY"] = "x"\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_an_unrelated_attribute_named_environ_is_not_os_environ(checker):
    """Matching any attribute called `environ` rejected innocent code."""
    body = (
        "class Config:\n    environ = {}\n\n\n"
        'settings = Config()\nsettings.environ["SECRET_KEY"] = "x"\n'
    )
    module = checker({"test_ok.py": body})
    assert module.main() == 0


def test_modules_named_with_the_suffix_pattern_are_scanned(checker):
    """pytest collects `*_test.py` too; `tests/integration/…_test.py` is real."""
    module = checker({"bridge_test.py": 'import os\n\nos.environ["SECRET_KEY"] = "x"\n'})
    assert module.main() == 1


def test_fails_closed_when_the_guarded_list_is_a_bare_string(checker):
    """`_GUARDED_ENV_VARS = "SECRET_KEY"` iterates CHARACTERS.

    The guarded set becomes {'S', 'E', 'C', …}, which matches no real variable,
    so every module passes and the gate is off while reporting success.
    """
    module = checker(
        {"test_bad.py": 'import os\n\nos.environ["SECRET_KEY"] = "x"\n'},
        conftest='_GUARDED_ENV_VARS = "SECRET_KEY"\n',
    )
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 1


def test_fails_closed_when_the_guarded_list_holds_a_non_string(checker):
    module = checker({"test_ok.py": "import os\n"}, conftest="_GUARDED_ENV_VARS = (1, 2)\n")
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 1


def test_the_real_repo_is_clean():
    """The estate's actual tests, not a synthetic stand-in."""
    module = _load()
    assert module.main() == 0


def test_the_dunder_setitem_form_is_detected(checker):
    """`os.environ.__setitem__("SECRET_KEY", "x")` bypassed the target scan.

    The target scan catches subscript assignment; written as a call, the same
    mutation was a one-line way around this gate.
    """
    body = 'import os\n\nos.environ.__setitem__("SECRET_KEY", "x")\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_the_dunder_delitem_form_is_detected(checker):
    body = 'import os\n\nos.environ.__delitem__("JWT_SECRET")\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_a_dunder_call_on_an_unguarded_name_is_allowed(checker):
    body = 'import os\n\nos.environ.__setitem__("SOME_OTHER", "x")\n'
    module = checker({"test_ok.py": body})
    assert module.main() == 0


def test_a_function_default_is_evaluated_at_import(checker):
    """`def f(v=os.environ.pop("SECRET_KEY")):` mutates during collection.

    The body is deferred; the DEFINITION is not. Skipping the whole
    `FunctionDef` node made every default value, decorator and annotation
    invisible — all of which run when the `def` statement executes.
    """
    body = 'import os\n\n\ndef test_x(v=os.environ.pop("SECRET_KEY", None)):\n    assert v\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_a_decorator_argument_is_evaluated_at_import(checker):
    """Same statement, a different part of it."""
    body = (
        "import os\n\nimport pytest\n\n\n"
        '@pytest.mark.parametrize("v", [os.environ.pop("SECRET_KEY", None)])\n'
        "def test_x(v):\n    assert v\n"
    )
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_a_lambda_default_is_evaluated_at_import(checker):
    body = 'import os\n\nf = lambda v=os.environ.pop("JWT_SECRET", None): v  # noqa: E731\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_a_function_body_is_still_deferred(checker):
    """The boundary has to stay where it was: bodies do not run at import."""
    body = 'import os\n\n\ndef test_x():\n    os.environ["SECRET_KEY"] = "x"\n'
    module = checker({"test_ok.py": body})
    assert module.main() == 0


def test_a_harmless_default_is_not_reported(checker):
    """Scanning definitions must not turn every `def` into a finding."""
    module = checker({"test_ok.py": "import os\n\n\ndef test_x(v=os.getcwd()):\n    assert v\n"})
    assert module.main() == 0


def test_a_chained_alias_does_not_bypass_the_check(checker):
    """`env = os.environ` was resolved; `copy = env` was not.

    Two lines instead of one, and the gate stopped seeing the mutation.
    """
    body = 'import os\n\nenv = os.environ\ncopy = env\ncopy["SECRET_KEY"] = "x"\n'
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_a_chained_alias_is_found_regardless_of_statement_order(checker):
    """`ast.walk` is not source order, so one pass over assignments is not enough.

    A single pass resolved the chain only when the walk happened to visit the
    root assignment first — which makes the gate's verdict depend on tree shape
    rather than on the code.
    """
    body = (
        "import os\n\n\n"
        "def _unrelated():\n    pass\n\n\n"
        "copy = env\nenv = os.environ\n"
        'copy["SECRET_KEY"] = "x"\n'
    )
    module = checker({"test_bad.py": body})
    assert module.main() == 1


def test_a_postponed_annotation_is_not_a_mutation(checker):
    """`from __future__ import annotations` makes annotations strings.

    `x: os.environ.pop("SECRET_KEY")` under that import evaluates nothing at
    all, and reporting it fails a correct module — the kind of false failure
    that gets a gate suppressed rather than fixed.
    """
    module = checker(
        {
            "test_ok.py": (
                'from __future__ import annotations\nimport os\n\nx: os.environ.pop("SECRET_KEY")\n'
            )
        }
    )
    assert module.main() == 0


def test_a_valued_annotation_still_runs_under_postponed_annotations(checker):
    """Only the ANNOTATION is deferred. The value is assigned as normal.

    Skipping the whole `AnnAssign` lost this: `x: T = os.environ.pop("K")`
    mutates the environment at import exactly like a bare line.
    """
    module = checker(
        {
            "test_bad.py": (
                "from __future__ import annotations\n"
                "import os\n\n"
                'x: str = os.environ.pop("SECRET_KEY")\n'
            )
        }
    )
    assert module.main() == 1


def test_an_annotation_target_still_evaluates_under_postponed_annotations(checker):
    """An attribute or subscript TARGET is evaluated even with no value.

    `env.pop("SECRET_KEY").field: int` runs `pop` before Python decides there
    is nothing to assign, so the statement mutates the environment while
    looking like a pure annotation.
    """
    module = checker(
        {
            "test_bad.py": (
                "from __future__ import annotations\n"
                "import os\n\n"
                'os.environ.pop("SECRET_KEY").field: int\n'
            )
        }
    )
    assert module.main() == 1


def test_without_the_future_import_an_annotation_does_run(checker):
    """No postponed annotations means the annotation expression evaluates."""
    module = checker({"test_bad.py": ('import os\n\nx: os.environ.pop("SECRET_KEY")\n')})
    assert module.main() == 1
