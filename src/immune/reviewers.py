"""Sight for the review layer: did the reviewers on a pull request actually look?

`docs/governance/IMMUNE-SYSTEM.md` sets one rule for every sensor in this
estate: *a sensor that cannot see reports exactly what a clean estate reports*,
so each one must declare whether it could see. `src/immune/sensors.py` applies
that to the scanners this repository runs. It does not apply to the reviewers
that run on this repository, and that is a real gap rather than a tidiness one.

Measured on 2026-10-05 across the fifteen most recent pull requests:

* `coderabbitai` posted "Review limit reached -- you've used all free OSS
  reviews" on four of them.
* `devloai` posted "You have run out of credits" on the same four.
* `qodo-code-review` posted "reviews are paused because the subscription is no
  longer active" on the same four.
* `ecc-tools` posted 207 comments, a recurring one ending "Check publication was
  denied or unavailable. An app owner must enable Checks: read and write" -- it
  reached findings and could not publish them as a check.

On #1372, `sourcery-ai` was the only reviewer that genuinely reviewed, and it
found five real defects, one of which destroyed a concurrent edit. Had it also
been out of credits, that pull request would have carried every one of them and
the pull request page would have looked no different: quiet bots, green checks.

That is the whole problem. A reviewer out of credits and a reviewer with nothing
to say produce the same *visible* result, so "no review comments" silently means
either "this is fine" or "nobody looked". This module refuses to collapse those
two, and so a pull request nothing reviewed is reported as UNREVIEWED rather
than as clean.

Coverage is measured against a written decision, never inferred from who
commented. `config/immune/reviewers.yaml` names the reviewers this estate
depends on and, separately, the bots that comment without reviewing. That file
exists because the first live run of this module reported #1372 as "reviewed by
mergify[bot], Trancendos" -- a merge-queue checkbox and the author's own
replies. Counting those as coverage is the same false-clean the module was
written to stop, so with no declared reviewer matched the verdict is
UNDETERMINED rather than a guess.

Pure functions over comment text. Nothing here touches the network; the caller
supplies the comments and the manifest (see `scripts/review_sight.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence

__all__ = [
    "Sight",
    "ReviewerVerdict",
    "ReviewCoverage",
    "BLINDNESS_PHRASES",
    "UNPUBLISHED_PHRASES",
    "classify",
    "assess",
    "load_manifest",
    "DEFAULT_MANIFEST",
]

DEFAULT_MANIFEST = Path("config/immune/reviewers.yaml")


class Sight(str, Enum):
    """What a reviewer's own words establish about whether it looked."""

    REVIEWED = "reviewed"
    BLIND = "blind"
    UNPUBLISHED = "unpublished"
    SILENT = "silent"

    @property
    def trustworthy(self) -> bool:
        """Can this reviewer's silence on a defect be believed?

        Only a reviewer that reviewed. BLIND said it could not look. SILENT
        never spoke, so there is no evidence either way -- and treating absence
        of comment as evidence of quality is the inference this module exists to
        block. UNPUBLISHED did look, but its findings never became a check,
        so nothing enforces them.
        """
        return self is Sight.REVIEWED


# Each phrase is quoted from a comment measured in this repository, with the bot
# that wrote it, because a pattern list assembled from imagination is how a
# detector ends up matching nothing. Lowercase; matched as substrings.
BLINDNESS_PHRASES: tuple[tuple[str, str], ...] = (
    ("out of credits", "devloai[bot]"),
    ("run out of credits", "devloai[bot]"),
    ("upgrade your plan", "devloai[bot]"),
    ("subscription is no longer active", "qodo-code-review[bot]"),
    ("reviews are paused", "qodo-code-review[bot]"),
    ("review limit reached", "coderabbitai[bot]"),
    ("used all free oss reviews", "coderabbitai[bot]"),
    ("rate limited by", "coderabbitai[bot]"),
    # Not yet measured here, but the same class, and cheap to carry:
    ("quota exceeded", "generic"),
    ("insufficient credits", "generic"),
    ("trial has expired", "generic"),
    ("plan does not include", "generic"),
)

UNPUBLISHED_PHRASES: tuple[tuple[str, str], ...] = (
    ("check publication was denied or unavailable", "ecc-tools[bot]"),
    ("must enable checks: read and write", "ecc-tools[bot]"),
)


def _match(body: str, phrases: Iterable[tuple[str, str]]) -> str | None:
    low = body.lower()
    for phrase, _source in phrases:
        if phrase in low:
            return phrase
    return None


@dataclass(frozen=True)
class ReviewerVerdict:
    reviewer: str
    sight: Sight
    evidence: str
    """The phrase that decided a BLIND or UNPUBLISHED verdict, so the judgement
    can be checked rather than taken on faith. Empty for REVIEWED and SILENT."""

    @property
    def trustworthy(self) -> bool:
        return self.sight.trustworthy


def classify(reviewer: str, bodies: Sequence[str]) -> ReviewerVerdict:
    """Decide what a reviewer's comments establish about its sight.

    Order matters and is deliberate. A reviewer that declared blindness ANYWHERE
    in its comments is BLIND even if it also posted a cheerful template: three
    of the four bots measured here post a banner and a greeting in the same
    breath, and reading the greeting first would score them as having reviewed.
    """
    if not bodies:
        return ReviewerVerdict(reviewer, Sight.SILENT, "")

    for body in bodies:
        hit = _match(body, BLINDNESS_PHRASES)
        if hit:
            return ReviewerVerdict(reviewer, Sight.BLIND, hit)

    for body in bodies:
        hit = _match(body, UNPUBLISHED_PHRASES)
        if hit:
            return ReviewerVerdict(reviewer, Sight.UNPUBLISHED, hit)

    return ReviewerVerdict(reviewer, Sight.REVIEWED, "")


@dataclass
class ReviewCoverage:
    """Who reviewed a pull request, and who only appeared to."""

    pr: str
    verdicts: list[ReviewerVerdict] = field(default_factory=list)
    expected: tuple[str, ...] = ()
    """The reviewers this estate declared it depends on. Coverage is judged
    against these and nothing else."""

    def _of(self, sight: Sight) -> list[ReviewerVerdict]:
        return [v for v in self.verdicts if v.sight is sight]

    @property
    def reviewed(self) -> list[ReviewerVerdict]:
        return self._of(Sight.REVIEWED)

    @property
    def blind(self) -> list[ReviewerVerdict]:
        return self._of(Sight.BLIND)

    @property
    def unpublished(self) -> list[ReviewerVerdict]:
        return self._of(Sight.UNPUBLISHED)

    @property
    def silent(self) -> list[ReviewerVerdict]:
        return self._of(Sight.SILENT)

    @property
    def coverage_known(self) -> bool:
        """Is there a declared set to judge coverage against?

        Without one, "somebody commented" is all that can be observed, and that
        is not the same question. Saying so beats answering a question nobody
        measured.
        """
        return bool(self.expected)

    @property
    def covered(self) -> bool:
        """Did a reviewer this estate DEPENDS ON actually review this pull request?

        This is the question the pull request page cannot answer. A page with no
        review comments and a page whose every reviewer was out of credits look
        identical, and only one of them has been reviewed.

        Judged only over `expected`. A trustworthy verdict from a bot that posts
        a merge checkbox does not make a pull request reviewed, and neither do
        the author's own replies.
        """
        if not self.coverage_known:
            return False
        return any(v.trustworthy and v.reviewer in self.expected for v in self.verdicts)

    @property
    def depended_on(self) -> list[ReviewerVerdict]:
        """Verdicts for the declared reviewers only."""
        return [v for v in self.verdicts if v.reviewer in self.expected]

    @property
    def summary(self) -> str:
        if not self.coverage_known:
            commented = sorted(v.reviewer for v in self.reviewed)
            return (
                f"{self.pr}: UNDETERMINED -- no reviewers declared, so coverage was "
                f"not measured ({len(commented)} author(s) commented)"
            )
        if self.covered:
            names = ", ".join(
                sorted(v.reviewer for v in self.reviewed if v.reviewer in self.expected)
            )
            return f"{self.pr}: reviewed by {names}"
        blind = sorted(v.reviewer for v in self.blind if v.reviewer in self.expected)
        if blind:
            return (
                f"{self.pr}: UNREVIEWED -- {len(blind)} depended-on reviewer(s) declared "
                f"they could not review ({', '.join(blind)}) and none reviewed"
            )
        return f"{self.pr}: UNREVIEWED -- no depended-on reviewer reported on it"


def load_manifest(path: Path | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Read (depends_on, not_a_reviewer) from the manifest.

    A missing manifest returns two empty tuples rather than a default list, so
    coverage reads UNDETERMINED instead of being judged against names this file
    invented.
    """
    import yaml

    target = path or DEFAULT_MANIFEST
    if not target.is_file():
        return (), ()
    data = yaml.safe_load(target.read_text()) or {}
    return (
        tuple(data.get("depends_on") or ()),
        tuple(data.get("not_a_reviewer") or ()),
    )


def assess(
    pr: str,
    comments: Iterable[tuple[str, str]],
    expected: Sequence[str] = (),
    author: str | None = None,
) -> ReviewCoverage:
    """Group (author, body) pairs by reviewer and classify each one.

    `expected` names the reviewers coverage is judged against -- normally
    `load_manifest()[0]`. One of them that posts nothing is recorded SILENT
    rather than dropped, because a reviewer absent from a pull request entirely
    is the hardest blindness to notice: there is no comment to read.

    `author` is excluded. A pull request is not reviewed by the person who
    opened it, and on this estate the author's own replies to review threads
    were being counted as review coverage until this argument existed.
    """
    grouped: dict[str, list[str]] = {name: [] for name in expected}
    for commenter, body in comments:
        if author is not None and commenter == author:
            continue
        grouped.setdefault(commenter, []).append(body)

    verdicts = [classify(name, bodies) for name, bodies in sorted(grouped.items())]
    return ReviewCoverage(pr=pr, verdicts=verdicts, expected=tuple(expected))
