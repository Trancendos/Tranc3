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
      Accepted because the vulnerable path is `unzipSync` parsing malformed
      ZIP64 archives, and `web/` never decompresses — `posthog-js` uses
      fflate only to compress outbound data. That second half was measured
      by reading the shipped code of ONE version, `posthog-js@1.422.5`, so
      it is a fact about that version and not about posthog-js in general.

Each entry's `Re-evaluate` row listed only version and dependency triggers: a
new nltk release, a widened `posthog-js` range. Neither covered the premise the
reasoning actually rests on. Someone adding `nltk.data.load(user_path)`, or a
decompression path in `web/`, would void the justification while the
disposition kept the finding suppressed and the gate kept passing — a control
still reporting green about a fact that had stopped being true.

CodeRabbit raised exactly this on PR #1152. Extending the prose alone would
have been the same defect one level up: a re-evaluation trigger nobody checks
is not a trigger. This script is what checks them.

Standard library only: the production gate installs little else.
"""

from __future__ import annotations

import ast
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

#: fflate's decompression surface. `posthog-js` calls only the compression
#: side, which is why SEC-007 holds.
_FFLATE_DECOMPRESS = (
    "unzipSync",
    "unzip(",
    "decompressSync",
    "decompress(",
    "gunzipSync",
    "gunzip(",
    "inflateSync",
    "inflate(",
    "unzlibSync",
    "unzlib(",
)

_WEB_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".svelte", ".vue"}

#: The exact versions SEC-007's call-site evidence was read from. The entry
#: records "Measured on web/node_modules/posthog-js@1.422.5" — two import
#: sites, `gzipSync`/`strToU8`/`strFromU8` only, zero decompression entry
#: points. That is a fact about 1.422.5. A different version ships different
#: code, and the measurement would have to be redone before the acceptance
#: means anything; CI has no `node_modules` to re-read it from, so the
#: lockfile pin is what makes the evidence checkable at all.
_SEC_007_MEASURED = {"posthog-js": "1.422.5", "fflate": "0.4.8"}
_WEB_LOCKFILE = "web/package-lock.json"


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


def check_sec_006() -> list[str]:
    """nltk stays a single lazy wordnet lookup, with no path-taking call."""
    failures: list[str] = []
    sites: list[str] = []

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


def _locked_versions() -> dict[str, str] | None:
    """`web/`'s lockfile resolutions for the packages SEC-007 rests on."""
    import json  # noqa: PLC0415 - only needed on this path

    lock = ROOT / _WEB_LOCKFILE
    if not lock.is_file():
        return None
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    found: dict[str, str] = {}
    for key, node in (data.get("packages") or {}).items():
        name = key.rsplit("node_modules/", 1)[-1] if "node_modules/" in key else None
        if name in _SEC_007_MEASURED and isinstance(node, dict):
            version = node.get("version")
            if isinstance(version, str):
                found[name] = version
    return found


def check_sec_007() -> list[str]:
    """`web/` compresses with fflate and never decompresses.

    Two premises, and the second is the one a reviewer caught the entry
    over-stating: the "never decompresses" conclusion was established by
    reading `posthog-js@1.422.5`'s shipped code, so it is scoped to that
    version. CI has no `node_modules` to re-read, which is exactly why the
    lockfile pin has to be the thing that is checked.
    """
    failures: list[str] = []

    locked = _locked_versions()
    if locked is None:
        failures.append(
            f"SEC-007: {_WEB_LOCKFILE} is missing or unreadable, so the versions the "
            f"call-site evidence in {REGISTER} was measured on cannot be confirmed. "
            "The acceptance rests on that measurement."
        )
    else:
        for package, measured in _SEC_007_MEASURED.items():
            actual = locked.get(package)
            if actual is None:
                failures.append(
                    f"SEC-007: `{package}` is no longer in {_WEB_LOCKFILE}. The "
                    f"acceptance in {REGISTER} describes a risk that may no longer "
                    "exist — close the entry rather than leaving it asserting one."
                )
            elif actual != measured:
                failures.append(
                    f"SEC-007: {_WEB_LOCKFILE} resolves `{package}` to {actual}, but the "
                    f"evidence in {REGISTER} was measured on {measured}. A different "
                    "version ships different code; the call sites have to be re-read "
                    "before the acceptance means anything."
                )
    for path in _walk(ROOT / "web", _WEB_SUFFIXES):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "fflate" not in text and "pako" not in text:
            continue
        for token in _FFLATE_DECOMPRESS:
            if token in text:
                failures.append(
                    f"SEC-007: {path.relative_to(ROOT).as_posix()} uses `{token}` "
                    f"alongside fflate. The acceptance in {REGISTER} rests on `web/` "
                    "never decompressing — GHSA-px8p-9vwx-vf98 is an infinite loop in "
                    "unzipSync parsing malformed ZIP64. A decompression path voids it."
                )
    return failures


def main() -> int:
    failures = check_sec_006() + check_sec_007()
    if failures:
        print(
            "[ERROR] A recorded disposition rests on a premise that no longer holds.\n"
            "        The finding is not suppressed by this — re-open it, or amend the\n"
            f"        entry in {REGISTER} to match what the code now does.\n"
        )
        for failure in failures:
            print(f"  {failure}")
        return 1
    pins = ", ".join(f"{name}@{version}" for name, version in _SEC_007_MEASURED.items())
    print(
        "Disposition premises: PASSED — SEC-006 (nltk reached lazily, wordnet only, no "
        f"path call) and SEC-007 (no fflate decompression in web/; {pins} still the "
        "versions the call-site evidence was measured on) both still hold"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
