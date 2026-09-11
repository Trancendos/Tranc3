"""The semgrep pin must be the same number everywhere it is installed.

Why this file exists, rather than a comment saying "keep these in sync":

SEC-005 accepted three CVEs in ``mcp`` on the basis that semgrep hard-pinned
``mcp==1.23.3`` and overriding it broke semgrep.  semgrep 1.173.0 moved that pin
to ``mcp==1.29.0``, which has no advisories, so the acceptance was retired.  The
retirement is only true of an environment that actually installs a semgrep at or
above 1.173.0.

``requirements-security.txt`` and ``.forgejo/workflows/security-scan.yml`` were
bumped to 1.177.0 and ``Makefile``'s ``security-install`` was left at 1.172.0 --
the last release that requires the vulnerable ``mcp``.  So the register said the
risk was gone while one install path kept installing it.  Nothing caught that,
because nothing was looking; the drift was found by a reviewer reading a comment
that claimed the opposite.

This guard looks.  It does not encode which version is correct -- only that every
place that pins semgrep pins the same one, so a partial bump fails loudly
instead of silently splitting the estate into a patched half and an unpatched
half.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Anything that looks like an installable pin, wherever it lives.  Comment lines
# are skipped so prose *about* the pin (including this repo's own explanations of
# why 1.172.0 was wrong) does not register as an install site.
PIN_RE = re.compile(r"semgrep==([0-9]+(?:\.[0-9]+)*)")

SEARCH_SUFFIXES = {".txt", ".yml", ".yaml", ".sh", ".cfg", ".toml", ".in", ".dockerfile"}
SEARCH_NAMES = {"Makefile"}


#: Dockerfiles install things too, and this guard did not look at them. It
#: claimed to watch every install site while `deploy/forgejo/runner.Dockerfile`
#: pinned semgrep==1.100.0 -- 73 releases below the mcp-fix floor -- and both
#: alignment tests passed. cubic caught it on PR #1207.
#:
#: Matched by prefix AND suffix on purpose: the file that was missed is named
#: `runner.Dockerfile`, so a `Dockerfile*` prefix match alone would still not
#: see it. That naming variant is the whole reason the blind spot existed.
def _is_dockerfile(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith("dockerfile") or name.endswith(".dockerfile")


SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "compliance/magna-carta",  # own repo, own pin policy (a floating >= range)
}


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _candidate_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if any(rel == d or rel.startswith(d + "/") for d in SKIP_DIRS):
            continue
        if path.suffix in SEARCH_SUFFIXES or path.name in SEARCH_NAMES or _is_dockerfile(path):
            files.append(path)
    return files


def _pins_in(text: str) -> list[str]:
    return [
        match.group(1)
        for line in text.splitlines()
        if not _is_comment(line)
        for match in [PIN_RE.search(line)]
        if match
    ]


def collect_pins() -> dict[str, list[str]]:
    """Map each file that pins semgrep to the versions it pins."""
    found: dict[str, list[str]] = {}
    for path in _candidate_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        pins = _pins_in(text)
        if pins:
            found[path.relative_to(REPO_ROOT).as_posix()] = pins
    return found


def test_semgrep_is_pinned_somewhere():
    """A guard over an empty set passes trivially; this is the canary for that."""
    pins = collect_pins()
    assert pins, (
        "No semgrep== pin found anywhere. Either the pins moved to a file shape "
        "this guard does not scan (extend SEARCH_SUFFIXES/SEARCH_NAMES) or the "
        "guard is now watching nothing."
    )


def test_the_three_known_install_sites_still_pin_semgrep():
    """Named so a *removal* is a deliberate edit here, not a silent pass."""
    pins = collect_pins()
    for expected in (
        "requirements-security.txt",
        "Makefile",
        ".forgejo/workflows/security-scan.yml",
        "deploy/forgejo/runner.Dockerfile",
    ):
        assert expected in pins, (
            f"{expected} no longer pins semgrep. If that is intentional, remove it "
            f"from this list; if not, the pin was dropped."
        )


def test_every_semgrep_pin_agrees():
    pins = collect_pins()
    versions = {v for vs in pins.values() for v in vs}
    assert len(versions) == 1, (
        "semgrep is pinned to more than one version:\n"
        + "\n".join(f"  {f}: {', '.join(vs)}" for f, vs in sorted(pins.items()))
        + "\n\nA split pin means one environment installs a semgrep whose transitive "
        "mcp differs from the one SEC-005's retirement was measured against."
    )


def test_no_pin_predates_the_mcp_fix():
    """1.173.0 is where semgrep moved off the vulnerable mcp==1.23.3."""
    pins = collect_pins()
    for path, versions in sorted(pins.items()):
        for version in versions:
            parts = tuple(int(p) for p in version.split("."))
            assert parts >= (1, 173, 0), (
                f"{path} pins semgrep=={version}, which requires mcp==1.23.3 "
                f"(CVE-2026-52869/52870/59950). SEC-005 is retired on the basis "
                f"that no environment installs that."
            )


class TestTheGuardWouldCatchIt:
    """Probe: a guard that cannot fail is not evidence of anything."""

    def test_disagreeing_pins_are_detected(self):
        a = _pins_in("pip install semgrep==1.177.0\n")
        b = _pins_in("run: python3 -m pip install semgrep==1.172.0 --quiet\n")
        assert set(a + b) == {"1.177.0", "1.172.0"}
        assert len({*a, *b}) != 1, "the disagreement check would not have fired"

    def test_prose_about_a_pin_is_not_an_install_site(self):
        assert _pins_in("# semgrep==1.172.0 was the last vulnerable release\n") == []
        assert _pins_in("  #   pip download --no-deps semgrep==<version>\n") == []

    def test_a_dockerfile_is_recognised_in_both_spellings(self):
        """The blind spot, as a test rather than a memory."""
        assert _is_dockerfile(Path("Dockerfile"))
        assert _is_dockerfile(Path("workers/x/Dockerfile.prod"))
        assert _is_dockerfile(Path("deploy/forgejo/runner.Dockerfile"))
        assert not _is_dockerfile(Path("notes-about-dockerfile-usage.md"))

    def test_an_old_pin_fails_the_floor(self):
        parts = tuple(int(p) for p in "1.172.0".split("."))
        assert parts < (1, 173, 0), "the mcp-fix floor would not have fired"
