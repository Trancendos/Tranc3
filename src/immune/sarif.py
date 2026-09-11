"""SARIF 2.1.0 as the platform's bloodstream.

WHY THIS EXISTS
---------------
`defender-for-devops.yml` was deleted from this estate because Microsoft
Security DevOps needs an Azure tenant, a `windows-latest` runner, and a
Defender for Cloud onboarding this platform does not have and will not buy.

But MSDO's *value* was never the analysers it bundled. This repository already
runs ruff, bandit, semgrep, gitleaks, trivy, pip-audit and CodeQL. MSDO's value
was that it made every one of them speak **one language** and report to **one
place**. Without that, each sensor reports in its own dialect, to its own
surface, on its own schedule -- and nothing in the estate can answer "what does
this repository look like right now" without a human reading seven formats.

SARIF 2.1.0 (OASIS standard, no vendor) is that one language. This module is
the normalisation layer: it converts each tool's native output into SARIF, and
merges many SARIF runs into one document that GitHub's Security tab, any SARIF
viewer, or this platform's own grading can read.

WHAT THIS DOES THAT MSDO DID NOT
--------------------------------
MSDO reports what it found. It does not distinguish "this tool ran and found
nothing" from "this tool did not run". That distinction is the whole engagement
here: a scanner that cannot reach its backend and reports clean is worse than
one that crashes, because the clean report is believed. Sensor outcomes are
modelled explicitly in `src.immune.sensors`; this module refuses to silently
absorb an unreadable or malformed SARIF file, raising `SarifUnreadable` so the
caller has to decide, rather than merging an empty run and moving on.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/"
    "schema/sarif-schema-2.1.0.json"
)

# SARIF's own level vocabulary. Anything a tool emits outside this set is
# mapped rather than passed through, so downstream consumers never have to
# know which tool a finding came from in order to read its severity.
LEVELS = ("error", "warning", "note", "none")

# Severity ordering used for grading and for "is this worse than baseline".
_LEVEL_RANK = {"error": 3, "warning": 2, "note": 1, "none": 0}


class SarifUnreadable(Exception):
    """A file that was supposed to be SARIF could not be read as SARIF.

    Raised rather than returning an empty run, because an empty run is
    indistinguishable from a clean scan and would be believed.
    """


@dataclass(frozen=True)
class Finding:
    """One normalised finding, tool-agnostic.

    `fingerprint` is what makes a finding the *same* finding across runs, which
    is what lets the baseline say "this is not new" and lets memory say "this
    one was adjudicated". It deliberately excludes the line number: code moves,
    and a finding that re-fingerprints on every unrelated edit above it cannot
    be remembered.
    """

    tool: str
    rule_id: str
    level: str
    message: str
    path: str
    start_line: int
    end_line: int = 0
    snippet: str = ""
    # Which declared sensor produced this, as distinct from `tool`, which is
    # whatever that sensor calls itself in its own output. They diverge more
    # often than you would expect -- the manifest's `trivy-fs` reports a SARIF
    # driver named `Trivy`, and `semgrep` reports `semgrep OSS`. The baseline
    # matches on `sensor`, because "was this instrument part of the measurement"
    # is a question about the manifest, not about a vendor's product naming.
    # Excluded from the fingerprint: renaming a sensor must not orphan every
    # adjudication and baseline entry that referred to its findings.
    sensor: str = ""

    @property
    def rank(self) -> int:
        return _LEVEL_RANK.get(self.level, 0)

    @property
    def fingerprint(self) -> str:
        basis = f"{self.tool}\x00{self.rule_id}\x00{self.path}\x00{self.message}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]

    @property
    def located(self) -> str:
        return f"{self.path}:{self.start_line}" if self.start_line else self.path

    def to_result(self) -> dict[str, Any]:
        """Render back to a SARIF `result` object."""
        region: dict[str, Any] = {}
        if self.start_line:
            region["startLine"] = self.start_line
        if self.end_line and self.end_line != self.start_line:
            region["endLine"] = self.end_line
        if self.snippet:
            region["snippet"] = {"text": self.snippet}
        location: dict[str, Any] = {
            "physicalLocation": {
                "artifactLocation": {"uri": self.path},
            }
        }
        if region:
            location["physicalLocation"]["region"] = region
        return {
            "ruleId": self.rule_id,
            "level": self.level,
            "message": {"text": self.message},
            "locations": [location],
            "partialFingerprints": {"trancendosImmune/v1": self.fingerprint},
            "properties": {"tool": self.tool, "sensor": self.sensor or self.tool},
        }


def normalise_level(raw: Any, default: str = "warning") -> str:
    """Map any tool's severity vocabulary onto SARIF's four levels.

    Every scanner invents its own words. Keeping the mapping in one function
    means a new sensor needs a vocabulary entry, not a new code path.
    """
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if text in LEVELS:
        return text
    mapping = {
        # Severity words, common across bandit / trivy / semgrep / pip-audit.
        "critical": "error",
        "high": "error",
        "blocker": "error",
        "fatal": "error",
        "medium": "warning",
        "moderate": "warning",
        "low": "note",
        "info": "note",
        "informational": "note",
        "unknown": "note",
        "negligible": "note",
        # Linter-shaped vocabularies.
        "e": "error",
        "f": "error",
        "w": "warning",
        "c": "note",
        "r": "note",
        "convention": "note",
        "refactor": "note",
        "style": "note",
    }
    return mapping.get(text, default)


def _first(seq: Iterable[Any]) -> Any:
    for item in seq:
        return item
    return None


def _uri_of(result: dict[str, Any]) -> str:
    for loc in result.get("locations") or []:
        physical = loc.get("physicalLocation") or {}
        artifact = physical.get("artifactLocation") or {}
        uri = artifact.get("uri")
        if uri:
            return _relativise(str(uri))
    return ""


# The repository this module lives in. Used to strip an absolute checkout
# prefix off a finding's path -- ruff, for one, always reports absolute paths,
# and the checkout sits at /home/runner/work/Tranc3/Tranc3 on a GitHub runner
# and somewhere else entirely on anyone's laptop.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# Never a cut point: present in every checkout, tracked in none of them, and
# `.git/` in particular appears inside completely unrelated paths.
_UNTRACKED_NOISE = frozenset(
    {".git", ".ruff_cache", ".mypy_cache", ".pytest_cache", ".venv", "venv", "__pycache__"}
)


def _top_level_entries() -> frozenset[str]:
    """Top-level names in this repository, used to find where content starts.

    Computed from disk rather than written down, so it cannot drift from the
    tree it describes.

    DOT-DIRECTORIES ARE INCLUDED, and the first version's exclusion of them was
    backwards. The reasoning then was that `.github` would cut unrelated paths
    at the wrong place; in fact a dot-directory is among the LEAST likely names
    to collide, while the generic entries that were kept -- `src`, `docs`,
    `tests`, `config`, `scripts` -- are the ones that appear in arbitrary
    filesystem paths all the time. Excluding `.github` meant a finding reported
    by a workflow scanner against an absolute path stayed absolute, so its
    fingerprint carried the machine it ran on and the file never matched a
    graded path. Reported by cubic on PR #1150.

    What is excluded instead is untracked machine noise -- caches, virtualenvs,
    and `.git` itself, which turns up inside unrelated paths constantly.
    """
    try:
        return frozenset(
            entry.name for entry in _REPO_ROOT.iterdir() if entry.name not in _UNTRACKED_NOISE
        )
    except OSError:  # pragma: no cover - only if the checkout vanishes mid-run
        return frozenset()


_TOP_LEVEL = _top_level_entries()


def _cut_at_repo_content(text: str) -> str:
    """Find where this repository's content starts inside a foreign path.

    Several segments can match a top-level name at once:

        /home/src/checkouts/Tranc3/src/immune/sarif.py
              ^^^                    ^^^

    Taking the FIRST match yields `src/checkouts/Tranc3/src/immune/sarif.py`,
    which is wrong and, worse, wrong in a way that still looks relative -- so
    it would sail into a fingerprint and never match a graded file. Reported by
    cubic on PR #1150.

    So candidates are verified against the tree rather than accepted on the
    strength of their name: prefer the cut whose remainder actually EXISTS in
    this repository. That is the same content-over-names principle that made
    the enclosing fallback stop asking what the checkout is called.

    When nothing verifies -- a file deleted since the scan, a path from a
    different revision -- fall back to the LAST match rather than the first.
    The repository's own directory sits closest to the file it contains, so on
    a nested path the last match is right far more often than the first.
    """
    segments = text.lstrip("/").split("/")
    matches = [i for i, segment in enumerate(segments) if segment in _TOP_LEVEL]
    if not matches:
        return text
    for index in matches:
        candidate = "/".join(segments[index:])
        if (_REPO_ROOT / candidate).exists():
            return candidate
    return "/".join(segments[matches[-1] :])


def _relativise(uri: str, root: Path | None = None) -> str:
    """Strip the accidents of where a scanner happened to be run.

    Trivy reports absolute container paths, CodeQL reports `file:` URIs, ruff
    reports the absolute path of the checkout, and a locally run tool reports
    whatever the working directory was.

    This matters more than tidiness. A finding's fingerprint includes its path,
    so an un-stripped checkout prefix makes the fingerprint machine-specific: a
    baseline written on a laptop under /home/user/Tranc3 matches nothing in CI
    under /home/runner/work/Tranc3/Tranc3, and every finding reads as new. That
    is a gate that fails on every pull request for a reason nobody can see --
    found by planting a deliberately tangled function and reading the path in
    the failure line: `home/user/Tranc3/src/immune/_cx_probe.py`.
    """
    text = uri
    for prefix in ("file://", "file:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    # Strip the checkout root before anything else -- it is the longest and
    # most specific prefix, and the one that differs between machines.
    for candidate in (root, _REPO_ROOT):
        if candidate is None:
            continue
        as_posix = candidate.as_posix().rstrip("/")
        if as_posix and text.startswith(as_posix + "/"):
            text = text[len(as_posix) + 1 :]
            break
    else:
        # Still absolute: a scanner reporting from a checkout that is not this
        # one -- a container mount, or a SARIF produced on the runner and merged
        # here. Cut at the first segment that is a real top-level entry of THIS
        # repository.
        #
        # The first version cut at the last segment matching `_REPO_ROOT.name`,
        # and cubic was right that it is fragile -- though its proposed fix,
        # hardcoding the literal "Tranc3", is fragile in the same way and
        # additionally wrong: the repository can be renamed, forked, vendored,
        # or checked out into any directory, and a constant cannot follow it.
        # Both versions ask "what is this repository called?", which is a
        # question about a name.
        #
        # The right question is "where does this repository's content start?",
        # which is a question about CONTENT, and the answer is on disk. A path
        # ending `.../anything/src/immune/sarif.py` starts at `src/` because
        # `src/` is a directory that exists here -- true whatever the checkout
        # is called, including a fork with a different name and the runner's
        # doubled `/home/runner/work/X/X/` layout.
        if text.startswith("/"):
            text = _cut_at_repo_content(text)
    while text.startswith("./"):
        text = text[2:]
    text = text.lstrip("/")
    for marker in ("github/workspace/", "workspace/", "src/app/", "app/"):
        if text.startswith(marker):
            text = text[len(marker) :]
    return text


def _region_of(result: dict[str, Any]) -> tuple[int, int, str]:
    for loc in result.get("locations") or []:
        region = (loc.get("physicalLocation") or {}).get("region") or {}
        start = int(region.get("startLine") or 0)
        end = int(region.get("endLine") or start)
        snippet = ((region.get("snippet") or {}).get("text") or "").strip()
        if start or snippet:
            return start, end, snippet[:200]
    return 0, 0, ""


def _rule_levels(run: dict[str, Any]) -> dict[str, str]:
    """Build ruleId -> default level from the run's rule metadata.

    Several tools omit `level` on individual results and declare it once on the
    rule. Reading only the result would grade every one of those findings at
    the fallback severity.
    """
    levels: dict[str, str] = {}
    driver = ((run.get("tool") or {}).get("driver")) or {}
    for rule in driver.get("rules") or []:
        rid = rule.get("id")
        if not rid:
            continue
        config = rule.get("defaultConfiguration") or {}
        if config.get("level"):
            levels[str(rid)] = normalise_level(config["level"])
            continue
        props = rule.get("properties") or {}
        for key in ("problem.severity", "security-severity", "severity"):
            if props.get(key):
                levels[str(rid)] = normalise_level(props[key])
                break
    return levels


def findings_from_sarif(document: dict[str, Any], *, tool_hint: str = "") -> list[Finding]:
    """Flatten a SARIF document into normalised findings."""
    findings: list[Finding] = []
    for run in document.get("runs") or []:
        driver = ((run.get("tool") or {}).get("driver")) or {}
        tool = str(driver.get("name") or tool_hint or "unknown").strip()
        rule_levels = _rule_levels(run)
        for result in run.get("results") or []:
            rule_id = str(result.get("ruleId") or result.get("rule", {}).get("id") or "")
            if not rule_id:
                rule_id = f"{tool}/unnamed"
            level = result.get("level")
            level = normalise_level(level) if level else rule_levels.get(rule_id, "warning")
            message = str((result.get("message") or {}).get("text") or "").strip()
            start, end, snippet = _region_of(result)
            findings.append(
                Finding(
                    tool=tool,
                    rule_id=rule_id,
                    level=level,
                    message=message[:500],
                    path=_uri_of(result),
                    start_line=start,
                    end_line=end,
                    snippet=snippet,
                )
            )
    return findings


def load_sarif(path: Path, *, tool_hint: str = "") -> list[Finding]:
    """Read one SARIF file, or say clearly that it could not be read.

    An unreadable sensor output is not a clean scan. Callers get an exception
    so that "we could not see" can never be recorded as "there was nothing to
    see" -- the failure mode this whole subsystem exists to close.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SarifUnreadable(f"{path}: {exc}") from exc
    if not raw.strip():
        raise SarifUnreadable(f"{path}: file is empty")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SarifUnreadable(f"{path}: not valid JSON ({exc})") from exc
    if not isinstance(document, dict) or "runs" not in document:
        raise SarifUnreadable(f"{path}: JSON, but not a SARIF document (no 'runs')")
    return findings_from_sarif(document, tool_hint=tool_hint)


def dedupe(findings: Iterable[Finding]) -> list[Finding]:
    """Collapse findings two sensors both reported.

    Overlap is the price of defence in depth -- ruff and semgrep will both see
    some things -- and counting it twice would make the estate look worse the
    more carefully it looked at itself. Deduplication is by fingerprint AND
    line, so the same rule firing twice in one file is still two findings.
    """
    seen: set[tuple[str, int]] = set()
    out: list[Finding] = []
    for finding in findings:
        key = (finding.fingerprint, finding.start_line)
        if key in seen:
            continue
        seen.add(key)
        out.append(finding)
    return out


@dataclass
class MergedReport:
    """The estate's findings, as one document plus the provenance to audit it."""

    findings: list[Finding] = field(default_factory=list)
    sensors: list[str] = field(default_factory=list)

    def by_level(self) -> dict[str, int]:
        counts = dict.fromkeys(LEVELS, 0)
        for finding in self.findings:
            counts[finding.level] = counts.get(finding.level, 0) + 1
        return counts

    def by_tool(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.tool] = counts.get(finding.tool, 0) + 1
        return counts

    def to_sarif(self) -> dict[str, Any]:
        """One SARIF run per contributing tool, so viewers keep attribution."""
        grouped: dict[str, list[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.tool, []).append(finding)
        runs = []
        for tool in sorted(grouped):
            group = grouped[tool]
            rules = sorted({f.rule_id for f in group})
            runs.append(
                {
                    "tool": {
                        "driver": {
                            "name": tool,
                            "informationUri": "https://trancendos.com",
                            "rules": [{"id": rule} for rule in rules],
                        }
                    },
                    "results": [f.to_result() for f in group],
                }
            )
        return {"$schema": SARIF_SCHEMA, "version": SARIF_VERSION, "runs": runs}


def merge(reports: Iterable[tuple[str, list[Finding]]]) -> MergedReport:
    """Merge per-sensor findings into one report, recording who contributed."""
    merged = MergedReport()
    collected: list[Finding] = []
    for name, findings in reports:
        merged.sensors.append(name)
        collected.extend(findings)
    merged.findings = dedupe(collected)
    merged.findings.sort(key=lambda f: (-f.rank, f.tool, f.path, f.start_line, f.rule_id))
    return merged


def iter_findings(report: MergedReport) -> Iterator[Finding]:
    yield from report.findings
