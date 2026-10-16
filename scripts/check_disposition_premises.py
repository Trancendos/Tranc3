#!/usr/bin/env python3
"""Every suppression rests on facts. When the facts move, the suppression must fall.

`SECURITY_ALERT_REGISTER.md` records a disposition for each open finding the
vulnerability census would otherwise block on. Two of those dispositions are
justified not by the advisory but by *how this repository uses the component*:

  SEC-006 (nltk PYSEC-2026-3740)
      Suppressed because the repository's only nltk use is a lazy
      `from nltk.corpus import wordnet` inside a try/except — no model
      artifact, no caller-supplied path, and so no reachable route to the
      path-sandbox bypass the advisory describes.

  SEC-007 (fflate GHSA-px8p-9vwx-vf98)
      Resolved, because `web/package-lock.json` resolves `fflate` to 0.4.9 —
      the advisory's own fixed release for the 0.4.x line. What is checked
      here is that it stays out of an affected range.

      It was an ACCEPT until 2026-09-26, justified by a long argument that
      the fix was unreachable behind `posthog-js`'s `^0.4.8` range. That
      argument read a *declared range* as if it were a *resolved version*
      and never opened the lockfile; 0.4.9 satisfies `^0.4.8` and was
      already installed. The check below is written the other way round —
      it reads the lockfile and compares it to the advisory, never to a
      version this repository asserts.

Each entry's `Re-evaluate` row listed only version and dependency triggers: a
new nltk release, a widened `posthog-js` range. Neither covered the premise the
reasoning actually rests on. Someone adding `nltk.data.load(user_path)` would
void the justification while the disposition kept the finding suppressed and
the gate kept passing — a control still reporting green about a fact that had
stopped being true.

CodeRabbit raised exactly this on PR #1152. Extending the prose alone would
have been the same defect one level up: a re-evaluation trigger nobody checks
is not a trigger. This script is what checks them.

Standard library only: the production gate installs little else.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = "SECURITY_ALERT_REGISTER.md"

#: Directories whose contents are not ours to reason about.
_SKIP = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "venv",
    ".venv",
    "site-packages",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
}

#: nltk APIs that read or write a filesystem path. The advisory is a
#: path-sandbox bypass; these are the calls that could reach it.
_NLTK_PATH_APIS = {"load", "download", "find", "retrieve"}

#: Manifests whose contents install into a *running* service. SEC-006 rests
#: partly on nltk not being one of these: today it reaches the tree only
#: transitively, because `safety` declares `nltk>=3.9`, so it is present in
#: the security tooling's resolution and in no production image.
#:
#: A manifest whose name marks it as tooling is exempt. Pinning nltk in
#: `requirements-security.txt` is how a future advisory would be remediated,
#: and a check that failed on the remediation would be a check pushing
#: people the wrong way.
_TOOLING_MANIFEST_MARKERS = ("test", "dev", "security", "lint", "docs", "ci")

#: GHSA-px8p-9vwx-vf98's affected ranges, transcribed from OSV
#: (https://api.osv.dev/v1/vulns/GHSA-px8p-9vwx-vf98). The advisory is not one
#: range but five, one per minor line, each with its own fix — which is the
#: whole reason this entry was mis-accepted. `posthog-js` declares
#: `fflate: ^0.4.8`, and 0.4.9, the fix for the 0.4.x line, is inside that
#: range. Reading the declared range as the resolved version is what produced
#: a year-long "the fix is unreachable" acceptance for a fix already installed.
#:
#: Each pair is (introduced, fixed): a version v is affected when
#: introduced <= v < fixed for any one pair.
_FFLATE_AFFECTED_RANGES = (
    ("0.4.5", "0.4.9"),
    ("0.5.0", "0.5.4"),
    ("0.6.0", "0.6.11"),
    ("0.7.0", "0.7.5"),
    ("0.8.0", "0.8.3"),
)

#: The package whose resolved version decides SEC-007. Only one: the call-site
#: evidence about `posthog-js@1.422.5` no longer carries the disposition, so
#: pinning it here would fail CI on an unrelated bump and say "security".
_SEC_007_PACKAGE = "fflate"
_WEB_LOCKFILE = "web/package-lock.json"

#: SEC-006 is a SUPPRESS, and a SUPPRESS is only honest while no fix exists.
#: The entry states that plainly: "3.10.3 is the latest version on PyPI, and
#: the GHSA record's range is introduced: 0, last_affected: 3.10.3 — every
#: published release is affected." Both halves are facts about a moment.
#:
#: `safety` pulls nltk in transitively, so no manifest pins it and there is
#: no Python lockfile to read. What there is: the census runs immediately
#: before this script in the production gate and writes what it actually
#: resolved. Reading its output is how the version premise becomes checkable
#: at all rather than remaining a sentence nobody re-reads.
_SEC_006_MEASURED_NLTK = "3.10.3"
_CENSUS_OUTPUT = "logs/vulnerability_census.json"

#: SEC-020 is a SUPPRESS on the same terms as SEC-006: no patched release
#: exists, and the finding is not reachable as this repository uses the
#: component. The second half is the part that can rot silently, so it is
#: the part this checks.
#:
#: CVE-2026-85394 (GHSA-3qf3-8w2g-rqmx, alias of CVE-2024-33663) is an
#: algorithm-confusion bypass: the guard python-jose added for the original
#: CVE can be stepped around with a DER-encoded public key. Exploiting it
#: requires a verifier that will attempt an HMAC algorithm while holding an
#: asymmetric key. A decode call that passes exactly ONE algorithm cannot do
#: that -- the token's `alg` either matches that single entry or is rejected
#: before any key is touched.
#:
#: So the premise is: every JWT decode site in this repository pins exactly
#: one algorithm, as a literal list. Measured 2026-10-06: twelve sites, all
#: single-element. The failure mode this guards is somebody widening one to
#: two (`["HS256", "RS256"]`) or passing a variable, which reintroduces the
#: confusion the suppression says cannot happen here.
_SEC_020_MEASURED_JOSE = "3.5.0"
_SEC_020_PACKAGE = "python-jose"

#: The advisory SEC-020 suppresses, with its aliases. Matching on the package
#: alone was wrong: if SEC-020 were closed while a *different* python-jose
#: finding stood at 3.5.0 with no fix, the package match would mark it "seen"
#: and this entry would never be re-evaluated. Raised by coderabbit on #1376.
_SEC_020_ADVISORY_IDS = frozenset(
    {
        "CVE-2026-85394",
        "GHSA-3QF3-8W2G-RQMX",
        "CVE-2024-33663",
        "GHSA-6C5P-J8VQ-PQHJ",
        "PYSEC-2024-232",
    }
)

#: Every manifest pinning python-jose. The census runs `--scope core`, which
#: does not cover the worker manifests, so the entry's "any version other than
#: 3.5.0" trigger went unenforced for seven of the eight places it is pinned.
#: Read directly rather than inferred. Raised by codex on #1376.
_SEC_020_MANIFESTS = (
    "requirements.txt",
    "workers/gateway-service/requirements-worker.txt",
    "workers/infinity-one-service/requirements-worker.txt",
    "workers/infinity-admin-service/requirements-worker.txt",
    "workers/sentinel-station-service/requirements-worker.txt",
    "workers/infinity-auth/requirements-worker.txt",
    "workers/infinity-portal-service/requirements-worker.txt",
    "workers/gbrain-bridge/requirements-worker.txt",
)

_JOSE_PIN = re.compile(r"^python-jose(?:\[[^\]]*\])?\s*==\s*([0-9][^\s#;]*)", re.MULTILINE)

#: SEC-021 is the register's first `Blocked-by` entry, and it inverts SEC-006's
#: and SEC-020's version premise rather than repeating it.
#:
#: Those two rest on "no patched release exists", so a fix appearing is what
#: makes them dishonest. This one rests on the opposite: a fix DOES exist
#: (1.30.0, 2.2.0) and nothing can reach it, because `semgrep` exact-pins
#: `mcp==1.29.0`. So the failing conditions are mirrored — an *empty*
#: `fix_versions` means the entry should be a SUPPRESS and not a Blocked-by,
#: and a resolved version other than 1.29.0 means the pin holding it there has
#: moved.
#:
#: That second condition is what makes the "re-check on every semgrep bump"
#: trigger checkable offline. semgrep's exact pin is the *only* thing fixing
#: mcp at 1.29.0 in this tree, so if semgrep relaxes it, the census resolves a
#: different version — or stops reporting the advisory at all, if the newly
#: reachable version is a patched one. Either way this fails and the entry gets
#: re-read. Reading `Requires-Dist: mcp` from semgrep's own metadata would be
#: more direct and is deliberately not done here: it needs the package index,
#: and a check that cannot reach the index would report a clean result it never
#: measured.
_SEC_021_MEASURED_MCP = "1.29.0"
_SEC_021_PACKAGE = "mcp"

#: The advisory SEC-021 carries, with its alias. Matched on the id, never on
#: the package alone — for the reason `_SEC_020_ADVISORY_IDS` records: a
#: different `mcp` finding standing at 1.29.0 would otherwise read as "already
#: adjudicated" and this entry would never be re-evaluated.
_SEC_021_ADVISORY_IDS = frozenset({"CVE-2026-59951", "GHSA-84M7-P3X7-PCFV"})

#: The names a JWT module is bound to at the decode sites in this tree:
#: `jwt` (python-jose and PyJWT both), `pyjwt`, `_jwt`, `jose_jwt`. The check
#: covers PyJWT sites too, deliberately: algorithm confusion is not unique to
#: python-jose (cf. CVE-2022-29217), and a single-algorithm allowlist is
#: correct on both. A site that genuinely needs two amends the entry.
_JWT_MODULE_NAMES = {"jwt", "pyjwt", "_jwt", "jose_jwt"}


def _walk(base: Path, suffixes: set[str]):
    """Repository files under `base` with one of `suffixes`, skipping vendored trees."""
    if not base.is_dir():
        return
    for path in base.rglob("*"):
        if path.suffix not in suffixes or not path.is_file():
            continue
        if any(part in _SKIP for part in path.parts):
            continue
        yield path


def _nltk_import_sites(tree: ast.AST) -> list[tuple[int, str, bool]]:
    """(line, module, is_lazy) for every nltk import in one module.

    `is_lazy` means the import statement is inside a function body, so it does
    not run at import time. The whole of SEC-006's reasoning is that nltk is
    reached lazily and only for a wordnet synonym lookup.
    """
    lazy_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                lazy_lines.add(getattr(inner, "lineno", -1))

    found: list[tuple[int, str, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "nltk" or alias.name.startswith("nltk."):
                    found.append((node.lineno, alias.name, node.lineno in lazy_lines))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "nltk" or module.startswith("nltk."):
                found.append((node.lineno, module, node.lineno in lazy_lines))
    return found


def _import_time_calls(body: list[ast.stmt]) -> set[str]:
    """Names called at import time in this module.

    A function body is deferred; a class body is not, and neither is an
    `if`/`try`/`with` at module level. Only bare `name()` calls are
    collected, which is what the laziness premise can actually be defeated
    by in practice.
    """
    called: set[str] = set()

    def descend(node: ast.AST) -> None:
        """Children that run when `node` runs.

        `ast.walk` is wrong here and was: it queues a function's children
        before the `isinstance` test can skip them, so a call inside a method
        of a module-level class read as an import-time call. That is exactly
        what it did on `src/search/query_expansion.py`, where
        `_wordnet_synonyms(kw)` sits in a `QueryExpander` method — deferred,
        not import-time — and the guard reported a premise violation that had
        not happened. A guard that cries wolf on the code it ships with is
        worse than no guard.

        A class body runs on import, so it is descended into; a `def`, `async
        def` or `lambda` body does not, so it is not.
        """
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                called.add(child.func.id)
            descend(child)

    for statement in body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(statement, ast.Call) and isinstance(statement.func, ast.Name):
            called.add(statement.func.id)
        descend(statement)
    return called


def _functions_importing_nltk(tree: ast.AST) -> dict[str, int]:
    """Function name -> line, for functions whose body imports nltk."""
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            module = None
            if isinstance(inner, ast.ImportFrom):
                module = inner.module or ""
            elif isinstance(inner, ast.Import):
                module = next((a.name for a in inner.names if a.name.split(".")[0] == "nltk"), None)
            if module and module.split(".")[0] == "nltk":
                found[node.name] = node.lineno
                break
    return found


def _nltk_path_calls(tree: ast.AST) -> list[tuple[int, str]]:
    """Calls into nltk's filesystem surface, e.g. `nltk.data.load(...)`."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _NLTK_PATH_APIS:
            continue
        # Walk the dotted prefix back to its root name.
        root = func.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and root.id == "nltk":
            found.append((node.lineno, f"nltk...{func.attr}()"))
    return found


def _census_staleness(output: Path) -> str:
    """A reason the census is too old to confirm a premise, or "".

    `src/immune/verdict.py` already holds the TTL rule and the reasoning for
    it, so this loads that module BY PATH rather than copying the arithmetic.
    Importing `src.immune.verdict` normally would execute `src/immune/__init__.py`,
    which imports PyYAML -- and this script's contract is that the production
    gate installs little else. Loading the one stdlib-only module directly keeps
    both promises: a single implementation of freshness, and no new dependency.
    """
    # Imported here, not at module scope: this is the only path that needs it,
    # and the import is cheap exactly once. (No suppression: PLC0415 is not in
    # [tool.ruff] select, so a directive naming it would silence nothing --
    # which is what scripts/check_inert_suppressions.py now counts.)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_verdict_for_premises", ROOT / "src" / "immune" / "verdict.py"
    )
    if spec is None or spec.loader is None:
        return (
            "SEC-006: src/immune/verdict.py could not be loaded, so the census "
            "freshness could not be established. Not a pass -- an unchecked age "
            "is not a current answer."
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    verdict = module.load_verdict(output)

    # FRESHNESS, not cleanliness. `counts_as_pass()` also requires the census
    # to have found nothing fixable, and that is the wrong question here: these
    # premises are about nltk's resolved version and whether a fix exists for
    # one advisory, which a census reporting seventeen other findings answers
    # perfectly well. Using counts_as_pass() made this step unsatisfiable while
    # ANY finding was open anywhere -- caught by probing the fresh case as well
    # as the stale one, which is the only reason it is not in this commit.
    if verdict.freshness() == module.LIVE and verdict.outcome != module.UNKNOWN:
        return ""
    if verdict.outcome == module.UNKNOWN:
        return (
            f"SEC-006: the census did not complete ({verdict.explain()}), so the "
            "nltk version and fix-availability premises are unconfirmed. This is "
            "not a failing scan and must not be read as one, nor as a pass."
        )
    return (
        f"SEC-006: the census is not a current answer ({verdict.explain()}). Its "
        "premises are about a LIVE advisory feed, so confirming them from an aged "
        "file asserts that nothing has changed since -- the one thing the file "
        "cannot say. Re-run "
        "`python3 scripts/vulnerability_census.py --check --scope core`."
    )


def _census_nltk_premises() -> list[str]:
    """What the census actually resolved for nltk, against what SEC-006 claims.

    Two premises, both of which the entry states and neither of which any
    check read until now:

      * the resolved version is 3.10.3 — a different one ships different code
        and a different advisory range;
      * no fix is available — the moment the advisory names a `fix_versions`,
        "no patched release exists" is false and a SUPPRESS becomes a choice
        not to take an available fix.
    """
    import json  # imported on this path only

    output = ROOT / _CENSUS_OUTPUT
    if not output.is_file():
        return [
            f"SEC-006: {_CENSUS_OUTPUT} is absent, so the nltk version and "
            "fix-availability premises cannot be confirmed. Run "
            "`python3 scripts/vulnerability_census.py --check --scope core` first "
            "— in the production gate it runs immediately before this step."
        ]
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"SEC-006: {_CENSUS_OUTPUT} could not be read ({exc}); premises unconfirmed."]

    # A census answer has a shelf life, and this was the second consumer of the
    # file not to check it. Measured 2026-10-16: a worktree holding a census
    # generated 2026-10-13 confirmed SEC-006's premises three days later, from
    # a file reporting `fixable_count: 17` -- the same seventeen advisories
    # src/immune/verdict.py was written about. In the production gate the census
    # runs immediately before this step, which is why it was never visible;
    # anywhere else -- a local run, a reordered job, a leftover file -- the
    # answer had unbounded age.
    stale = _census_staleness(output)
    if stale:
        return [stale]

    failures: list[str] = []
    seen = False
    for surface in data.get("surfaces") or []:
        for finding in (surface or {}).get("findings") or []:
            if (finding or {}).get("package") != "nltk":
                continue
            seen = True
            version = finding.get("version")
            if version != _SEC_006_MEASURED_NLTK:
                failures.append(
                    f"SEC-006: the census resolved nltk {version}, but the entry in "
                    f"{REGISTER} is written against {_SEC_006_MEASURED_NLTK} — its "
                    "advisory range and its 'latest release' claim are both about "
                    "that version. Re-assess before the suppression is relied on."
                )
            fixes = finding.get("fix_versions") or []
            if fixes:
                failures.append(
                    f"SEC-006: the advisory now names fixed version(s) {fixes}. "
                    f"The suppression in {REGISTER} rests on 'no patched release "
                    "exists'. One does, so this is no longer a suppression — it is a "
                    "fix waiting to be taken."
                )
    if not seen:
        # Not a failure: the finding is gone, which is the good outcome. Say so
        # rather than passing silently on a register entry that now describes
        # nothing.
        failures.append(
            f"SEC-006: the census no longer reports nltk at all. The entry in "
            f"{REGISTER} suppresses a finding that is not being raised — close it "
            "rather than leaving a live suppression for a risk that has gone."
        )
    return failures


def _is_tooling_manifest(path: Path) -> bool:
    """Does this manifest install tooling rather than a running service?"""
    return any(marker in path.name.lower() for marker in _TOOLING_MANIFEST_MARKERS)


def _declares_package(line: str, package: str) -> bool:
    """Is this requirements line a direct requirement on `package`?

    Generalised from the nltk-only reader when SEC-021 needed the same
    question asked about `mcp`. One reader, because two copies of "does this
    line declare a dependency" is exactly the shape that drifts: the weaker
    copy is the one a future advisory meets.
    """
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith("-"):
        return False
    # Strip environment markers, extras and any version specifier.
    name = re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0].strip()
    return name.lower().replace("_", "-") == package


def _declares_nltk(line: str) -> bool:
    """Is this requirements line a direct `nltk` requirement?"""
    return _declares_package(line, "nltk")


def _runtime_declarations(package: str) -> list[str]:
    """Runtime manifests that declare `package` directly.

    SEC-006's `Re-evaluate` row names "nltk becoming a declared runtime
    dependency" as a trigger, and said the row was enforced here. It was not
    — nothing read a manifest, so adding `nltk` to `requirements.txt` would
    have left this gate green while the entry claimed the opposite. A
    reviewer caught the claim outrunning the code, which is the same defect
    the entries themselves were corrected for.

    Parameterised by package name when SEC-021 brought a second entry resting
    on the same premise. The tooling-manifest exemption carries over for the
    same reason it was written: pinning the package in
    `requirements-security.txt` is how a future advisory gets remediated, and
    a check that failed on the remediation would push people the wrong way.
    """
    found: list[str] = []

    for path in ROOT.rglob("requirements*.txt"):
        if any(part in _SKIP for part in path.parts) or _is_tooling_manifest(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, start=1):
            if _declares_package(line, package):
                found.append(f"{path.relative_to(ROOT).as_posix()}:{number}")

    pyproject = ROOT / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib  # stdlib from 3.11, which CI runs

            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError, ModuleNotFoundError):
            data = {}
        project = data.get("project") or {}
        groups: list[tuple[str, object]] = [("dependencies", project.get("dependencies"))]
        for name, deps in (project.get("optional-dependencies") or {}).items():
            if not any(marker in name.lower() for marker in _TOOLING_MANIFEST_MARKERS):
                groups.append((f"optional-dependencies.{name}", deps))
        for label, deps in groups:
            if not isinstance(deps, list):
                continue
            for entry in deps:
                if isinstance(entry, str) and _declares_package(entry, package):
                    found.append(f"pyproject.toml [project.{label}]")

    return found


def _runtime_nltk_declarations() -> list[str]:
    """Runtime manifests that declare nltk directly."""
    return _runtime_declarations("nltk")


def check_sec_006() -> list[str]:
    """nltk stays a single lazy wordnet lookup, with no path-taking call.

    Three premises, matching the three the register's `Re-evaluate` row now
    names: the import surface, the absence of any path-taking call, and nltk
    not being a declared runtime dependency.
    """
    failures: list[str] = _census_nltk_premises()
    sites: list[str] = []

    for manifest in _runtime_nltk_declarations():
        failures.append(
            f"SEC-006: {manifest} declares `nltk` as a runtime dependency. The "
            f"suppression in {REGISTER} rests on nltk reaching the tree only "
            "transitively, through `safety`, and so shipping in no production image. "
            "Declaring it changes what is deployed and needs re-evaluating."
        )

    for path in _walk(ROOT, {".py"}):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        relative = path.relative_to(ROOT).as_posix()

        for lineno, module, lazy in _nltk_import_sites(tree):
            sites.append(f"{relative}:{lineno}")
            if not lazy:
                failures.append(
                    f"SEC-006: {relative}:{lineno} imports {module} at module level. "
                    f"The suppression in {REGISTER} rests on nltk being reached only "
                    "lazily; an import-time one means nltk now loads on every start."
                )
            if module != "nltk.corpus":
                failures.append(
                    f"SEC-006: {relative}:{lineno} imports {module}, not `nltk.corpus`. "
                    f"The suppression in {REGISTER} covers a wordnet synonym lookup "
                    "only. A wider surface is a different risk and needs re-evaluating."
                )

        # Lexical nesting alone does not make an import lazy: a function that
        # imports nltk, called at module level, runs that import on import.
        # The check was reading the shape of the code rather than when it runs.
        importers = _functions_importing_nltk(tree)
        if importers:
            for name in _import_time_calls(tree.body) & set(importers):
                failures.append(
                    f"SEC-006: {relative} calls `{name}()` at import time, and "
                    f"`{name}` (line {importers[name]}) imports nltk. The suppression "
                    f"in {REGISTER} rests on nltk being reached lazily; an import-time "
                    "call makes it eager however deeply the import is nested."
                )

        for lineno, call in _nltk_path_calls(tree):
            failures.append(
                f"SEC-006: {relative}:{lineno} calls {call}. PYSEC-2026-3740 is a "
                f"path-sandbox bypass, and the suppression in {REGISTER} states this "
                "repository never hands nltk a path. It now does."
            )

    if len(sites) > 1:
        failures.append(
            f"SEC-006: nltk is imported at {len(sites)} sites ({', '.join(sites)}). "
            f"The suppression in {REGISTER} rests on there being exactly one. Each new "
            "site is a use the disposition never assessed."
        )
    return failures


def _locked_versions() -> list[tuple[str, str]] | None:
    """Every `fflate` resolution in `web/`'s lockfile, as (path, version).

    A list, not a dict keyed by name. An npm lockfile can resolve the same
    package at several paths -- `node_modules/fflate` alongside
    `node_modules/posthog-js/node_modules/fflate` -- and keying by name made
    the last one encountered win. A patched top-level copy would then mask an
    affected nested one, and the check would pass with the vulnerable package
    still installed. A security check whose whole premise is that the lockfile
    is the authoritative installed graph cannot read only part of it.
    (codeant-ai on #1240.)
    """
    import json  # imported on this path only

    lock = ROOT / _WEB_LOCKFILE
    if not lock.is_file():
        return None
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    found: list[tuple[str, str]] = []
    for key, node in (data.get("packages") or {}).items():
        name = key.rsplit("node_modules/", 1)[-1] if "node_modules/" in key else None
        if name == _SEC_007_PACKAGE and isinstance(node, dict):
            version = node.get("version")
            if isinstance(version, str):
                found.append((key, version))
    return found


def _version_key(version: str) -> tuple[int, ...]:
    """npm semver core as a comparable tuple, prerelease suffix discarded.

    A prerelease (`0.4.9-beta.1`) sorts *below* its release under semver, and
    discarding the suffix would round it up to the fix. It is treated as the
    release below instead, so an unreleased build never reads as patched.
    """
    core = version.split("+", 1)[0]
    core, _, pre = core.partition("-")
    parts = [int(p) if p.isdigit() else 0 for p in core.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return (*parts[:3], 0 if pre else 1)


def _fflate_is_affected(version: str) -> bool:
    """True when `version` falls in any of the advisory's five ranges."""
    v = _version_key(version)
    return any(
        _version_key(introduced) <= v < _version_key(fixed)
        for introduced, fixed in _FFLATE_AFFECTED_RANGES
    )


def check_sec_007() -> list[str]:
    """`web/` installs an fflate outside every affected range of the advisory.

    This is deliberately not a pin. A pin asserts a version this document
    chose; the advisory asserts the versions that are broken. Checking the
    lockfile against the advisory is the only form of this check that stays
    correct when `posthog-js` moves fflate within its `^0.4.8` range — which
    is exactly what happened, unobserved, while the entry read ACCEPT.
    """
    failures: list[str] = []

    locked = _locked_versions()
    if locked is None:
        return [
            f"SEC-007: {_WEB_LOCKFILE} is missing or unreadable, so the fflate version "
            f"the RESOLVED disposition in {REGISTER} rests on cannot be confirmed."
        ]

    if not locked:
        # fflate gone from the tree entirely: the advisory cannot apply. Not a
        # failure -- a dependency being dropped is remediation, not regression.
        return failures

    affected = [(path, version) for path, version in locked if _fflate_is_affected(version)]
    if affected:
        fixes = ", ".join(fixed for _, fixed in _FFLATE_AFFECTED_RANGES)
        where = "; ".join(f"{path} -> {version}" for path, version in affected)
        failures.append(
            f"SEC-007: {_WEB_LOCKFILE} resolves `fflate` inside an affected range of "
            f"GHSA-px8p-9vwx-vf98 at {len(affected)} path(s): {where}. {REGISTER} records "
            f"this finding as RESOLVED on the strength of every installed copy being "
            f"patched. Move each to a fixed release ({fixes}) or re-open the entry -- do "
            "not amend it to assert the fix is unreachable, which is the error this entry "
            "already made once."
        )
    return failures


def _jwt_bound_names(tree: ast.AST) -> dict[str, object]:
    """Local names a JWT module is bound to here, plus directly imported `decode`.

    Matching four hard-coded receiver spellings was not enough: `from jose
    import jwt as verifier` makes `verifier.decode(...)` invisible, so a site
    could widen its allowlist to two algorithms and the gate would stay green
    having never looked at it. Raised by sourcery, codex and coderabbit on
    #1376, and reproduced -- `verifier.decode(t, k, algorithms=["HS256",
    "RS256"])` returned no sites at all.

    Resolves: import aliases (`from jose import jwt as verifier`), directly
    imported decoders (`from jose.jwt import decode`), aliased plain imports
    (`import jwt as j`), qualified receivers (`jose.jwt.decode(...)`) and
    simple assignment aliases (`verifier = jose.jwt`), chained to a fixed
    point so `v3 = v2` / `v2 = v1` / `v1 = jose.jwt` resolves `v3` too, and
    so does a re-aliased decoder (`d2 = d1` where `d1 = jwt.decode`).

    Because the walk enters every statement body, an assignment nested inside
    an `if`, `try`/`except`, `with` or loop is resolved as well. Measured, not
    assumed -- and worth stating, because the first wording of this bound said
    "a conditional" and so UNDERSTATED the coverage, which is the same defect
    as overstating it pointed the other way.

    Does NOT resolve: an alias reached through a container (`d = {"j": jwt}`),
    a call (`get().decode(...)`), a comprehension, or a conditional EXPRESSION
    (`v = jose.jwt if flag else None`) -- anything needing real dataflow. That
    is a bound on what this can claim, not a gap being hidden: SEC-020's entry
    states the same bound, so the claim matches the capability in both
    directions.
    """
    names: set[str] = set(_JWT_MODULE_NAMES)
    direct: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "jose" or module.startswith("jose") or "jwt" in module:
                for alias in node.names:
                    local = alias.asname or alias.name
                    if alias.name == "decode":
                        direct.add(local)
                    else:
                        names.add(local)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "jwt" in alias.name or alias.name.startswith("jose"):
                    names.add(alias.asname or alias.name.split(".")[0])

    # Simple assignment aliases: `verifier = jose.jwt`, `d = jwt.decode`.
    # Raised by coderabbit on #1376, correctly: resolving imports but not
    # assignments left `verifier.decode(...)` invisible, and the register
    # claims coverage of EVERY decode site. A claim with a known gap is the
    # defect this checker exists to prevent, so the claim and the capability
    # have to match.
    #
    # Repeated to a FIXED POINT, because an alias can be defined after another
    # alias it is built from. It was two passes, which silently stopped one hop
    # short: `v3 = v2` / `v2 = v1` / `v1 = jose.jwt` left `v3` unresolved, so
    # `v3.decode(...)` was invisible and could widen its allowlist unseen.
    # Raised by cubic on #1376 and reproduced. A fixed point needs no stated
    # cap, which is the point -- the previous cap was a limit the docstring
    # above did not mention, so the function claimed a coverage it did not have.
    #
    # It terminates: every pass only ADDS names, and the candidates are this
    # module's own assignment targets, a finite set. The assignments are
    # collected once rather than re-walked per pass.
    assignments: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        path = _receiver_path(node.value)
        if path is not None:
            assignments.append((target.id, path))

    while True:
        before = (len(names), len(direct))
        for name, path in assignments:
            segments = set(path.split("."))
            # `d2 = d1` where `d1` is already a bound decoder. Found by probing
            # the fixed point above: it chained module aliases and left this
            # one hop short, which is the same defect in the other half of the
            # loop -- `d2(t, k, algorithms=[...])` was invisible.
            if path in direct:
                direct.add(name)
                continue
            if not (segments & names or segments & {"jwt", "jose"}):
                continue
            if path.split(".")[-1] == "decode":
                direct.add(name)
            else:
                names.add(name)
        if (len(names), len(direct)) == before:
            break

    bound: dict[str, object] = dict.fromkeys(names, True)
    bound["__direct__"] = frozenset(direct)
    return bound


#: Shapes `check_sec_020` accepts. Named once so the classifier and its
#: consumer cannot drift: the previous pair was a literal tuple at the call
#: site and a docstring listing different values.
_ADMISSIBLE_SHAPES = ("literal", "constant", "parameter", "imported")


#: Nodes that introduce a name scope. A comprehension introduces one too, but
#: its targets are recorded as declarations in the enclosing scope instead
#: (see `_name_bindings`), which keeps the chain short and still fails closed.
_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

#: Scopes that have a parameter list.
_CALLABLE_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    """Each node's parent, by `id`. Built once per module, not per call site."""
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _enclosing_scopes(
    tree: ast.AST, target: ast.AST, parents: dict[int, ast.AST] | None = None
) -> list[ast.AST]:
    """`target`'s scope chain, innermost first, ending at the module.

    A class body is a scope only for code written DIRECTLY in it -- a method
    does not see class-level names unqualified -- so a `ClassDef` is kept only
    when it is the innermost scope and dropped from the rest of the chain.
    Keeping it would let a class attribute resolve a name that raises
    `NameError` at runtime, which is accepting code that cannot run.
    """
    if parents is None:
        parents = _parent_map(tree)
    chain: list[ast.AST] = []
    node: ast.AST | None = target
    while node is not None:
        if isinstance(node, _SCOPE_NODES) or node is tree:
            chain.append(node)
        node = parents.get(id(node))
    if not chain:  # pragma: no cover - the target always comes from this tree
        return [tree]
    return [chain[0]] + [s for s in chain[1:] if not isinstance(s, ast.ClassDef)]


def _scope_local_nodes(scope: ast.AST) -> list[ast.AST]:
    """Every node inside `scope`, WITHOUT descending into a nested scope.

    This is the whole point of the function. `ast.walk` over the module sees
    every function's parameters at once, so an unrelated
    `def helper(algorithm="HS256")` elsewhere in the file laundered every
    same-named parameter at every decode site -- the module-global resolution
    codeant raised on #1376, reproduced before fixing:

        scope leak -> [(6, 'parameter', 1)]
        isolated   -> [(2, "algorithm 'algorithm' is not bound ...", -1)]

    Statement bodies (`if`, `try`, `with`, `for`, `while`) ARE descended into:
    they open no scope, and a binding inside one is a binding of this scope.
    """
    collected: list[ast.AST] = []
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        collected.append(node)
        if isinstance(node, _SCOPE_NODES):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return collected


def _parameter_defaults(args: ast.arguments) -> list[tuple[ast.arg, ast.expr | None]]:
    """Every parameter of one signature, paired with its default or `None`.

    `None` means "declared, with no value this checker can read". It is
    returned rather than omitted because a parameter with no default has
    nothing verified about it at all, and because the name still SHADOWS
    whatever an enclosing scope holds -- so resolution has to stop at it.
    """
    positional = list(args.posonlyargs) + list(args.args)
    split = len(positional) - len(args.defaults)
    pairs: list[tuple[ast.arg, ast.expr | None]] = [(arg, None) for arg in positional[:split]]
    # Defaults align to the END of the positional list.
    # strict=True: the slice is built to match `defaults` exactly, and
    # `kw_defaults` is spec'd to align 1:1 with `kwonlyargs`. If either ever
    # does not, that is a wrong assumption about the AST and should raise here
    # rather than silently drop the tail -- a dropped default is a name this
    # checker then reports as unbound.
    pairs += list(zip(positional[split:], args.defaults, strict=True))
    pairs += list(zip(args.kwonlyargs, args.kw_defaults, strict=True))
    pairs += [(extra, None) for extra in (args.vararg, args.kwarg) if extra is not None]
    return pairs


def _name_bindings(scope: ast.AST) -> dict[str, list[ast.expr | None]]:
    """Every value a bare name is bound to IN ONE SCOPE.

    Collects this scope's own parameters, plain assignments, annotated
    assignments and walrus targets, plus the binding targets whose value this
    checker does not read -- loop, `with`, `except` and comprehension targets,
    augmented assignments, and unpacking. A name with several bindings yields
    all of them, because the weakest one is what decides the verdict.

    A `None` entry means the name is declared here with no readable value. It
    is recorded rather than omitted so that resolution STOPS at this scope: at
    runtime such a binding shadows anything an enclosing scope holds, and
    quietly looking past it is how the module-global version accepted a name
    it had never resolved.

    A `global` or `nonlocal` statement records nothing, so resolution continues
    outward -- which is what happens at runtime.
    """
    bindings: dict[str, list[ast.expr | None]] = {}

    def _add(name: str, value: ast.expr | None) -> None:
        bindings.setdefault(name, []).append(value)

    def _declare(target: ast.expr | None) -> None:
        """Record a binding target whose value is not read.

        Only names actually rebound are recorded. `obj.attr = x` and
        `d[k] = x` bind no name, so they are ignored rather than marking
        `obj`/`d` unresolvable and causing a false refusal.
        """
        if isinstance(target, ast.Name):
            _add(target.id, None)
        elif isinstance(target, ast.Starred):
            _declare(target.value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                _declare(item)

    if isinstance(scope, _CALLABLE_SCOPES):
        for arg, default in _parameter_defaults(scope.args):
            _add(arg.arg, default)

    for node in _scope_local_nodes(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    _add(target.id, node.value)
                else:
                    _declare(target)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            _add(node.target.id, node.value)
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            _add(node.target.id, node.value)
        elif isinstance(node, ast.AugAssign):
            _declare(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            _declare(node.target)
        elif isinstance(node, ast.comprehension):
            _declare(node.target)
        elif isinstance(node, ast.withitem):
            _declare(node.optional_vars)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            _add(node.name, None)
    return bindings


def _imported_literal(name: str, tree: ast.AST, source: Path | None) -> bool | None:
    """Whether `name` is imported from a sibling module that binds it to a literal.

    ONE hop, deliberately. `workers/infinity-auth/service.py` does
    `from config import JWT_ALGORITHM` and `config.py:21` sets it to `"HS256"`,
    so the value is knowable and refusing it would be a false alarm -- but
    chasing a chain of re-exports is dataflow analysis by another name, and the
    bound has to stay somewhere a reader can check.

    The module path is resolved as written, dotted first: a bare basename is
    only tried when the module name HAS no dots, so a sibling file cannot
    stand in for a package module of the same leaf name.

    Returns True (resolved to a literal), False (resolved to something else) or
    None (could not resolve: no path, module not found, name not bound there).
    None is NOT "fine" -- the caller refuses it, per `IMMUNE-SYSTEM.md`'s rule
    that a check which could not look must not read as a check that looked.
    """
    if source is None:
        return None
    module: str | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if any((alias.asname or alias.name) == name for alias in node.names):
                module = node.module
                break
    if module is None:
        return None

    # The DOTTED path first, and the bare-basename shortcut only for a module
    # with no dots at all. It used to try the basename first, which resolved
    # `from pkg.config import ALG` against any sibling `config.py` -- a
    # different module, for a different binding. Raised by cubic on #1376 and
    # reproduced: the sibling bound `ALG = "HS256"`, the real `pkg/config.py`
    # bound it to `get_unverified_header(t)["alg"]`, and the site was accepted
    # as `imported`. The checker had measured the wrong file and reported the
    # answer as if it were the right one.
    #
    # `workers/infinity-auth/service.py` does `from config import
    # JWT_ALGORITHM` -- no dot -- so the shortcut it needs is kept, and only
    # for the case where the basename IS the module.
    parts = module.split(".")
    candidates = [
        source.parent / Path(*parts).with_suffix(".py"),
        ROOT / Path(*parts).with_suffix(".py"),
    ]
    if len(parts) == 1:
        candidates.append(source.parent / f"{parts[0]}.py")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            other = ast.parse(candidate.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            return None
        bindings = _name_bindings(other).get(name)
        if not bindings:
            return None
        return all(isinstance(v, ast.Constant) and isinstance(v.value, str) for v in bindings)
    return None


def _algorithm_shape(
    element: ast.expr,
    tree: ast.AST | None = None,
    source: Path | None = None,
    scopes: list[ast.AST] | None = None,
) -> tuple[str, int]:
    """Classify the sole `algorithms=` entry as (shape, count).

    Counting AST elements was the first version's defect: it reported
    `algorithms=[get_unverified_header(token)["alg"]]` as *pinned*, which is
    the attack verbatim -- the token picks the algorithm while the verifier
    holds an asymmetric key. Raised by sourcery, codex, coderabbit and codeant
    on #1376, all correctly, and reproduced before fixing.

    The SECOND version had a subtler form of the same defect, raised by codeant
    on the same PR and reproduced: it accepted ANY bare name as `reference`,
    having only claimed that such a name resolves to something this code
    chooses. It did not check. So the rejected attack needed moving up one
    line to pass:

        alg = jwt.get_unverified_header(t)["alg"]   # the token picks it
        jwt.decode(t, k, algorithms=[alg])          # -> accepted

    The name is now RESOLVED against the module's own bindings. Three shapes
    are admissible, reported apart because they are not equally strong:

      * `literal`   -- a string constant; the allowlist is in the source.
      * `constant`  -- a name bound only to string literals in this module.
      * `parameter` -- a function parameter whose default is a string literal.
        Weaker on purpose: the DEFAULT is verified, the call sites are not.
        Four of this estate's decode sites are of this shape.

    The THIRD version fixed where it looks. The second resolved names against
    the whole module, so an unrelated default elsewhere in the file laundered
    every same-named parameter -- a bypass of the fix above, raised by codeant
    and reproduced. Resolution now walks the decode site's own scope chain,
    innermost first, and stops at the first scope that declares the name,
    because that is the binding in force at runtime.

    Everything else is rejected, including a name this module does not bind and
    a dotted attribute, both of which are unresolvable from here. Failing
    closed on what it cannot see is `IMMUNE-SYSTEM.md`'s rule for sensors,
    applied to an allowlist check: "I could not look" must never read the same
    as "I looked and it was fine".
    """
    if isinstance(element, ast.Constant):
        if isinstance(element.value, str):
            return "literal", 1
        return f"algorithm is a non-string constant {element.value!r}", -1

    if not isinstance(element, ast.Name):
        if isinstance(element, ast.Attribute):
            return (
                "algorithm is a dotted attribute, which this check cannot "
                "resolve -- bind it to a module constant instead",
                -1,
            )
        return "algorithm is computed, so the token could choose it", -1

    if tree is None:  # pragma: no cover - every caller passes the tree
        return "algorithm reference could not be resolved: no module tree", -1
    if not scopes:
        scopes = [tree]

    # Innermost scope first, stopping at the first one that DECLARES the name:
    # that is the binding in force where the decode call sits. Looking past it
    # into an outer scope is the module-global bypass this version fixes.
    for scope in scopes:
        bindings = _name_bindings(scope).get(element.id)
        if bindings is None:
            continue
        # The weakest binding decides. One literal binding does not make a name
        # safe if another assignment computes it.
        if all(isinstance(v, ast.Constant) and isinstance(v.value, str) for v in bindings):
            return ("parameter" if _is_parameter(element.id, scope) else "constant"), 1
        if all(v is None for v in bindings) and _is_parameter(element.id, scope):
            return (
                f"algorithm {element.id!r} is a parameter with no default, so its "
                "callers choose it and this check cannot see what they pass",
                -1,
            )
        if any(v is None for v in bindings):
            return (
                f"algorithm {element.id!r} is bound to a target this check does "
                "not read, so the token could choose it",
                -1,
            )
        return (
            f"algorithm {element.id!r} is bound to a computed value, so the token could choose it",
            -1,
        )

    imported = _imported_literal(element.id, tree, source)
    if imported is True:
        return "imported", 1
    if imported is False:
        return (
            f"algorithm {element.id!r} is imported from a module that does "
            "not bind it to a string literal",
            -1,
        )
    return (
        f"algorithm {element.id!r} is not bound in this module and could "
        "not be resolved to one it is imported from",
        -1,
    )


def _is_parameter(name: str, scope: ast.AST) -> bool:
    """Whether `name` is a parameter of THIS scope.

    It used to be "a parameter anywhere in this module", which is the bypass
    codeant raised on #1376: any one default launders every same-named
    parameter in the file, including parameters of functions that have none.
    """
    if not isinstance(scope, _CALLABLE_SCOPES):
        return False
    return any(arg.arg == name for arg, _ in _parameter_defaults(scope.args))


def _receiver_path(node: ast.expr) -> str | None:
    """The dotted receiver of a call, e.g. "jose.jwt" for `jose.jwt.decode(...)`.

    Requiring a bare `ast.Name` receiver missed every qualified spelling:
    `jose.jwt.decode(...)` has an `ast.Attribute` base, so the site was skipped
    entirely and a widened allowlist written that way would never be seen.
    Raised by `llamapreview` on #1376.
    """
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _algorithm_of(
    node: ast.Call,
    tree: ast.AST,
    source: Path | None = None,
    parents: dict[int, ast.AST] | None = None,
) -> tuple[str, int]:
    """Shape of a `decode(...)` call's `algorithms=` argument.

    Used for both call spellings -- a directly-imported `decode(...)` and a
    qualified `jwt.decode(...)` / `jose.jwt.decode(...)` -- so the two cannot
    disagree about what an acceptable allowlist looks like.
    """
    keyword = next((k for k in node.keywords if k.arg == "algorithms"), None)
    if keyword is None:
        return "no algorithms= argument at all", 0
    if not isinstance(keyword.value, ast.List):
        return "algorithms= is not a literal list", -1
    if len(keyword.value.elts) != 1:
        return "algorithms= names more than one", len(keyword.value.elts)
    scopes = _enclosing_scopes(tree, node, parents)
    return _algorithm_shape(keyword.value.elts[0], tree, source, scopes)


def _jwt_decode_sites(tree: ast.AST, source: Path | None = None) -> list[tuple[int, str, int]]:
    """(line, shape, count) for every JWT decode call in one module.

    Three shapes are admissible -- `_ADMISSIBLE_SHAPES`, which `check_sec_020`
    tests against so the two cannot disagree:

    - "literal"   -- one algorithm, written as a string literal in the list
    - "constant"  -- a name bound only to string literals in this module
    - "parameter" -- a function parameter whose default is a string literal

    Anything else is a refusal naming what is wrong: an absent `algorithms=`
    (python-jose then accepts whatever the token asks for), a non-literal list
    the AST cannot read, a list naming more than one, or a single element that
    is computed -- a token-derived element is the algorithm-confusion bug the
    allowlist exists to prevent, so it is rejected rather than counted.

    There is no "pinned" shape. It was replaced by the literal/reference split
    because "exactly one element" is not the property that matters: one
    token-derived element pins nothing.
    """
    bound = _jwt_bound_names(tree)
    # One parent map for the whole module: every decode site's scope chain is
    # read from it, so adding sites does not re-walk the tree per site.
    parents = _parent_map(tree)
    sites: list[tuple[int, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in bound["__direct__"]:
            sites.append((node.lineno, *_algorithm_of(node, tree, source, parents)))
            continue
        if not isinstance(func, ast.Attribute) or func.attr != "decode":
            continue
        path = _receiver_path(func.value)
        if path is None:
            continue
        segments = set(path.split("."))
        # A bare bound name (`jwt`, or an alias resolved from the imports), or
        # any qualified spelling whose segments name a JWT module.
        if not (segments & set(bound) or segments & {"jwt", "jose"}):
            continue
        # Same analysis as the direct-import branch above, so the same function.
        # It was a verbatim second copy -- including the three message strings
        # -- until review pointed out that two copies of an allowlist check can
        # drift, which is the one thing this checker must not do.
        sites.append((node.lineno, *_algorithm_of(node, tree, source, parents)))
    return sites


def _census_jose_premises() -> list[str]:
    """What the census resolved for python-jose, against what SEC-020 claims.

    Same two premises as SEC-006, for the same reason: a SUPPRESS is only
    honest while the version is the one assessed and no fix exists.
    """
    import json  # imported on this path only

    output = ROOT / _CENSUS_OUTPUT
    if not output.is_file():
        return [
            f"SEC-020: {_CENSUS_OUTPUT} is absent, so the {_SEC_020_PACKAGE} version "
            "and fix-availability premises cannot be confirmed. Run "
            "`python3 scripts/vulnerability_census.py --check --scope core` first."
        ]
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"SEC-020: {_CENSUS_OUTPUT} could not be read ({exc}); premises unconfirmed."]

    failures: list[str] = []
    seen = False
    for surface in data.get("surfaces") or []:
        for finding in (surface or {}).get("findings") or []:
            if (finding or {}).get("package") != _SEC_020_PACKAGE:
                continue
            identifiers = {
                str((finding or {}).get("id") or "").upper(),
                *(str(a).upper() for a in ((finding or {}).get("aliases") or [])),
            }
            if not (_SEC_020_ADVISORY_IDS & identifiers):
                continue  # a different python-jose advisory, not this premise
            seen = True
            version = finding.get("version")
            if version != _SEC_020_MEASURED_JOSE:
                failures.append(
                    f"SEC-020: the census resolved {_SEC_020_PACKAGE} {version}, but the "
                    f"entry in {REGISTER} is written against {_SEC_020_MEASURED_JOSE}. "
                    "Re-assess before the suppression is relied on."
                )
            fixes = finding.get("fix_versions") or []
            if fixes:
                failures.append(
                    f"SEC-020: the advisory now names fixed version(s) {fixes}. The "
                    f"suppression in {REGISTER} rests on 'no patched release exists'. "
                    "One does, so this is a fix waiting to be taken, not a suppression."
                )
    if not seen:
        failures.append(
            f"SEC-020: the census no longer reports {_SEC_020_PACKAGE} at all. Close the "
            f"entry in {REGISTER} rather than leaving a live suppression for a risk that "
            "has gone."
        )
    return failures


def _declared_jose_versions() -> list[str]:
    """Every manifest pin of python-jose, read from the manifests themselves.

    The census runs `--scope core`, which does not cover the worker manifests,
    so SEC-020's "any version other than 3.5.0" trigger was unenforced for
    seven of the eight files that pin this package. A worker could have been
    moved to a different version while the checker went on reading the root
    finding and passing. Raised by `chatgpt-codex-connector` on #1376.
    """
    failures: list[str] = []
    seen = 0
    for relative in _SEC_020_MANIFESTS:
        path = ROOT / relative
        if not path.is_file():
            failures.append(
                f"SEC-020: {relative} is named in this check's manifest list but is not "
                "in the tree. Either it moved, in which case the list is stale, or the "
                "pin it carried is gone -- re-assess rather than skipping it."
            )
            continue
        pins = _JOSE_PIN.findall(path.read_text(encoding="utf-8"))
        if not pins:
            failures.append(
                f"SEC-020: {relative} no longer pins python-jose. The entry in {REGISTER} "
                "lists it as one of the places the assessed version is pinned; drop it "
                "from the list deliberately rather than leaving the claim unverified."
            )
            continue
        for pin in pins:
            seen += 1
            if pin != _SEC_020_MEASURED_JOSE:
                failures.append(
                    f"SEC-020: {relative} pins python-jose {pin}, but the entry in "
                    f"{REGISTER} is assessed against {_SEC_020_MEASURED_JOSE}. A "
                    "different version ships different code and a different advisory "
                    "range. Re-assess before the suppression is relied on."
                )
    if not failures and seen == 0:
        failures.append(
            "SEC-020: no python-jose pin was found in any listed manifest, so the "
            "version premise rests on nothing. Re-assess."
        )
    return failures


#: The pinned-site count `check_sec_020` measured on this run. Held here so the
#: pass message can report it without a second full-tree walk --
#: `_pinned_decode_sites` used to re-parse every `.py` file purely to format
#: that line, roughly doubling the script's cost. Raised by cubic on #1376.
_SEC_020_PINNED: list[int] = []


def check_sec_020() -> list[str]:
    """python-jose algorithm confusion: no fix exists, and no site can reach it."""
    failures = _census_jose_premises() + _declared_jose_versions()

    pinned = 0
    for path in _walk(ROOT, {".py"}):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            # Not this check's business to police unparseable files; other
            # guards do that. Silence here would hide a decode site, so say so.
            failures.append(
                f"SEC-020: {path.relative_to(ROOT)} could not be parsed, so any JWT "
                "decode site in it is unexamined. The premise covers every site or none."
            )
            continue
        for line, shape, count in _jwt_decode_sites(tree, path):
            if shape in _ADMISSIBLE_SHAPES:
                pinned += 1
                continue
            detail = f" ({count})" if count > 1 else ""
            failures.append(
                f"SEC-020: {path.relative_to(ROOT)}:{line} — {shape}{detail}. The "
                f"suppression in {REGISTER} rests on every decode site naming exactly "
                "one algorithm, which is what makes the DER-encoded-public-key "
                "confusion unreachable. This site does not."
            )

    _SEC_020_PINNED[:] = [pinned]
    if not failures and pinned == 0:
        failures.append(
            f"SEC-020: no JWT decode site was found at all. The entry in {REGISTER} "
            "argues from twelve of them; a premise about code that is not there "
            "describes nothing. Re-assess."
        )
    return failures


def _pinned_decode_sites() -> int:
    """The count `check_sec_020` measured on this run.

    Reported rather than re-derived: this used to walk and parse every `.py`
    file a second time just to format the pass line, duplicating the walk
    `check_sec_020` had already completed.
    """
    return _SEC_020_PINNED[0] if _SEC_020_PINNED else 0


def _mcp_imports_in(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, description) for every import of the `mcp` package in one module.

    Split out from the walk so it can be tested against source strings rather
    than against whatever happens to be in the tree today — the same shape as
    `_jwt_decode_sites`, and for the same reason: a premise checker is only
    worth having if the discrimination it claims can be demonstrated.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "mcp" or alias.name.startswith("mcp."):
                    found.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            # `level > 0` is a relative import — `from .mcp import x` inside a
            # package is this repository's own module, not the package. And
            # `src.mcp` is The Spark, which shares the name and none of the code.
            module = node.module or ""
            if node.level == 0 and (module == "mcp" or module.startswith("mcp.")):
                found.append((node.lineno, f"from {module} import ..."))
    return found


def _mcp_import_sites() -> list[str]:
    """Every import of the `mcp` PyPI package in this repository.

    SEC-021 rests on the package being installed only into the security
    tooling and never reached from this code. The name makes that easy to get
    wrong by eye: `src/mcp/` is this estate's own MCP server (The Spark), and
    it is imported as `src.mcp`. A bare `import mcp` is the distribution with
    the advisory, not that package, because Python 3 imports are absolute.

    So the AST is read rather than the text: a string containing "import mcp"
    in a docstring or a test fixture is not an import, and the register has
    already been bitten once by a reader that could not tell the difference.
    """
    sites: list[str] = []
    for path in _walk(ROOT, {".py"}):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue  # other guards police unparseable files; see check_sec_020
        relative = path.relative_to(ROOT).as_posix()
        sites.extend(f"{relative}:{line} ({what})" for line, what in _mcp_imports_in(tree))
    return sites


def _census_mcp_premises() -> list[str]:
    """What the census resolved for mcp, against what SEC-021 claims.

    Mirrored from `_census_jose_premises`, with the fix-availability test
    inverted — see `_SEC_021_MEASURED_MCP` for why that inversion is the
    point of a `Blocked-by` entry rather than an oversight.
    """
    import json  # imported on this path only

    output = ROOT / _CENSUS_OUTPUT
    if not output.is_file():
        return [
            f"SEC-021: {_CENSUS_OUTPUT} is absent, so the {_SEC_021_PACKAGE} version "
            "and fix-reachability premises cannot be confirmed. Run "
            "`python3 scripts/vulnerability_census.py --check --scope core` first."
        ]
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"SEC-021: {_CENSUS_OUTPUT} could not be read ({exc}); premises unconfirmed."]

    failures: list[str] = []
    seen = False
    for surface in data.get("surfaces") or []:
        for finding in (surface or {}).get("findings") or []:
            if (finding or {}).get("package") != _SEC_021_PACKAGE:
                continue
            identifiers = {
                str((finding or {}).get("id") or "").upper(),
                *(str(a).upper() for a in ((finding or {}).get("aliases") or [])),
            }
            if not (_SEC_021_ADVISORY_IDS & identifiers):
                continue  # a different mcp advisory, not this premise
            seen = True
            version = finding.get("version")
            if version != _SEC_021_MEASURED_MCP:
                failures.append(
                    f"SEC-021: the census resolved {_SEC_021_PACKAGE} {version}, but the "
                    f"entry in {REGISTER} is written against {_SEC_021_MEASURED_MCP}. "
                    "semgrep's exact pin is the only thing holding it there, so this "
                    "means the pin moved — re-read `Requires-Dist: mcp` and close the "
                    "entry if a patched release is now reachable."
                )
            if not (finding.get("fix_versions") or []):
                failures.append(
                    "SEC-021: the advisory no longer names any fixed version. The "
                    f"`Blocked-by` row in {REGISTER} says a fix exists and cannot be "
                    "reached; with no fix at all this is a SUPPRESS on SEC-006's terms, "
                    "and the distinction is what keeps the gate failing the day one ships."
                )
    if not seen:
        failures.append(
            f"SEC-021: the census no longer reports this {_SEC_021_PACKAGE} advisory. "
            f"Close the entry in {REGISTER} rather than leaving a blocked-by label on a "
            "finding that has gone — most likely because semgrep relaxed its pin and a "
            "patched version resolved, which is the outcome the entry is waiting for."
        )
    return failures


def check_sec_021() -> list[str]:
    """mcp stays a security-tooling transitive, unimported and undeclared.

    Three premises, matching the three the register's `Re-evaluate` row claims
    are enforced here: the resolved version with its fix still unreachable,
    the absence of any runtime declaration, and the absence of any import of
    the package anywhere in the tree.
    """
    failures = _census_mcp_premises()

    for manifest in _runtime_declarations(_SEC_021_PACKAGE):
        failures.append(
            f"SEC-021: {manifest} declares `{_SEC_021_PACKAGE}` as a runtime dependency. "
            f"The entry in {REGISTER} rests on the package reaching this tree only "
            "through the security tooling, so it is absent from a production install "
            "entirely. That is no longer true."
        )

    for site in _mcp_import_sites():
        failures.append(
            f"SEC-021: {site} imports the `{_SEC_021_PACKAGE}` package. The entry in "
            f"{REGISTER} rests on nothing here importing it — the vulnerable surface is "
            "the SDK's StreamableHTTP server transport, which this repository never "
            "starts. An import is how that stops being true."
        )

    return failures


def main() -> int:
    failures = check_sec_006() + check_sec_007() + check_sec_020() + check_sec_021()
    if failures:
        print(
            "[ERROR] A recorded disposition rests on a premise that no longer holds.\n"
            "        The finding is not suppressed by this — re-open it, or amend the\n"
            f"        entry in {REGISTER} to match what the code now does.\n"
        )
        for failure in failures:
            print(f"  {failure}")
        return 1
    locked = _locked_versions() or []
    fflate = ", ".join(sorted({version for _, version in locked})) or "absent"
    print(
        "Disposition premises: PASSED — SEC-006 (nltk 3.10.3 with no fix available, "
        "undeclared in runtime manifests, reached lazily, wordnet only, no path call), "
        f"SEC-007 (web/ resolves fflate {fflate}, outside every affected range of "
        "GHSA-px8p-9vwx-vf98), SEC-020 (python-jose 3.5.0 with no fix available, "
        f"{_pinned_decode_sites()} JWT decode sites all naming exactly one algorithm), "
        f"and SEC-021 (mcp {_SEC_021_MEASURED_MCP} with a published fix still behind "
        "semgrep's exact pin, undeclared in runtime manifests, imported nowhere) "
        "all still hold"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
