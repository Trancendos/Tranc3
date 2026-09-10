"""Vitals: a grade this estate computes for itself, and can show its working for.

WHY THIS EXISTS
---------------
CodeFactor grades this repository A. That grade is real, it is publicly
readable, and it is not ours. Its formula is not published, its history lives
in a vendor's database, its per-file detail is behind a login, and the day the
free tier changes the estate loses a health signal it never owned.

What CodeFactor actually provides is four things, and each is reproducible:

    1. an A-F grade per file, and a distribution across the repository
    2. new-vs-fixed issue counts per commit and per pull request
    3. debt prioritisation weighted towards files that change often
    4. a list of the worst files

This module computes all four from findings the estate already produces, with
a formula written in Python that anyone can read, argue with, and test.

WHAT IT DOES THAT THE VENDORS DO NOT
------------------------------------
**It grades the change, not the repository.** A grade over the whole tree is
almost useless on a pull request: a large estate's absolute number barely moves
whatever you do, so the number stops carrying information and reviewers stop
looking. The signal is the DELTA on the files this change touched. This is the
principle SonarQube calls "Clean as You Code", and it is also the fix for a
defect this estate has hit for real -- a freshness gate that measured absolute
state went red on `main` because a bot bumped a digest, blocking pull requests
that had touched nothing. **Gates must measure change, not state.**

**It shows its working.** `GradeReport.explain()` prints the arithmetic: the
findings counted, the weights applied, the lines of code divided by, and the
threshold crossed. A grade you cannot audit is a number you have to trust, and
this estate's whole problem has been controls trusted without evidence.

**It knows what a grade cannot see.** A grade computed from sensors that were
blind is a confident number resting on nothing. `GradeReport.confidence`
carries the fraction of required sensors that actually reported, and a grade
computed with blind sensors is reported as provisional -- never as an A.
"""

from __future__ import annotations

import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from src.immune.sarif import Finding

# What a finding costs, by severity. Deliberately steep: one error outweighs
# three warnings, because a repository with one live secret and ninety style
# nits is not in better health than one with ninety-one style nits.
WEIGHTS = {"error": 10.0, "warning": 3.0, "note": 1.0, "none": 0.0}

# Weighted findings per thousand lines. Below the first number is an A.
# Calibrated so that this estate at the time of writing lands where CodeFactor
# independently put it -- see docs/governance/IMMUNE-SYSTEM.md for the
# comparison, which is the point of choosing a public vendor to check against.
THRESHOLDS: Sequence[tuple[str, float]] = (
    ("A", 2.0),
    ("B", 5.0),
    ("C", 10.0),
    ("D", 20.0),
)
WORST_GRADE = "F"

# A file with fewer lines than this is graded on its findings alone: density
# over a 4-line module is arithmetic noise, and grading it would put __init__
# files at the top of every worst-files list forever.
MIN_LINES_FOR_DENSITY = 30


def grade_for(density: float) -> str:
    for letter, ceiling in THRESHOLDS:
        if density <= ceiling:
            return letter
    return WORST_GRADE


def _grade_rank(letter: str) -> int:
    order = [letter for letter, _ in THRESHOLDS] + [WORST_GRADE]
    return order.index(letter) if letter in order else len(order)


@dataclass
class FileGrade:
    path: str
    lines: int
    weighted: float
    findings: int
    errors: int = 0

    @property
    def density(self) -> float:
        if self.lines < MIN_LINES_FOR_DENSITY:
            return self.weighted
        return self.weighted * 1000.0 / self.lines

    @property
    def grade(self) -> str:
        return grade_for(self.density)


@dataclass
class GradeReport:
    files: dict[str, FileGrade] = field(default_factory=dict)
    total_lines: int = 0
    weighted: float = 0.0
    findings: int = 0
    confidence: float = 1.0
    # Every required sensor that did not produce a trustworthy reading, by
    # name, whatever the reason -- blind, failed, absent, unreadable. They are
    # one category for grading because they are one category epistemically:
    # the estate did not look. Keeping only 'blind' here was a real defect in
    # the first version of this file, and it printed "grade A" on a run whose
    # required security sensor had exited 2 without scanning anything.
    unseeing: list[str] = field(default_factory=list)

    @property
    def density(self) -> float:
        if not self.total_lines:
            return 0.0
        return self.weighted * 1000.0 / self.total_lines

    @property
    def grade(self) -> str:
        """The letter -- with a hard ceiling when the sensors were not all seeing.

        A grade is a claim about what is there. If a required sensor could not
        look, the claim's scope has outrun its evidence, and the honest answer
        is not 'A', it is 'we could not tell'. Capping at C is deliberate: high
        enough not to cry wolf, low enough that nobody ships on it.
        """
        letter = grade_for(self.density)
        if self.unseeing and _grade_rank(letter) < _grade_rank("C"):
            return "C"
        return letter

    @property
    def provisional(self) -> bool:
        return bool(self.unseeing) or self.confidence < 1.0

    def distribution(self) -> dict[str, int]:
        counts: dict[str, int] = {letter: 0 for letter, _ in THRESHOLDS}
        counts[WORST_GRADE] = 0
        for fg in self.files.values():
            counts[fg.grade] = counts.get(fg.grade, 0) + 1
        return counts

    def worst(self, limit: int = 10) -> list[FileGrade]:
        return sorted(
            self.files.values(),
            key=lambda fg: (-fg.density, -fg.errors, fg.path),
        )[:limit]

    def explain(self) -> str:
        """The arithmetic, in full. A grade nobody can check is a rumour."""
        lines = [
            f"grade         {self.grade}"
            + ("  (PROVISIONAL -- see below)" if self.provisional else ""),
            f"density       {self.density:.3f} weighted findings per 1,000 lines",
            f"weighted      {self.weighted:.1f} from {self.findings} finding(s)",
            f"lines counted {self.total_lines:,} across {len(self.files):,} graded file(s)",
            "weights       " + ", ".join(f"{k}={v:g}" for k, v in WEIGHTS.items() if v),
            "thresholds    "
            + ", ".join(f"{letter}<={ceiling:g}" for letter, ceiling in THRESHOLDS)
            + f", else {WORST_GRADE}",
        ]
        if self.unseeing:
            lines.append(
                "capped at C   because these required sensors did not see: "
                + ", ".join(sorted(self.unseeing))
            )
        return "\n".join(lines)


def count_lines(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def grade(
    findings: Iterable[Finding],
    *,
    tracked: Sequence[str],
    repo_root: Path = Path("."),
    unseeing: Sequence[str] = (),
    confidence: float = 1.0,
) -> GradeReport:
    """Grade a set of files against a set of findings.

    `tracked` is the population being graded. Passing only the files a pull
    request changed is what turns this from a repository score into a change
    score, which is the form that carries information on a pull request.
    """
    report = GradeReport(
        unseeing=list(unseeing),
        confidence=confidence,
    )
    by_path: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_path[finding.path].append(finding)

    for rel in tracked:
        lines = count_lines(repo_root / rel)
        if not lines:
            continue
        hits = by_path.get(rel, [])
        weighted = sum(WEIGHTS.get(f.level, 0.0) for f in hits)
        report.files[rel] = FileGrade(
            path=rel,
            lines=lines,
            weighted=weighted,
            findings=len(hits),
            errors=sum(1 for f in hits if f.level == "error"),
        )
        report.total_lines += lines
        report.weighted += weighted
        report.findings += len(hits)

    # Findings on paths outside the graded population still count against the
    # estate. Dropping them would let a change be graded clean by touching only
    # files the population happened to exclude.
    graded = set(report.files)
    for path, hits in by_path.items():
        if path in graded:
            continue
        report.weighted += sum(WEIGHTS.get(f.level, 0.0) for f in hits)
        report.findings += len(hits)
    return report


# ── churn-weighted debt, the part CodeFactor charges for ─────────────


def churn(
    paths: Sequence[str], *, since: str = "6 months ago", repo_root: Path = Path(".")
) -> dict[str, int]:
    """How often each file has changed recently.

    A defect in a file nobody touches costs less than the same defect in a file
    edited weekly: the second one is read, copied and built on. Churn is the
    cheapest available proxy for that, and git already knows it.
    """
    try:
        proc = subprocess.run(  # noqa: S603,S607 - fixed argv, no shell
            ["git", "log", f"--since={since}", "--name-only", "--pretty=format:"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return {}
    if proc.returncode != 0:
        return {}
    wanted = set(paths)
    counts: dict[str, int] = defaultdict(int)
    for line in proc.stdout.splitlines():
        name = line.strip()
        if name and name in wanted:
            counts[name] += 1
    return dict(counts)


def blast_radius(
    paths: Sequence[str],
    repo_root: Path = Path("."),
    *,
    searched: Sequence[str] | None = None,
) -> dict[str, int]:
    """How many other Python modules import each file.

    A defect in a leaf module is contained. A defect in something forty modules
    import is not. This is a static approximation -- it counts textual imports
    of the module's dotted path -- and it is deliberately cheap, because a debt
    ranking that takes an hour to compute will not be computed.
    """
    modules: dict[str, str] = {}
    for rel in paths:
        if not rel.endswith(".py"):
            continue
        dotted = rel[:-3].replace("/", ".")
        if dotted.endswith(".__init__"):
            dotted = dotted[: -len(".__init__")]
        modules[dotted] = rel
    counts: dict[str, int] = dict.fromkeys(modules.values(), 0)
    # `searched` is the population scanned FOR importers, and it must be the
    # whole tree, not the handful of files being ranked. Passing only the
    # ranked files makes every blast radius zero -- a few files that do not
    # import one another -- which is what the first version of `rank_debt`
    # did, quietly flattening the third factor of the priority formula to a
    # constant. Measured on the first real run: every row read "x 0 importers".
    for rel in searched if searched is not None else paths:
        if not rel.endswith(".py"):
            continue
        try:
            text = (repo_root / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for dotted, target in modules.items():
            if target == rel:
                continue
            if f"import {dotted}" in text or f"from {dotted}" in text:
                counts[target] = counts.get(target, 0) + 1
    return counts


@dataclass
class DebtItem:
    path: str
    grade: str
    weighted: float
    changes: int
    importers: int

    @property
    def priority(self) -> float:
        """severity x how often it changes x how much depends on it.

        The +1s keep a file that has never changed, or that nothing imports,
        from scoring zero and vanishing off the list -- a never-touched file
        with a live secret in it is still a problem.
        """
        return self.weighted * (self.changes + 1) * (self.importers + 1)


def rank_debt(
    report: GradeReport, *, repo_root: Path = Path("."), limit: int = 20
) -> list[DebtItem]:
    """Order the estate's debt by what it would actually cost to keep."""
    paths = [p for p, fg in report.files.items() if fg.weighted > 0]
    if not paths:
        return []
    changes = churn(paths, repo_root=repo_root)
    # Search the whole graded population for importers, not just the files
    # being ranked -- otherwise the blast-radius factor is always zero.
    importers = blast_radius(
        paths, repo_root=repo_root, searched=sorted(report.files)
    )
    items = [
        DebtItem(
            path=path,
            grade=report.files[path].grade,
            weighted=report.files[path].weighted,
            changes=changes.get(path, 0),
            importers=importers.get(path, 0),
        )
        for path in paths
    ]
    items.sort(key=lambda item: (-item.priority, item.path))
    return items[:limit]
