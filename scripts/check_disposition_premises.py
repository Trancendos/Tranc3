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
    import json  # noqa: PLC0415 - only needed on this path

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


def _declares_nltk(line: str) -> bool:
    """Is this requirements line a direct `nltk` requirement?"""
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith("-"):
        return False
    # Strip environment markers, extras and any version specifier.
    name = re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0].strip()
    return name.lower().replace("_", "-") == "nltk"


def _runtime_nltk_declarations() -> list[str]:
    """Runtime manifests that declare nltk directly.

    SEC-006's `Re-evaluate` row names "nltk becoming a declared runtime
    dependency" as a trigger, and said the row was enforced here. It was not
    — nothing read a manifest, so adding `nltk` to `requirements.txt` would
    have left this gate green while the entry claimed the opposite. A
    reviewer caught the claim outrunning the code, which is the same defect
    the entries themselves were corrected for.
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
            if _declares_nltk(line):
                found.append(f"{path.relative_to(ROOT).as_posix()}:{number}")

    pyproject = ROOT / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib  # noqa: PLC0415 - stdlib from 3.11, which CI runs

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
                if isinstance(entry, str) and _declares_nltk(entry):
                    found.append(f"pyproject.toml [project.{label}]")

    return found


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
    import json  # noqa: PLC0415 - only needed on this path

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
    simple assignment aliases (`verifier = jose.jwt`).

    Does NOT resolve: an alias reached through a container, a call, a
    comprehension or a conditional -- anything needing real dataflow. That is
    a bound on what this can claim, not a gap being hidden: SEC-020's entry
    says the checker resolves imports and simple assignments, so the claim
    matches the capability rather than overstating it.
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
    # Two passes, because an alias can be defined after another alias it is
    # built from. Deliberately NOT general dataflow -- see the module note
    # below on what this does and does not resolve.
    for _ in range(2):
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            path = _receiver_path(node.value)
            if path is None:
                continue
            segments = set(path.split("."))
            if path.split(".")[-1] == "decode" and (segments & names or segments & {"jwt", "jose"}):
                direct.add(target.id)
            elif segments & names or segments & {"jwt", "jose"}:
                names.add(target.id)

    bound: dict[str, object] = dict.fromkeys(names, True)
    bound["__direct__"] = frozenset(direct)
    return bound


def _algorithm_shape(element: ast.expr) -> tuple[str, int]:
    """Classify the sole `algorithms=` entry as (shape, count).

    Counting AST elements was the first version's defect: it reported
    `algorithms=[get_unverified_header(token)["alg"]]` as *pinned*, which is
    the attack verbatim -- the token picks the algorithm while the verifier
    holds an asymmetric key. Raised by sourcery, codex, coderabbit and codeant
    on #1376, all correctly, and reproduced before fixing.

    Two shapes are admissible, reported apart because they are not equally
    strong:

      * `literal`   -- a string constant; the allowlist is in the source.
      * `reference` -- a bare name or dotted attribute, resolving to a module
        constant or parameter default. Chosen by this code, never by the token.

    Anything else is rejected: a call, subscript, f-string, starred or computed
    expression could all take their value from the token.
    """
    if isinstance(element, ast.Constant):
        if isinstance(element.value, str):
            return "literal", 1
        return f"algorithm is a non-string constant {element.value!r}", -1
    root = element
    while isinstance(root, ast.Attribute):
        root = root.value
    if isinstance(root, ast.Name):
        return "reference", 1
    return "algorithm is computed, so the token could choose it", -1


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


def _algorithm_of(node: ast.Call) -> tuple[str, int]:
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
    return _algorithm_shape(keyword.value.elts[0])


def _jwt_decode_sites(tree: ast.AST) -> list[tuple[int, str, int]]:
    """(line, shape, count) for every JWT decode call in one module.

    Two shapes are admissible, and `check_sec_020` accepts exactly these:

    - "literal"   -- one algorithm, written as a string literal in the list
    - "reference" -- one algorithm, a module-level name the AST can see

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
    sites: list[tuple[int, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in bound["__direct__"]:
            sites.append((node.lineno, *_algorithm_of(node)))
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
        sites.append((node.lineno, *_algorithm_of(node)))
    return sites


def _census_jose_premises() -> list[str]:
    """What the census resolved for python-jose, against what SEC-020 claims.

    Same two premises as SEC-006, for the same reason: a SUPPRESS is only
    honest while the version is the one assessed and no fix exists.
    """
    import json  # noqa: PLC0415 - only needed on this path

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
        for line, shape, count in _jwt_decode_sites(tree):
            if shape in ("literal", "reference"):
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


def main() -> int:
    failures = check_sec_006() + check_sec_007() + check_sec_020()
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
        "GHSA-px8p-9vwx-vf98), and SEC-020 (python-jose 3.5.0 with no fix available, "
        f"{_pinned_decode_sites()} JWT decode sites all naming exactly one algorithm) "
        "all still hold"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
