"""Basement → The Library promotion: turn recurring evidence into an article.

THE LEG THIS CLOSES

The learning pipeline runs Chaos Party → Observatory → Basement → Library →
Think Tank, with Section 7 supplying external context. The first three legs now
carry data. This is the fourth: nothing promoted a confirmed pattern out of the
evidence store, so findings accumulated in The Basement and were never surfaced
for anyone to act on. Evidence nobody reads is the same as no evidence.

WHAT "CONFIRMED PATTERN" MEANS HERE

Not "something failed" — a single failure is an incident, not a pattern, and
promoting it would bury real signal under noise. A pattern requires **recurrence
across distinct observations**, and this module recognises two kinds:

  * a **cluster** — several failures whose messages are near-identical, which
    almost always means one root cause presenting many times. Reporting seven
    symptoms as seven articles hides the fact that they are one bug.
  * a **sustained regression** — a test whose pass rate dropped against its own
    baseline and stayed down, as classified upstream by the Chaos Party bridge.

Both thresholds are configurable and both are deliberately conservative. The
cost of a missed pattern is a delayed fix; the cost of a false pattern is an
admin learning to ignore the queue, which disables the whole mechanism.

WHY difflib AND NOT EMBEDDINGS

The estate has FAISS, sentence-transformers, Qdrant and Meilisearch available,
and any of them could cluster these strings. `difflib.SequenceMatcher` is used
instead because error messages are short, highly templated strings where
character-level similarity is exactly the right signal; because it is
deterministic, so the same evidence always yields the same clusters and an
admin's decision stays reproducible; and because it needs no model download,
no index to keep warm, and no dependency beyond the standard library. Reaching
for embeddings here would add operational weight and non-determinism to buy
semantic matching that templated stack traces do not need.

Promoted articles are created as DRAFT with `source="observatory"`, which is the
Library's existing vocabulary for this provenance. A draft is a proposal for an
admin; publishing a machine-detected pattern automatically would let a false
positive become something the platform subsequently treats as established fact.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)

# A cluster needs this many near-identical observations to count as a pattern.
MIN_CLUSTER_SIZE = int(os.environ.get("BASEMENT_PROMOTION_MIN_CLUSTER", "3"))
# Similarity above which two messages are treated as the same failure.
SIMILARITY_THRESHOLD = float(os.environ.get("BASEMENT_PROMOTION_SIMILARITY", "0.82"))
# How many recent Basement records to consider in one pass.
SCAN_LIMIT = int(os.environ.get("BASEMENT_PROMOTION_SCAN_LIMIT", "500"))

# Volatile substrings that differ between otherwise identical failures. Left in
# place, they drag similarity below the threshold and split one root cause into
# several clusters — the exact failure this module exists to prevent.
_NOISE = [
    (re.compile(r"0x[0-9a-fA-F]+"), "<addr>"),
    (
        re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        ),
        "<uuid>",
    ),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*"), "<ts>"),
    (re.compile(r"\bline \d+\b"), "line <n>"),
    # No trailing \b on these two: durations and codes are routinely written with
    # a unit suffix ("30.5s", "503ms"), and a closing word boundary fails to
    # match there because digit→letter is not a boundary. That left the volatile
    # number in place and split one root cause across several clusters — which is
    # precisely the outcome this normalisation exists to prevent. Float stays
    # ahead of int so "30.5" is not consumed as two separate integers.
    (re.compile(r"\b\d+\.\d+"), "<float>"),
    (re.compile(r"\b\d{3,}"), "<num>"),
    # A redaction pattern, not a filesystem path: it strips temp paths *out* of
    # failure messages before clustering, so the same failure from two different
    # scratch directories compares equal. Bandit's hardcoded-tmp check matches
    # the literal anywhere it appears — including inside the regex that removes
    # it — so the suppression below is on the pattern, not on any temp-file use.
    (re.compile(r"/tmp/\S+"), "<tmp>"),  # nosec B108
]


def normalise(message: str) -> str:
    """Strip volatile detail so the same failure compares as the same string."""
    out = (message or "").strip()
    for pattern, repl in _NOISE:
        out = pattern.sub(repl, out)
    return " ".join(out.split()).lower()


@dataclass
class Pattern:
    """A confirmed, promotable pattern."""

    kind: str  # "cluster" | "regression"
    signature: str
    occurrences: int
    record_ids: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    sample: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def confidence(self) -> str:
        """Coarse band, from occurrence count only.

        Deliberately not a percentage: the inputs do not support that precision
        and a number would imply rigour the method does not have.
        """
        if self.occurrences >= MIN_CLUSTER_SIZE * 3:
            return "high"
        if self.occurrences >= MIN_CLUSTER_SIZE * 2:
            return "medium"
        return "low"


def _failure_records(records: list[Any]) -> list[Any]:
    """Records that represent a failing or erroring test run."""
    out = []
    for r in records:
        action = str(getattr(r, "event_type", "") or "")
        meta = getattr(r, "metadata", {}) or {}
        if action.startswith("test.run.") and action.rsplit(".", 1)[-1] in ("fail", "error"):
            out.append(r)
        elif meta.get("trend_regression"):
            out.append(r)
    return out


def cluster_failures(records: list[Any]) -> list[Pattern]:
    """Group near-identical failures. Greedy single-pass — O(n·k), k = clusters.

    Greedy rather than exhaustive because pairwise clustering over a large scan
    window is quadratic and the extra precision does not change which patterns
    cross the promotion threshold.
    """
    buckets: list[dict[str, Any]] = []
    for rec in records:
        meta = getattr(rec, "metadata", {}) or {}
        raw = meta.get("error_msg") or getattr(rec, "content", "") or ""
        sig = normalise(raw)
        if not sig:
            continue
        for b in buckets:
            if SequenceMatcher(None, sig, b["signature"]).ratio() >= SIMILARITY_THRESHOLD:
                b["records"].append(rec)
                b["tests"].add(meta.get("resource") or meta.get("test") or "unknown")
                break
        else:
            buckets.append(
                {
                    "signature": sig,
                    "sample": raw[:400],
                    "records": [rec],
                    "tests": {meta.get("resource") or meta.get("test") or "unknown"},
                }
            )

    patterns = []
    for b in buckets:
        if len(b["records"]) < MIN_CLUSTER_SIZE:
            continue
        patterns.append(
            Pattern(
                kind="cluster",
                signature=b["signature"][:200],
                occurrences=len(b["records"]),
                record_ids=[getattr(r, "id", "") for r in b["records"]],
                tests=sorted(t for t in b["tests"] if t),
                sample=b["sample"],
                evidence={"distinct_tests": len(b["tests"])},
            )
        )
    return patterns


def regression_patterns(records: list[Any]) -> list[Pattern]:
    """One pattern per test the upstream bridge classified as regressing."""
    by_test: dict[str, list[Any]] = {}
    for rec in records:
        meta = getattr(rec, "metadata", {}) or {}
        if meta.get("trend") != "regression":
            continue
        test = meta.get("resource") or "unknown"
        by_test.setdefault(test, []).append(rec)

    out = []
    for test, recs in by_test.items():
        latest = getattr(recs[0], "metadata", {}) or {}
        out.append(
            Pattern(
                kind="regression",
                signature=f"regression:{test}",
                occurrences=len(recs),
                record_ids=[getattr(r, "id", "") for r in recs],
                tests=[test],
                sample=str(latest.get("error_msg") or "")[:400],
                evidence={
                    "recent_pass_rate": latest.get("trend_recent_pass_rate"),
                    "baseline_pass_rate": latest.get("trend_baseline_pass_rate"),
                    "predicted_next_fail": latest.get("trend_predicted_next_fail"),
                    "confidence_floor": latest.get("trend_confidence_floor"),
                },
            )
        )
    return out


def render_article(p: Pattern) -> tuple[str, str, list[str]]:
    """Render a pattern as (title, body, tags) for an admin to review."""
    if p.kind == "regression":
        test = p.tests[0] if p.tests else "unknown"
        title = f"Regression detected: {test}"
    else:
        subject = p.tests[0] if len(p.tests) == 1 else f"{len(p.tests)} tests"
        title = f"Recurring failure across {subject} ({p.occurrences} observations)"

    lines = [
        f"**Pattern kind:** {p.kind}",
        f"**Observations:** {p.occurrences}",
        f"**Confidence:** {p.confidence} (band from occurrence count, not a probability)",
        "",
        "## Why this was promoted",
        "",
    ]
    if p.kind == "regression":
        e = p.evidence
        lines += [
            f"A test's pass rate fell against its own baseline: "
            f"recent {e.get('recent_pass_rate')} vs baseline {e.get('baseline_pass_rate')}. "
            f"The Chaos Party bridge classified this as a regression rather than a flake "
            f"because the drop persisted across the recent window.",
            "",
            f"Estimated chance the next run also fails: {e.get('predicted_next_fail')}. "
            f"That is a ranking aid drawn from the recent window, not a forecast.",
        ]
    else:
        lines += [
            f"{p.occurrences} failures across {p.evidence.get('distinct_tests')} distinct "
            f"test(s) share a near-identical message after volatile detail (addresses, "
            f"UUIDs, timestamps, line numbers) was normalised away. That pattern usually "
            f"means one root cause presenting repeatedly rather than several unrelated bugs.",
        ]

    lines += [
        "",
        "## Affected tests",
        "",
        *[f"- `{t}`" for t in p.tests[:20]],
        "",
        "## Representative message",
        "",
        "```",
        p.sample or "(none captured)",
        "```",
        "",
        "## Evidence",
        "",
        f"{len(p.record_ids)} Basement record(s): "
        + ", ".join(f"`{r}`" for r in p.record_ids[:10])
        + (" …" if len(p.record_ids) > 10 else ""),
        "",
        "## What this article is not",
        "",
        "A draft raised automatically from evidence, awaiting review. It asserts that "
        "something recurred, not what causes it or how to fix it. Think Tank studies "
        "confirmed patterns and designs the remediation; Section 7 supplies external "
        "context — recent releases, known issues, published work bearing on the problem.",
    ]

    tags = [
        "auto-promoted",
        "basement-evidence",
        p.kind,
        f"confidence-{p.confidence}",
        promotion_key(p.signature),
    ]
    return title, "\n".join(lines), tags


def promotion_key(signature: str) -> str:
    """A stable per-pattern tag, so the same evidence promotes exactly once.

    Promotion is now reachable over HTTP (`POST /basement/promote`), which makes
    the write path retryable: a client retry, an impatient second click, or two
    admins acting on the same alert would each raise another Library draft from
    identical Basement evidence. Duplicate drafts are worse than none -- the
    queue is a proposal list an admin reads, and a list that repeats itself is
    one they stop reading.

    Keyed on the pattern signature rather than the rendered title, because the
    title carries occurrence counts and moves as more evidence arrives, while
    the signature is the identity of the pattern itself. Hashed and truncated
    only to keep it usable as a tag; collisions at 64 bits over a few hundred
    patterns are not a real risk, and the cost of one would be a single skipped
    draft, not a corrupted article.
    """
    digest = hashlib.sha256(signature.encode("utf-8", errors="replace")).hexdigest()
    return f"promotion-{digest[:16]}"


def promote(limit: int = SCAN_LIMIT, dry_run: bool = False) -> dict[str, Any]:
    """Scan Basement evidence and raise a Library draft per confirmed pattern.

    Fail-open: promotion is an enrichment step, so an unavailable Library must
    not raise into whatever triggered the scan. Returns what it found either
    way, and `dry_run=True` reports without writing — the mode to use when
    tuning thresholds against real evidence.
    """
    result: dict[str, Any] = {
        "scanned": 0,
        "failures": 0,
        "patterns": 0,
        "promoted": 0,
        "skipped": 0,
        "duplicates": 0,
        "details": [],
    }
    try:
        from src.basement.archive import ArchiveSource, get_basement

        records = get_basement().recent(limit=limit, source=ArchiveSource.OBSERVATORY)
    except Exception as exc:  # noqa: BLE001 — enrichment never breaks the caller
        logger.warning("Basement unavailable for promotion: %s", exc)
        return result

    result["scanned"] = len(records)
    failures = _failure_records(records)
    result["failures"] = len(failures)

    patterns = cluster_failures(failures) + regression_patterns(failures)
    result["patterns"] = len(patterns)
    if not patterns or dry_run:
        result["details"] = [
            {"kind": p.kind, "occurrences": p.occurrences, "tests": p.tests[:5]} for p in patterns
        ]
        result["skipped"] = len(patterns) if dry_run else 0
        return result

    try:
        from src.library.knowledge_base import ArticleStatus, get_library

        library = get_library()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Library unavailable for promotion: %s", exc)
        result["skipped"] = len(patterns)
        return result

    for p in patterns:
        title, body, tags = render_article(p)
        key = promotion_key(p.signature)
        try:
            if library.by_tag(key, limit=1):
                # Already raised from this evidence. Not an error and not a
                # skip-for-failure: the requested end state already holds.
                result["duplicates"] += 1
                result["details"].append({"title": title, "kind": p.kind, "duplicate": True})
                continue
        except Exception as exc:  # noqa: BLE001 -- a lookup failure must not
            # silently become a duplicate write, so it is recorded and skipped.
            logger.warning("Duplicate check failed for %r: %s", p.signature[:60], exc)
            result["skipped"] += 1
            continue

        try:
            art = library.create(
                title=title,
                body=body,
                tags=tags,
                author="The Observatory",
                source="observatory",
                # DRAFT, not PUBLISHED: a proposal for an admin, not knowledge.
                status=ArticleStatus.DRAFT,
            )
            result["promoted"] += 1
            result["details"].append({"article_id": art.id, "title": title, "kind": p.kind})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to promote pattern %r: %s", p.signature[:60], exc)
            result["skipped"] += 1
    return result
