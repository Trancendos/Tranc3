"""SEC-021's premise checker must see what the entry says it sees.

SEC-021 is the register's first `Blocked-by` entry, and its `Re-evaluate` row
claims all four of its triggers are enforced. A claim like that is worth
exactly as much as the probe behind it — `docs/governance/IMMUNE-SYSTEM.md`
makes that the rule for sensors, and a disposition is a sensor whose output is
"this finding has been adjudicated".

So each case here plants the defect the entry says it would catch, and asserts
the checker catches it. The inverse cases matter as much: a checker that fails
on `from src.mcp import ...` would make The Spark's own import look like the
vulnerable SDK, and the quickest way to get a noisy check disabled is to have
it cry about the thing it was told to ignore.
"""

from __future__ import annotations

import ast
import datetime
import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "cdp_sec021", Path(__file__).resolve().parents[1] / "scripts" / "check_disposition_premises.py"
)
assert _SPEC and _SPEC.loader
cdp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cdp)


def _imports(src: str) -> list[str]:
    return [what for _line, what in cdp._mcp_imports_in(ast.parse(src))]


# --- the import premise -------------------------------------------------


def test_a_bare_import_of_the_package_is_seen():
    assert _imports("import mcp") == ["import mcp"]
    assert _imports("import mcp.server.streamable_http") == ["import mcp.server.streamable_http"]
    assert _imports("from mcp import ClientSession") == ["from mcp import ..."]
    assert _imports("from mcp.server import Server") == ["from mcp.server import ..."]


def test_a_lazy_import_inside_a_function_is_still_an_import():
    """Unlike SEC-006, laziness buys nothing here.

    SEC-006 turns on nltk being reached lazily, because its premise is about
    what runs at import time. SEC-021's premise is that the package is not
    present on a production install at all, so an import anywhere contradicts
    it — including one inside a function that may never be called.
    """
    assert _imports("def f():\n    import mcp\n    return mcp") == ["import mcp"]


def test_the_spark_is_not_the_sdk():
    """`src/mcp/` is this estate's own MCP server and must not trip the check."""
    assert _imports("from src.mcp.server import router") == []
    assert _imports("import src.mcp") == []
    assert _imports("from .mcp import router") == []
    assert _imports("from ..mcp.server import router") == []


def test_a_similarly_named_package_is_not_the_sdk():
    assert _imports("import mcpx") == []
    assert _imports("from mcp_shim import thing") == []


def test_the_name_in_a_string_is_not_an_import():
    """Why this reads the AST and not the text."""
    assert _imports('DOC = "import mcp"') == []
    assert _imports('"""Example: from mcp import ClientSession."""') == []


# --- the runtime-declaration premise ------------------------------------


def test_a_direct_requirement_line_is_recognised():
    for line in ("mcp", "mcp==1.29.0", "mcp>=1.30.0", "mcp[cli]==2.2.0", "MCP == 1.29.0 # x"):
        assert cdp._declares_package(line, "mcp"), line


def test_a_comment_or_flag_or_other_package_is_not_a_declaration():
    for line in ("# mcp==1.29.0", "-r other.txt", "mcpx==1.0.0", "semgrep==1.179.0", ""):
        assert not cdp._declares_package(line, "mcp"), line


def test_a_runtime_manifest_declaring_the_package_fails(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text("mcp==1.29.0\n", encoding="utf-8")
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    assert cdp._runtime_declarations("mcp") == ["requirements.txt:1"]


def test_a_tooling_manifest_declaring_the_package_is_exempt(tmp_path, monkeypatch):
    """Pinning it in `requirements-security.txt` is how a fix would be taken.

    A check that failed on the remediation would push the next person the
    wrong way, which is the reasoning `_runtime_declarations` inherits from
    SEC-006 rather than inventing here.
    """
    (tmp_path / "requirements-security.txt").write_text("mcp==1.30.0\n", encoding="utf-8")
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    assert cdp._runtime_declarations("mcp") == []


# --- the census premises ------------------------------------------------


def _census(tmp_path: Path, *, generated_at: str | None = None, **overrides) -> None:
    finding = {
        "package": "mcp",
        "version": "1.29.0",
        "id": "CVE-2026-59951",
        "aliases": ["GHSA-84m7-p3x7-pcfv"],
        "fix_versions": ["1.30.0", "2.2.0"],
        "classification": "blocked",
    }
    finding.update(overrides)
    payload = {
        # These three are not decoration. SEC-021's premises are about what a
        # LIVE advisory feed currently says, so the checker now applies the
        # same freshness rule SEC-006 uses, and a fixture with no timestamp
        # reads as an answer of unbounded age -- correctly. Every case below
        # that is about version or fix-availability needs a CURRENT census to
        # reach that question at all.
        "generated_at": generated_at
        if generated_at is not None
        else datetime.datetime.now(datetime.UTC).isoformat(),
        "scanned_ok": True,
        "fixable_count": 0,
        "surfaces": [{"manifest": "requirements-security.txt", "findings": [finding]}],
    }
    out = tmp_path / cdp._CENSUS_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload), encoding="utf-8")


def test_the_measured_version_with_a_reachable_fix_named_passes(tmp_path, monkeypatch):
    _census(tmp_path)
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    assert cdp._census_mcp_premises() == []


def test_a_different_resolved_version_fails(tmp_path, monkeypatch):
    """The offline half of "re-check on every semgrep bump".

    semgrep's exact pin is the only thing holding mcp at 1.29.0 here, so a
    relaxed pin shows up as a different resolved version.
    """
    _census(tmp_path, version="1.31.0")
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    failures = cdp._census_mcp_premises()
    assert len(failures) == 1
    assert "resolved mcp 1.31.0" in failures[0]
    assert "the pin moved" in failures[0]


def test_no_named_fix_fails_because_that_is_a_suppress_not_a_block(tmp_path, monkeypatch):
    """The inverse of SEC-006's and SEC-020's version premise, deliberately.

    Those rest on "no patched release exists". This one rests on a fix
    existing and being out of reach, so an empty `fix_versions` means the
    label is wrong — and the distinction is what keeps a `Blocked-by` from
    silently outliving the condition that justified it.
    """
    _census(tmp_path, fix_versions=[])
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    failures = cdp._census_mcp_premises()
    assert len(failures) == 1
    assert "no longer names any fixed version" in failures[0]


def test_the_advisory_disappearing_fails_rather_than_passing_quietly(tmp_path, monkeypatch):
    (tmp_path / cdp._CENSUS_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    # Fresh and complete, with no surfaces: the premise under test is the
    # advisory VANISHING, which is only reachable once the file's age and
    # completeness are settled. An undated file fails on age first — correct
    # precedence, and not what this case is about.
    (tmp_path / cdp._CENSUS_OUTPUT).write_text(
        json.dumps(
            {
                "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "scanned_ok": True,
                "fixable_count": 0,
                "surfaces": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    failures = cdp._census_mcp_premises()
    assert len(failures) == 1
    assert "no longer reports" in failures[0]


def test_a_different_mcp_advisory_does_not_satisfy_this_premise(tmp_path, monkeypatch):
    """Matched on the id, never on the package alone.

    A second mcp finding standing at 1.29.0 would otherwise read as "already
    adjudicated" and SEC-021 would never be re-evaluated — the defect a
    reviewer reported against SEC-020's first version.
    """
    _census(tmp_path, id="CVE-2027-00001", aliases=[])
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    failures = cdp._census_mcp_premises()
    assert len(failures) == 1
    assert "no longer reports" in failures[0]


def test_an_absent_census_is_reported_as_unconfirmed_not_as_clean(tmp_path, monkeypatch):
    """A checker that cannot see must not say the premise holds."""
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    failures = cdp._census_mcp_premises()
    assert len(failures) == 1
    assert "is absent" in failures[0]


def test_an_unreadable_census_is_reported_as_unconfirmed(tmp_path, monkeypatch):
    out = tmp_path / cdp._CENSUS_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    failures = cdp._census_mcp_premises()
    assert len(failures) == 1
    assert "could not be read" in failures[0]


# --- the entry and the checker must agree -------------------------------


def test_the_register_entry_marks_the_advisory_blocked_and_nothing_else():
    """`blocked_ids()` collects every id in a block carrying a `Blocked-by` row.

    So a second identifier mentioned anywhere inside SEC-021 would be labelled
    unreachable-behind-an-upstream-pin on the strength of a decision made about
    mcp. The entry says it names no other id; this is what holds it to that.
    """
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    try:
        from src.security import accepted_risk_register as register
    finally:
        sys.path.remove(str(root))

    assert register.blocked_ids() == {"CVE-2026-59951", "GHSA-84M7-P3X7-PCFV"}


def test_the_checker_is_wired_into_main():
    """An unreferenced check is a check that does not run."""
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "check_disposition_premises.py"
    ).read_text(encoding="utf-8")
    main = source.split("def main() -> int:", 1)[1]
    assert "check_sec_021()" in main.split("\n\n", 1)[0]


# ---------------------------------------------------------------------------
# Reported by cubic on #1376, and it is the same defect this entry's probes
# were written to demonstrate: everything above exercises a HELPER, so
# replacing `check_sec_021` with `return []` left all of it green, and the
# wiring test only proved the name appears in `main`. These call the function.
# ---------------------------------------------------------------------------


def _tree(tmp_path: Path, **kwargs) -> Path:
    """A synthetic repository `check_sec_021` can be pointed at."""
    out = tmp_path / cdp._CENSUS_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    finding = {
        "package": "mcp",
        "version": "1.29.0",
        "id": "CVE-2026-59951",
        "aliases": ["GHSA-84m7-p3x7-pcfv"],
        "fix_versions": ["1.30.0", "2.2.0"],
    }
    finding.update(kwargs.pop("finding", {}))
    out.write_text(
        json.dumps(
            {
                # Current and complete, for the reason `_census` gives: the
                # freshness rule now gates these premises, so a tree whose
                # census carries no timestamp fails on its AGE and never
                # reaches the premise each case here is about.
                "generated_at": kwargs.pop(
                    "generated_at", datetime.datetime.now(datetime.UTC).isoformat()
                ),
                "scanned_ok": True,
                "fixable_count": 0,
                "surfaces": [{"manifest": "requirements-security.txt", "findings": [finding]}],
            }
        ),
        encoding="utf-8",
    )
    for name, body in kwargs.pop("files", {}).items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    assert not kwargs, kwargs
    return tmp_path


def test_the_whole_check_passes_on_a_tree_that_holds_the_premises(tmp_path, monkeypatch):
    """The control: without it, every case below could pass for the wrong reason."""
    monkeypatch.setattr(cdp, "ROOT", _tree(tmp_path))
    assert cdp.check_sec_021() == []


def test_the_whole_check_fails_on_a_runtime_declaration(tmp_path, monkeypatch):
    monkeypatch.setattr(cdp, "ROOT", _tree(tmp_path, files={"requirements.txt": "mcp==1.29.0\n"}))
    failures = cdp.check_sec_021()
    assert len(failures) == 1
    assert "declares `mcp` as a runtime dependency" in failures[0]


def test_the_whole_check_fails_on_a_nested_project_declaration(tmp_path, monkeypatch):
    """`tranc3-bots/pyproject.toml` is a real second project in this repository.

    Reading only the root pyproject meant a package could become a declared
    runtime dependency of a shipped component with this check still green.
    """
    monkeypatch.setattr(
        cdp,
        "ROOT",
        _tree(
            tmp_path,
            files={"sub/pyproject.toml": '[project]\nname = "x"\ndependencies = ["mcp==1.29.0"]\n'},
        ),
    )
    failures = cdp.check_sec_021()
    assert len(failures) == 1
    assert "sub/pyproject.toml" in failures[0]


def test_the_whole_check_fails_on_an_import_of_the_package(tmp_path, monkeypatch):
    monkeypatch.setattr(cdp, "ROOT", _tree(tmp_path, files={"m.py": "from mcp import Client\n"}))
    failures = cdp.check_sec_021()
    assert len(failures) == 1
    assert "imports the `mcp` package" in failures[0]


@pytest.mark.parametrize(
    "source",
    [
        '__import__("mcp")\n',
        'import importlib\nimportlib.import_module("mcp")\n',
        'from importlib import import_module\nimport_module("mcp.server")\n',
    ],
    ids=["dunder-import", "importlib-attribute", "importlib-bare-name"],
)
def test_the_whole_check_fails_on_a_dynamic_import(tmp_path, monkeypatch, source):
    """An AST guard that only reads `Import`/`ImportFrom` can be walked past."""
    monkeypatch.setattr(cdp, "ROOT", _tree(tmp_path, files={"m.py": source}))
    failures = cdp.check_sec_021()
    assert len(failures) == 1
    assert "imports the `mcp` package" in failures[0]


def test_a_computed_dynamic_import_is_not_guessed_at():
    """Unresolvable is reported as nothing, not as a match.

    A guard that guessed at `import_module(name)` would fire on every dynamic
    import in the tree, and a check that cries about what it cannot read is
    the kind that gets switched off.
    """
    assert cdp._mcp_imports_in(ast.parse("import_module(name)\n")) == []
    assert cdp._mcp_imports_in(ast.parse('__import__("mcp" + suffix)\n')) == []
    assert cdp._mcp_imports_in(ast.parse('import_module("other")\n')) == []


def test_the_whole_check_fails_when_the_census_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    failures = cdp.check_sec_021()
    assert any("is absent" in f for f in failures)


# --- the freshness premise ----------------------------------------------
#
# Raised by coderabbit on #1403: SEC-006 applied `_census_staleness` and
# SEC-020/SEC-021 did not, so a census old enough to predate a new fixed
# release could confirm "a fix exists and cannot be reached" from the one
# document that cannot know. Three entries now share one rule.


def test_a_stale_census_cannot_confirm_the_premises(tmp_path, monkeypatch):
    """A three-day-old census is not a current answer about a live feed.

    Measured on this estate: a worktree holding a census generated
    2026-10-13 confirmed SEC-006's premises three days later. The same file
    would have confirmed SEC-021's.
    """
    old = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=3)
    _census(tmp_path, generated_at=old.isoformat())
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    failures = cdp._census_mcp_premises()
    assert len(failures) == 1
    assert failures[0].startswith("SEC-021:"), "the reason must read as SEC-021's, not SEC-006's"
    assert "not a current answer" in failures[0]


def test_an_incomplete_census_is_unconfirmed_rather_than_passing(tmp_path, monkeypatch):
    """`scanned_ok: false` means the scan did not complete. That is neither a
    failing scan nor a pass, and must not confirm a premise either way."""
    _census(tmp_path)
    out = tmp_path / cdp._CENSUS_OUTPUT
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["scanned_ok"] = False
    out.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    failures = cdp._census_mcp_premises()
    assert len(failures) == 1
    assert failures[0].startswith("SEC-021:")
    assert "did not complete" in failures[0]


def test_the_freshness_rule_is_read_from_the_checker_not_the_subject(tmp_path, monkeypatch):
    """REGRESSION. `_census_staleness` resolved `src/immune/verdict.py` from
    `ROOT` -- the tree being MEASURED -- while the boundary reader beside it
    used `_SOURCE_ROOT`. `spec_from_file_location` returns a spec for a path
    that does not exist, so against any subject tree without a `src/` the
    unguarded `exec_module` raised `FileNotFoundError` and took the whole
    check down, instead of the "could not be loaded" reason the next lines
    were written to return. Every test here monkeypatches `ROOT`, so this is
    the configuration the suite itself runs in."""
    _census(tmp_path)
    monkeypatch.setattr(cdp, "ROOT", tmp_path)
    assert not (tmp_path / "src" / "immune" / "verdict.py").exists()
    assert cdp._census_mcp_premises() == []


# --- the dynamic-import receiver ----------------------------------------
#
# cubic raised both halves on #1403: matching `.import_module` on any receiver
# claims unrelated code, and matching only the bare spelling lets an alias or
# the `name=` keyword walk past. The bindings are now read from each module's
# own imports.


@pytest.mark.parametrize(
    "source",
    [
        'import importlib as il\nil.import_module("mcp")\n',
        'from importlib import import_module as imp\nimp("mcp")\n',
        'from importlib import import_module\nimport_module(name="mcp")\n',
        'import importlib\nimportlib.import_module(name="mcp.server")\n',
        'import builtins\nbuiltins.__import__("mcp")\n',
        'import importlib.util\nimportlib.import_module("mcp")\n',
        'from importlib import *\nimport_module("mcp")\n',
    ],
    ids=[
        "module-alias",
        "function-alias",
        "name-keyword",
        "name-keyword-dotted",
        "builtins-dunder",
        "submodule-import-binds-parent",
        "wildcard-import",
    ],
)
def test_every_importlib_spelling_is_seen(source):
    """Each of these reached the `mcp` SDK and none was recognised before."""
    assert _imports(source), f"bypassed: {source!r}"


@pytest.mark.parametrize(
    "source",
    [
        'self.import_module("mcp")\n',
        'registry.import_module("mcp")\n',
        'loader.import_module("mcp")\n',
        'import_module("mcp")\n',
        'il.import_module("mcp")\n',
        'obj.__import__("mcp")\n',
    ],
    ids=[
        "self-method",
        "named-receiver",
        "loader-method",
        "unbound-bare-name",
        "unbound-receiver",
        "dunder-on-object",
    ],
)
def test_an_unrelated_import_module_method_is_not_claimed(source):
    """`.import_module` is an ordinary method name. Claiming every receiver
    would have this check firing on code that never touches importlib, and the
    quickest way to get a noisy check disabled is to have it cry about the
    thing it was told to ignore."""
    assert _imports(source) == [], f"false positive: {source!r}"


def test_a_locally_defined_import_module_is_not_importlibs():
    """The whole-module case: a class with its own `import_module`, called on
    an instance, resolves to no importlib binding and is left alone."""
    source = (
        "class Registry:\n"
        "    def import_module(self, name):\n"
        "        return name\n"
        'Registry().import_module("mcp")\n'
    )
    assert _imports(source) == []
