"""Sight for the review layer: did the reviewers on a pull request actually look?

`docs/governance/IMMUNE-SYSTEM.md` sets one rule for every sensor in this
estate: *a sensor that cannot see reports exactly what a clean estate reports*,
so each one must declare whether it could see. `src/immune/sensors.py` applies
that to the scanners this repository runs. It did not apply to the reviewers
that run on this repository, and that was a real gap rather than a tidy one.

Measured on 2026-10-05 across the fifteen most recent pull requests:

* `coderabbitai` posted "Review limit reached -- you've used all free OSS
  reviews" on four of them.
* `devloai` posted "You have run out of credits" on the same four.
* `qodo-code-review` posted "reviews are paused because the subscription is no
  longer active" on the same four.
* `ecc-tools` posted 207 comments, a recurring one ending "Check publication was
  denied or unavailable" -- it reached findings and could not publish them.

On #1372, `sourcery-ai` was the only reviewer that genuinely reviewed, and it
found five real defects, one of which destroyed a concurrent edit. Had it also
been out of credits, that pull request would have carried every one of them and
the page would have looked no different: quiet bots, green checks.

WHY THIS MODULE IS SHAPED THE WAY IT IS
---------------------------------------
The first version of it caught that disease itself, and the review of #1373
proved it in two measurable ways:

* `classify` returned REVIEWED for any comment that merely lacked a blindness
  phrase. Sourcery's own progress notice -- "Sourcery is reviewing your pull
  request!" -- therefore made a pull request read as **covered and
  trustworthy**. A greeting counted as a review.
* Blindness phrases were matched against every author. A genuine review that
  quoted the words "review limit reached" -- a review *of this file* would --
  was classified BLIND.

Both are the exact false-clean this module exists to prevent, so the design now
refuses them structurally rather than by pattern-matching harder:

1. **REVIEWED requires affirmative evidence**, never the absence of a bad sign.
   Only a submitted review or an inline comment on the diff proves a reviewer
   read it. An ordinary issue comment proves it spoke, which is UNPROVEN.
2. **Evidence is tied to the head it reviewed.** A review of an earlier commit
   is STALE, not coverage: the question is whether anyone has seen *this* diff.
3. **A phrase binds to the reviewer that emits it.** `coderabbitai`'s banner
   says nothing about `sourcery-ai`, and quoting it is not emitting it.
4. **Evidence that could not be collected reads UNKNOWN**, never SILENT -- which
   is rule one of this whole subsystem applied to its own inputs.

Pure functions over structured remarks. Nothing here touches the network; the
caller supplies the remarks and the manifest (see `scripts/review_sight.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence

__all__ = [
    "Sight",
    "Remark",
    "ReviewerVerdict",
    "ReviewCoverage",
    "BLINDNESS_PHRASES",
    "UNPUBLISHED_PHRASES",
    "REVIEW_KINDS",
    "classify",
    "assess",
    "load_manifest",
    "DEFAULT_MANIFEST",
]

# Resolved against the repository, not the process working directory: a relative
# default silently returned "no reviewers declared" -- i.e. UNDETERMINED -- for
# any caller run from elsewhere, which is a wrong answer dressed as a cautious
# one.
_REPO = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = _REPO / "config" / "immune" / "reviewers.yaml"


class Sight(str, Enum):
    """What a reviewer's own output establishes about whether it looked."""

    REVIEWED = "reviewed"
    STALE = "stale"
    BLIND = "blind"
    UNPUBLISHED = "unpublished"
    UNPROVEN = "unproven"
    SILENT = "silent"
    UNKNOWN = "unknown"

    @property
    def trustworthy(self) -> bool:
        """Can this reviewer's silence on a defect be believed?

        Only REVIEWED: a reviewer that left review evidence against the current
        head. Every other value is a different way of not knowing --

        STALE       reviewed an earlier diff, not this one
        BLIND       said it could not review
        UNPUBLISHED reached findings and could not publish them as a check
        UNPROVEN    spoke, or left review evidence anchored to no commit at all,
                    so nothing it shows proves it read this diff
        SILENT      said nothing at all
        UNKNOWN     its evidence could not be collected, or the pull request's
                    head could not be determined, so there is nothing to
                    compare the evidence against

        -- and treating any of them as evidence of quality is the inference this
        module exists to block.
        """
        return self is Sight.REVIEWED


# Remark kinds that constitute evidence a reviewer read the diff. A submitted
# review and an inline comment are both anchored to a commit; a bare issue
# comment is not anchored to anything and proves only that something was posted.
REVIEW_KINDS = frozenset({"review", "review_comment"})

# Each phrase is quoted from a comment measured in this repository and bound to
# the reviewer that emitted it, because a phrase list applied to every author
# classifies a reviewer QUOTING a banner as having emitted it. "generic" phrases
# apply to any reviewer and are kept deliberately few.
BLINDNESS_PHRASES: tuple[tuple[str, str], ...] = (
    ("out of credits", "devloai[bot]"),
    ("run out of credits", "devloai[bot]"),
    ("upgrade your plan", "devloai[bot]"),
    ("subscription is no longer active", "qodo-code-review[bot]"),
    ("reviews are paused", "qodo-code-review[bot]"),
    ("review limit reached", "coderabbitai[bot]"),
    ("used all free oss reviews", "coderabbitai[bot]"),
    ("rate limited by", "coderabbitai[bot]"),
    ("quota exceeded", "generic"),
    ("insufficient credits", "generic"),
    ("trial has expired", "generic"),
)

UNPUBLISHED_PHRASES: tuple[tuple[str, str], ...] = (
    ("check publication was denied or unavailable", "ecc-tools[bot]"),
    ("must enable checks: read and write", "ecc-tools[bot]"),
)


@dataclass(frozen=True)
class Remark:
    """One thing a reviewer posted, with the metadata that makes it evidence.

    `commit_id` is the head the remark was anchored to, where GitHub gives one.
    Reducing a remark to (author, body) -- as the first version did -- discards
    exactly what distinguishes "reviewed this diff" from "reviewed some diff".
    """

    author: str
    body: str
    kind: str = "issue_comment"
    commit_id: str | None = None
    state: str | None = None


def _match(body: str, reviewer: str, phrases: Iterable[tuple[str, str]]) -> str | None:
    """Find a phrase this reviewer is declared to emit.

    A phrase bound to another reviewer is ignored, so quoting someone else's
    banner -- or reviewing code that contains one -- does not read as blindness.
    """
    low = body.lower()
    for phrase, source in phrases:
        if source != "generic" and source != reviewer:
            continue
        if phrase in low:
            return phrase
    return None


@dataclass(frozen=True)
class ReviewerVerdict:
    reviewer: str
    sight: Sight
    evidence: str = ""
    """What decided a non-REVIEWED verdict -- the phrase matched, or the commit
    reviewed -- so the judgement can be checked rather than taken on faith."""

    @property
    def trustworthy(self) -> bool:
        return self.sight.trustworthy


def classify(
    reviewer: str,
    remarks: Sequence[Remark],
    head: str | None = None,
) -> ReviewerVerdict:
    """Decide what a reviewer's output establishes about its sight of `head`.

    Affirmative evidence is checked FIRST, so a reviewer that hit its quota
    earlier and reviewed successfully later reads REVIEWED rather than BLIND --
    the verdict describes the current state, not the first thing that happened.
    """
    if not remarks:
        return ReviewerVerdict(reviewer, Sight.SILENT)

    # A PENDING review is a draft the reviewer has not submitted. Counting it
    # would let an unfinished review satisfy coverage.
    evidence = [r for r in remarks if r.kind in REVIEW_KINDS and r.state != "PENDING"]
    if evidence:
        if head is None:
            # The head could not be determined, so whether this review covers it
            # is unknown. The previous version returned REVIEWED here, which
            # asserted coverage of a commit it had never identified -- this
            # module's own founding defect, one branch away from the comment
            # warning against it.
            return ReviewerVerdict(reviewer, Sight.UNKNOWN, "pull request head unknown")
        anchors = [r.commit_id for r in evidence]
        if any(c == head for c in anchors):
            return ReviewerVerdict(reviewer, Sight.REVIEWED)
        if not any(anchors):
            # GitHub can return `commit_id: null`. Calling that STALE would claim
            # the review targeted an earlier commit with nothing to show it --
            # the same invented fact refused for an unknown head above.
            return ReviewerVerdict(reviewer, Sight.UNPROVEN, "review evidence with no commit")
        seen = next(c for c in anchors if c)
        return ReviewerVerdict(reviewer, Sight.STALE, f"last reviewed {seen[:8]}")

    for remark in remarks:
        hit = _match(remark.body, reviewer, BLINDNESS_PHRASES)
        if hit:
            return ReviewerVerdict(reviewer, Sight.BLIND, hit)

    for remark in remarks:
        hit = _match(remark.body, reviewer, UNPUBLISHED_PHRASES)
        if hit:
            return ReviewerVerdict(reviewer, Sight.UNPUBLISHED, hit)

    # It spoke, and nothing it said shows it read the diff. A greeting, a
    # progress notice, a template. The first version of this module called that
    # REVIEWED, which made "Sourcery is reviewing your pull request!" count as
    # coverage.
    return ReviewerVerdict(reviewer, Sight.UNPROVEN, "commented without review evidence")


@dataclass
class ReviewCoverage:
    """Who reviewed a pull request, and who only appeared to."""

    pr: str
    verdicts: list[ReviewerVerdict] = field(default_factory=list)
    expected: tuple[str, ...] = ()
    """The reviewers this estate declared it depends on. Coverage is judged
    against these and nothing else."""
    collected: bool = True
    """False when some evidence could not be fetched. Everything downstream then
    reads UNKNOWN, because a partial evidence set presented as a verdict is this
    subsystem's founding defect applied to its own inputs."""

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
    def stale(self) -> list[ReviewerVerdict]:
        return self._of(Sight.STALE)

    @property
    def unproven(self) -> list[ReviewerVerdict]:
        return self._of(Sight.UNPROVEN)

    @property
    def silent(self) -> list[ReviewerVerdict]:
        return self._of(Sight.SILENT)

    @property
    def unknown(self) -> list[ReviewerVerdict]:
        return self._of(Sight.UNKNOWN)

    @property
    def unmeasurable(self) -> list[ReviewerVerdict]:
        """Expected reviewers whose sight could not be established at all."""
        return [v for v in self.unknown if v.reviewer in self.expected]

    @property
    def _declared(self) -> bool:
        return bool(self.expected) and self.collected

    @property
    def _proven(self) -> bool:
        return any(v.trustworthy and v.reviewer in self.expected for v in self.verdicts)

    @property
    def coverage_known(self) -> bool:
        """Is there a declared set to judge coverage against, and full evidence?

        An expected reviewer whose verdict is UNKNOWN is missing evidence just
        as surely as a failed collection is: that reviewer may hold the review
        which would make this head covered, and nothing here can tell. Proven
        coverage settles the question anyway -- one trustworthy review of this
        head is enough -- so an UNKNOWN withholds the answer only while no
        expected reviewer has proved coverage.
        """
        if not self._declared:
            return False
        return self._proven or not self.unmeasurable

    @property
    def covered(self) -> bool:
        """Did a reviewer this estate DEPENDS ON review the current head?

        This is the question the pull request page cannot answer. A page with no
        review comments and a page whose every reviewer was out of credits look
        identical, and only one of them has been reviewed.
        """
        return self._declared and self._proven

    @property
    def summary(self) -> str:
        if not self.collected:
            return f"{self.pr}: UNKNOWN -- some review evidence could not be collected"
        if not self.expected:
            return f"{self.pr}: UNDETERMINED -- no reviewers declared, so coverage was not measured"
        if self.covered:
            names = ", ".join(
                sorted(v.reviewer for v in self.reviewed if v.reviewer in self.expected)
            )
            return f"{self.pr}: reviewed by {names}"
        if self.unmeasurable:
            names = ", ".join(sorted(v.reviewer for v in self.unmeasurable))
            return f"{self.pr}: UNKNOWN -- sight not established for {names}"
        reasons = []
        for label, group in (
            ("blind", self.blind),
            # UNPUBLISHED belongs here for the same reason the others do. It was
            # missing until 2026-10-06, so an expected reviewer that reached its
            # findings and could not publish them fell through to the generic
            # "no depended-on reviewer reported" -- which is false: one did
            # report. Latent today only because every phrase source currently
            # sits in `not_a_reviewer`; live the moment one does not.
            ("unpublished", self.unpublished),
            ("stale", self.stale),
            ("unproven", self.unproven),
            ("silent", self.silent),
        ):
            named = [v.reviewer for v in group if v.reviewer in self.expected]
            if named:
                reasons.append(f"{len(named)} {label}")
        detail = ", ".join(reasons) or "no depended-on reviewer reported"
        return f"{self.pr}: UNREVIEWED -- {detail}"


def assess(
    pr: str,
    remarks: Iterable[Remark],
    expected: Sequence[str] = (),
    author: str | None = None,
    head: str | None = None,
    not_a_reviewer: Sequence[str] = (),
    collected: bool = True,
) -> ReviewCoverage:
    """Group remarks by reviewer and classify each one against `head`.

    `author` is excluded: a pull request is not reviewed by whoever opened it,
    and the author's own replies to review threads were counted as coverage
    until this argument existed.

    `not_a_reviewer` is excluded too. A merge-queue checkbox is not a review,
    and listing such a bot in the manifest should keep it out of the verdicts
    rather than merely out of the arithmetic.
    """
    excluded = set(not_a_reviewer)
    grouped: dict[str, list[Remark]] = {name: [] for name in expected}
    for remark in remarks:
        if author is not None and remark.author == author:
            continue
        if remark.author in excluded and remark.author not in expected:
            continue
        grouped.setdefault(remark.author, []).append(remark)

    if not collected:
        # Classifying an empty bucket as SILENT would say "this reviewer said
        # nothing" when the truth is "we could not look" -- reporting a result
        # not measured, in the module written to refuse exactly that. The
        # summary line was already honest; the per-reviewer verdicts were not.
        verdicts = [
            ReviewerVerdict(name, Sight.UNKNOWN, "evidence could not be collected")
            for name in sorted(set(grouped) | set(expected))
        ]
    else:
        verdicts = [classify(name, rs, head) for name, rs in sorted(grouped.items())]
    return ReviewCoverage(
        pr=pr,
        verdicts=verdicts,
        expected=tuple(expected),
        collected=collected,
    )


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
