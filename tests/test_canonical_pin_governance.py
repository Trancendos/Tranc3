"""Tests for scripts/check_canonical_pin_governance.py.

Each test corresponds to a fault that was injected against the real configs to
confirm the check fires, then restored. Building synthetic configs here rather
than mutating the repo's own keeps the suite from depending on the estate's
current bot settings, which change.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_canonical_pin_governance.py"


def _load():
    """Load the checker by path; it is a script, not an installed module."""
    spec = importlib.util.spec_from_file_location("_cpg", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_cpg"] = module
    spec.loader.exec_module(module)
    return module


CANONICAL_SRC = """
CANONICAL: dict[str, str] = {
    "fastapi": "0.141.1",
    "pydantic": "2.13.5",
}
"""

DISABLE_RULE = {
    "description": "Centrally governed pins — do not propose.",
    "matchPackageNames": ["fastapi", "pydantic"],
    "enabled": False,
}


def _write_configs(tmp_path, *, dependabot_ignore=("fastapi", "pydantic"), rules=None):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / ".github").mkdir(exist_ok=True)
    pin = tmp_path / "scripts" / "align_framework_pins.py"
    pin.write_text(CANONICAL_SRC, encoding="utf-8")

    ignore = "\n".join(f'      - dependency-name: "{n}"' for n in dependabot_ignore)
    dependabot = tmp_path / ".github" / "dependabot.yml"
    dependabot.write_text(
        "version: 2\nupdates:\n"
        '  - package-ecosystem: "pip"\n'
        '    directory: "/"\n'
        "    ignore:\n" + (ignore + "\n" if ignore else ""),
        encoding="utf-8",
    )

    renovate = tmp_path / "renovate.json"
    renovate.write_text(
        json.dumps({"packageRules": rules if rules is not None else [DISABLE_RULE]}),
        encoding="utf-8",
    )
    return pin, dependabot, renovate


@pytest.fixture()
def checker(tmp_path, monkeypatch):
    """The checker pointed at a synthetic repo under tmp_path."""
    module = _load()

    def _point_at(pin, dependabot, renovate):
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(module, "PIN_SCRIPT", pin)
        monkeypatch.setattr(module, "DEPENDABOT", dependabot)
        monkeypatch.setattr(module, "RENOVATE", renovate)
        return module

    return _point_at


def test_passes_when_both_bots_exclude_every_governed_pin(tmp_path, checker):
    module = checker(*_write_configs(tmp_path))
    assert module.main() == 0


def test_fails_when_dependabot_misses_a_governed_pin(tmp_path, checker):
    """F1: a package dropped from one pip ecosystem's ignore list."""
    module = checker(*_write_configs(tmp_path, dependabot_ignore=("fastapi",)))
    assert module.main() == 1


def test_fails_when_renovate_has_no_disabling_rule(tmp_path, checker):
    """F2: the disabling rule removed entirely."""
    module = checker(*_write_configs(tmp_path, rules=[]))
    assert module.main() == 1


def test_fails_when_a_later_rule_overrides_the_block(tmp_path, checker):
    """F3: the real defect — Renovate applies rules in order, last match wins.

    A grouping rule placed below the block silently re-enables the packages.
    This is how `automerge: true` came to apply to the governed pins.
    """
    module = checker(
        *_write_configs(
            tmp_path,
            rules=[
                DISABLE_RULE,
                {
                    "groupName": "FastAPI stack",
                    "matchPackageNames": ["fastapi", "pydantic", "httpx"],
                    "matchUpdateTypes": ["minor", "patch"],
                    "automerge": True,
                },
            ],
        )
    )
    assert module.main() == 1


def test_fails_when_the_block_is_scoped_to_one_update_type(tmp_path, checker):
    """F4: `matchUpdateTypes: [major]` reads as a block but leaves the rest on."""
    scoped = dict(DISABLE_RULE, matchUpdateTypes=["major"])
    module = checker(*_write_configs(tmp_path, rules=[scoped]))
    assert module.main() == 1


def test_fails_closed_on_unparseable_renovate_config(tmp_path, checker):
    """F5: a config it cannot read is a failure, never a pass."""
    pin, dependabot, renovate = _write_configs(tmp_path)
    renovate.write_text("{ broken", encoding="utf-8")
    module = checker(pin, dependabot, renovate)
    assert module.main() == 1


def test_fails_when_canonical_gains_a_package_without_exclusions(tmp_path, checker):
    """F6: the rot scenario — a sixth pin added with no matching bot config."""
    pin, dependabot, renovate = _write_configs(tmp_path)
    pin.write_text(
        CANONICAL_SRC.replace(
            '    "pydantic": "2.13.5",',
            '    "pydantic": "2.13.5",\n    "redis": "8.1.0",',
        ),
        encoding="utf-8",
    )
    module = checker(pin, dependabot, renovate)
    assert module.main() == 1


def test_regex_rule_forms_are_matched(tmp_path, checker):
    """Renovate accepts `/regex/` as well as bare names; both must count.

    A block written as `/^fastapi$/` is a real block, and a *later* rule
    written that way is a real override — reading only bare names would miss
    both.
    """
    module = checker(
        *_write_configs(
            tmp_path,
            rules=[
                {
                    "description": "Centrally governed pins",
                    "matchPackageNames": ["/^fastapi$/", "/^pydantic$/"],
                    "enabled": False,
                }
            ],
        )
    )
    assert module.main() == 0

    module = checker(
        *_write_configs(
            tmp_path,
            rules=[
                DISABLE_RULE,
                {"groupName": "late", "matchPackageNames": ["/^pydan/"]},
            ],
        )
    )
    assert module.main() == 1


def test_the_real_repo_configs_pass():
    """The estate's actual configs, not a synthetic stand-in."""
    module = _load()
    assert module.main() == 0
