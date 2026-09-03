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
        '    os.environ["SECRET_KEY"] = "module-specific"\n'
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


def test_the_real_repo_is_clean():
    """The estate's actual tests, not a synthetic stand-in."""
    module = _load()
    assert module.main() == 0
