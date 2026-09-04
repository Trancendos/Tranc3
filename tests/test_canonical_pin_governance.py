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
    renovate_extra=None,
    canonical_src=None,
):
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / ".github").mkdir(exist_ok=True)
    pin = tmp_path / "scripts" / "align_framework_pins.py"
    pin.write_text(canonical_src or CANONICAL_SRC, encoding="utf-8")

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
    config = {"packageRules": rules if rules is not None else [DISABLE_RULE]}
    config.update(renovate_extra or {})
    renovate.write_text(json.dumps(config), encoding="utf-8")
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
    """`!pattern` is a negative matcher: a rule that excludes the package does not re-enable it.

    Written as negations alone. Renovate requires `*` to be the only value in
    `matchPackageNames`, so `["*", "!pydantic", "!fastapi"]` -- how this fixture
    read until 2026-09-04 -- is schema-invalid and could never have run. A rule
    carrying only negations already matches everything they do not exclude,
    which is the same intent expressed legally.
    """
    module = checker(
        *_write_configs(
            tmp_path,
            rules=[
                DISABLE_RULE,
                {"matchPackageNames": ["!pydantic", "!fastapi"], "enabled": True},
            ],
        )
    )
    assert module.main() == 0


def test_a_regex_selector_with_the_i_flag_is_honoured(tmp_path, checker):
    """`/^py.*/i` is a Renovate regex, not a glob.

    Without the flag-aware branch it fell through to glob matching, where a
    literal `/^py.*/i` matches no package name at all -- so a rule re-enabling
    the governed pins read as inert and the check passed on a tree where it
    should have failed.
    """
    module = checker(
        *_write_configs(
            tmp_path,
            rules=[
                DISABLE_RULE,
                {"matchPackageNames": ["/^PYD.*/i"], "enabled": True},
            ],
        )
    )
    assert module.main() == 1


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


def test_a_boolean_minimum_release_age_is_rejected(tmp_path, checker):
    """Renovate types `minimumReleaseAge` as `string | null`; `false` is invalid.

    This is not cosmetic. A schema violation makes Renovate reject the WHOLE
    config, so the 7-day supply-chain cooldown every other rule sets stops being
    applied — including on the governed pins. The real file carried `false` in
    four places.
    """
    module = checker(
        *_write_configs(
            tmp_path,
            renovate_extra={"vulnerabilityAlerts": {"minimumReleaseAge": False}},
        )
    )
    assert module.main() == 1


def test_a_null_minimum_release_age_is_the_documented_way_to_waive_the_cooldown(tmp_path, checker):
    """`null` expresses the same intent legally, so it must not be reported."""
    module = checker(
        *_write_configs(
            tmp_path,
            renovate_extra={"vulnerabilityAlerts": {"minimumReleaseAge": None}},
        )
    )
    assert module.main() == 0


def test_a_boolean_minimum_release_age_inside_a_package_rule_is_rejected(tmp_path, checker):
    """The same violation is fatal wherever in the config it appears."""
    module = checker(
        *_write_configs(
            tmp_path,
            rules=[DISABLE_RULE, {"matchPackageNames": ["torch"], "minimumReleaseAge": False}],
        )
    )
    assert module.main() == 1


def test_selector_fields_are_anded_not_flattened(tmp_path, checker):
    """Renovate requires EVERY selector field to match, not any one of them.

    `matchPackageNames: ["fastapi", "pydantic"]` combined with
    `matchDepNames: ["something-else"]` matches nothing at all in Renovate. The
    earlier implementation flattened both fields into one list and read the rule
    as covering `fastapi`, so an entirely ineffective block satisfied
    governance.
    """
    ineffective = {
        "description": "Looks like a block, matches nothing",
        "matchPackageNames": ["fastapi", "pydantic"],
        "matchDepNames": ["a-package-that-is-not-governed"],
        "enabled": False,
    }
    module = checker(*_write_configs(tmp_path, rules=[ineffective]))
    assert module.main() == 1


def test_a_rule_scoped_to_another_manager_is_not_the_pypi_block(tmp_path, checker):
    """`matchManagers: ["npm"]` disables npm updates, not the Python pins.

    Accepting it as the estate-wide block let the tree pass with no pypi block
    at all.
    """
    scoped_away = dict(DISABLE_RULE, matchManagers=["npm"])
    module = checker(*_write_configs(tmp_path, rules=[scoped_away]))
    assert module.main() == 1

    module = checker(*_write_configs(tmp_path, rules=[DISABLE_RULE]))
    assert module.main() == 0


def test_a_rule_scoped_to_a_file_path_is_not_the_pypi_block(tmp_path, checker):
    """Same reasoning for `matchFileNames`: it narrows the block to one file."""
    scoped_away = dict(DISABLE_RULE, matchFileNames=["web/package.json"])
    module = checker(*_write_configs(tmp_path, rules=[scoped_away]))
    assert module.main() == 1


def test_an_unparseable_regex_selector_is_reported_not_treated_as_a_match(tmp_path, checker):
    """Returning True for a bad regex was fail-OPEN on the disabling rule.

    A typo in the block would have read as "this rule covers the package" and
    satisfied governance. It is a config error and is now reported as one.
    """
    broken = dict(DISABLE_RULE, matchPackageNames=["/^(fastapi/"])
    module = checker(*_write_configs(tmp_path, rules=[broken]))
    assert module.main() == 1


def test_a_minimatch_brace_selector_is_reported_rather_than_guessed(tmp_path, checker):
    """`{fastapi,pydantic}` is valid minimatch and means nothing to fnmatch.

    fnmatch would report "no match" for a selector Renovate does match, so the
    checker says it cannot model it instead of guessing.
    """
    braced = dict(DISABLE_RULE, matchPackageNames=["{fastapi,pydantic}"])
    module = checker(*_write_configs(tmp_path, rules=[braced]))
    assert module.main() == 1


def test_a_later_docker_rule_for_the_same_name_does_not_fail_governance(tmp_path, checker):
    """`redis` is both a governed PyPI pin and a Docker image on this estate.

    A later rule enabling the Docker image was reported as re-enabling the PyPI
    pin — a false failure on a correct config, and the kind of noise that gets a
    check deleted rather than obeyed.
    """
    docker_rule = {
        "description": "Redis image digests carry real fixes",
        "matchDatasources": ["docker"],
        "matchPackageNames": ["redis"],
        "enabled": True,
    }
    with_redis = (
        "\nCANONICAL: dict[str, str] = {\n"
        '    "fastapi": "0.141.1",\n'
        '    "pydantic": "2.13.5",\n'
        '    "redis": "6.4.0",\n'
        "}\n"
    )
    args = _write_configs(
        tmp_path,
        canonical_src=with_redis,
        dependabot_ignore=("fastapi", "pydantic", "redis"),
        rules=[
            dict(DISABLE_RULE, matchPackageNames=["fastapi", "pydantic", "redis"]),
            docker_rule,
        ],
    )
    module = checker(*args)
    # The fixture must actually govern `redis`, or this test passes for the
    # wrong reason: an ungoverned package is never evaluated at all.
    assert "redis" in module.canonical_packages()
    assert module.main() == 0


def test_a_regex_selector_is_case_sensitive_without_the_i_flag(tmp_path, checker):
    """Renovate treats `/^PYDANTIC$/` as case SENSITIVE; it matches nothing here.

    Applying re.IGNORECASE unconditionally made it match `pydantic`, so a
    disabling rule that does not actually cover the package read as covering
    it — over-matching, which on a block is fail-open.
    """
    wrong_case = dict(DISABLE_RULE, matchPackageNames=["/^FASTAPI$/", "/^PYDANTIC$/"])
    module = checker(*_write_configs(tmp_path, rules=[wrong_case]))
    assert module.main() == 1


def test_the_i_flag_still_matches(tmp_path, checker):
    """`/i` is how Renovate asks for case-insensitivity, and it must work."""
    flagged = dict(DISABLE_RULE, matchPackageNames=["/^FASTAPI$/i", "/^PYDANTIC$/i"])
    module = checker(*_write_configs(tmp_path, rules=[flagged]))
    assert module.main() == 0


def test_a_negative_extglob_is_reported_not_read_as_a_negation(tmp_path, checker):
    """`!(fastapi)` is a minimatch extglob, not a `!`-negated selector.

    Stripping the `!` handed `(fastapi)` to the matcher, which matches nothing,
    so the negation never fired and a block Renovate does not apply to
    `fastapi` was accepted.
    """
    extglob = dict(DISABLE_RULE, matchPackageNames=["!(fastapi)"])
    module = checker(*_write_configs(tmp_path, rules=[extglob]))
    assert module.main() == 1


def test_an_age_scoped_rule_is_not_the_estate_wide_block(tmp_path, checker):
    """`matchCurrentAge` narrows the rule; it cannot be the whole block."""
    aged = dict(DISABLE_RULE, matchCurrentAge="> 30 days")
    module = checker(*_write_configs(tmp_path, rules=[aged]))
    assert module.main() == 1


def test_a_later_rule_scoped_to_another_manager_is_not_an_override(tmp_path, checker):
    """An npm-scoped rule cannot re-enable a pypi pin.

    Flagging it was a false failure on a correct config — the same noise that
    gets a check deleted rather than obeyed.
    """
    npm_rule = {
        "description": "npm packages may update freely",
        "matchManagers": ["npm"],
        "matchPackageNames": ["fastapi"],
        "enabled": True,
    }
    module = checker(*_write_configs(tmp_path, rules=[DISABLE_RULE, npm_rule]))
    assert module.main() == 0
