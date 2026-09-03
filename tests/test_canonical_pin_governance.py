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


# The real config declares three pip ecosystems. Modelling only one meant a
# regression in `/tranc3-bots` or `/workers` could not be caught, so every
# fixture builds all three and faults can be injected into a non-root block.
PIP_DIRECTORIES = ("/", "/tranc3-bots", "/workers")


def _write_configs(
    tmp_path,
    *,
    dependabot_ignore=("fastapi", "pydantic"),
    per_directory=None,
    rules=None,
):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / ".github").mkdir(exist_ok=True)
    pin = tmp_path / "scripts" / "align_framework_pins.py"
    pin.write_text(CANONICAL_SRC, encoding="utf-8")

    per_directory = per_directory or {}
    blocks = []
    for directory in PIP_DIRECTORIES:
        names = per_directory.get(directory, dependabot_ignore)
        entries = "".join(
            f'      - dependency-name: "{n}"\n'
            if isinstance(n, str)
            else f'      - dependency-name: "{n[0]}"\n        update-types: {n[1]}\n'
            for n in names
        )
        blocks.append(
            f'  - package-ecosystem: "pip"\n    directory: "{directory}"\n    ignore:\n' + entries
        )
    dependabot = tmp_path / ".github" / "dependabot.yml"
    dependabot.write_text("version: 2\nupdates:\n" + "".join(blocks), encoding="utf-8")

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
                    "enabled": True,
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
                {"groupName": "late", "matchPackageNames": ["/^pydan/"], "enabled": True},
            ],
        )
    )
    assert module.main() == 1


def test_a_later_rule_that_does_not_re_enable_is_allowed(tmp_path, checker):
    """Renovate merges matching rules option by option.

    A later rule that groups or sets `automerge` does NOT re-enable a disabled
    package -- only `enabled: true` does. Flagging every later match would
    reject legitimate grouping rules, and a check people have to weaken to ship
    is a check that stops being trusted.
    """
    module = checker(
        *_write_configs(
            tmp_path,
            rules=[
                DISABLE_RULE,
                {
                    "groupName": "grouping only, no enabled key",
                    "matchPackageNames": ["fastapi", "pydantic"],
                    "automerge": True,
                },
            ],
        )
    )
    assert module.main() == 0


def test_fails_when_a_later_glob_rule_re_enables_a_governed_package(tmp_path, checker):
    """`matchPackageNames` accepts minimatch globs, not just exact names.

    A rule written `["pyd*"]` re-enables pydantic. Reading only exact names
    treated it as matching nothing, so the block looked intact.
    """
    module = checker(
        *_write_configs(
            tmp_path,
            rules=[
                DISABLE_RULE,
                {"groupName": "glob", "matchPackageNames": ["pyd*"], "enabled": True},
            ],
        )
    )
    assert module.main() == 1


def test_fails_when_a_selectorless_rule_re_enables_everything(tmp_path, checker):
    """A rule with no package selector at all applies to every dependency."""
    module = checker(
        *_write_configs(
            tmp_path,
            rules=[DISABLE_RULE, {"description": "catch-all", "enabled": True}],
        )
    )
    assert module.main() == 1


def test_fails_when_a_deprecated_selector_re_enables_a_governed_package(tmp_path, checker):
    """`matchPackagePatterns` and `matchPackagePrefixes` are still honoured."""
    for rule in (
        {"matchPackagePatterns": ["^pydan"], "enabled": True},
        {"matchPackagePrefixes": ["pyd"], "enabled": True},
        {"matchDepNames": ["pydantic"], "enabled": True},
    ):
        module = checker(*_write_configs(tmp_path, rules=[DISABLE_RULE, dict(rule)]))
        assert module.main() == 1, rule


def test_a_negated_glob_excludes_the_package_from_a_later_rule(tmp_path, checker):
    """`!pattern` is a negative matcher: a rule that excludes the package does not re-enable it."""
    module = checker(
        *_write_configs(
            tmp_path,
            rules=[
                DISABLE_RULE,
                {"matchPackageNames": ["*", "!pydantic", "!fastapi"], "enabled": True},
            ],
        )
    )
    assert module.main() == 0


def test_the_disabling_rule_must_cover_the_pypi_datasource(tmp_path, checker):
    """A block scoped to a non-pypi datasource does not govern the Python pins."""
    scoped_away = dict(DISABLE_RULE, matchDatasources=["docker"])
    module = checker(*_write_configs(tmp_path, rules=[scoped_away]))
    assert module.main() == 1

    scoped_right = dict(DISABLE_RULE, matchDatasources=["pypi"])
    module = checker(*_write_configs(tmp_path, rules=[scoped_right]))
    assert module.main() == 0


def test_fails_when_a_dependabot_ignore_is_scoped_to_update_types(tmp_path, checker):
    """A major-only ignore still lets minor and patch PRs through.

    That is the exact PR shape this governance exists to stop, so an
    `update-types`-scoped entry must not count as ignoring the package.
    """
    module = checker(
        *_write_configs(
            tmp_path,
            dependabot_ignore=("fastapi", ("pydantic", '["version-update:semver-major"]')),
        )
    )
    assert module.main() == 1


def test_fails_when_a_non_root_pip_ecosystem_misses_a_pin(tmp_path, checker):
    """The root block passing says nothing about /tranc3-bots or /workers."""
    module = checker(*_write_configs(tmp_path, per_directory={"/workers": ("fastapi",)}))
    assert module.main() == 1


def test_fails_closed_on_a_renovate_config_that_is_not_an_object(tmp_path, checker):
    """Valid JSON is not a valid config: a list parses, then crashes on `.get`."""
    for body in ("[]", '"just a string"', "42"):
        pin, dependabot, renovate = _write_configs(tmp_path)
        renovate.write_text(body, encoding="utf-8")
        module = checker(pin, dependabot, renovate)
        assert module.main() == 1, body


def test_the_real_repo_configs_pass():
    """The estate's actual configs, not a synthetic stand-in."""
    module = _load()
    assert module.main() == 0
