"""The Holding Score — what The Basement keeps, promotes, or lets go.

The Library sits directly above The Basement in the same building. Everything
contextual lands in the Basement first, stored by data type; the Holding Score is
what decides whether a record rises to the Library, stays where it is, or is
marked for deletion.

WHY THIS IS NOT ONE NUMBER

The named inputs — legal requirement, urgency, sensitivity, usefulness, learning
value — do not point the same way. Sensitivity argues *retain and protect*. Low
usefulness argues *delete*. Collapse them into a single scalar and a highly
sensitive record with no learning value scores low and gets deleted, which is a
compliance breach dressed up as tidying.

So one assessment produces **two independent verdicts**:

    retention  — MUST_RETAIN / RETAIN / REVIEW / MARK_FOR_DELETION
    promotion  — PROMOTE / WATCH / NO_VALUE

A record can be MUST_RETAIN and NO_VALUE at once: keep it because the law says
so, and never write an article about it. That combination is common and a single
score cannot express it.

THE LEGAL FLOOR IS A GATE, NOT A WEIGHT

`legal_hold`, a retention class that has not expired, and LOCAL_ONLY jurisdiction
are hard overrides evaluated before anything is weighed. A legal obligation
cannot be outvoted by "nobody read this" — that is the whole point of an
obligation. Everything else is a weighted judgement; these are not.

DIMENSIONS BEYOND THE FIVE NAMED

The five named inputs answer "is this worth keeping". These additions answer
"how would we know", which is the harder half:

  corroboration      how many other records say the same thing. One observation
                     is an anecdote; the fifth is a pattern. Already computed by
                     promotion.py's clustering.
  linkage_density    how many Town Hall epics/stories/incidents, conversations,
                     commits, DocUtari documents and Artifactory builds
                     reference it. A record wired into an epic, a commit and a
                     conversation carries context an orphan cannot.
  access_recency     has anyone actually read it. Never read in 90 days is the
                     strongest available evidence of low usefulness — and it is
                     evidence, where "usefulness" alone is an opinion.
  provenance         human-authored outranks machine-generated. A person's
                     decision is a primary source; a log line is a symptom.
  irreplaceability   could it be regenerated? A build log can be rebuilt; a
                     customer conversation cannot. Irreplaceable records deserve
                     retention even at low usefulness.
  derivation         has anything been built from it — an article, a fix, a
                     Learning Pathway. Proof of value already realised.
  novelty            first of its kind, or the five-hundredth duplicate.
  contradiction      does it conflict with an existing Library article? The most
                     valuable single signal here: a contradiction means either
                     the article or the record is wrong, and either way somebody
                     needs to look. Redundant agreement teaches nothing;
                     disagreement teaches something.
  retention_cost     size. Not a reason to delete on its own, but the tie-break
                     between two otherwise equal low-value records.

Deletion is never destruction: a marked record leaves the Basement but is held
compressed in a backend archive for 30 days, so a wrong call is recoverable.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

DAY = 86400.0
ARCHIVE_GRACE_DAYS = int(os.environ.get("BASEMENT_ARCHIVE_GRACE_DAYS", "30"))
# Never read in this long is treated as evidence of low usefulness.
STALE_ACCESS_DAYS = float(os.environ.get("BASEMENT_STALE_ACCESS_DAYS", "90"))
PROMOTE_AT = float(os.environ.get("BASEMENT_PROMOTE_AT", "0.60"))
DELETE_BELOW = float(os.environ.get("BASEMENT_DELETE_BELOW", "0.20"))


class Retention(str, Enum):
    MUST_RETAIN = "must_retain"  # legal floor — deletion is not available
    RETAIN = "retain"
    REVIEW = "review"  # a human decides
    MARK_FOR_DELETION = "mark_for_deletion"


class Promotion(str, Enum):
    PROMOTE = "promote"  # raise a Library draft
    WATCH = "watch"  # keep accruing; not yet a pattern
    NO_VALUE = "no_value"


# Weights for the value judgement only. The legal floor is not in here — it is a
# gate above this, not a heavy weight inside it.
WEIGHTS: dict[str, float] = {
    "learning_value": 0.20,
    "corroboration": 0.16,
    "contradiction": 0.14,
    "linkage_density": 0.12,
    "usefulness": 0.10,
    "irreplaceability": 0.10,
    "novelty": 0.08,
    "provenance": 0.06,
    "access_recency": 0.04,
}


@dataclass
class Assessment:
    """One record's Holding Score, with every input kept visible."""

    record_id: str = ""
    data_type: str = ""
    value_score: float = 0.0
    retention: Retention = Retention.REVIEW
    promotion: Promotion = Promotion.WATCH
    dimensions: dict[str, float] = field(default_factory=dict)
    legal_reasons: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    delete_after: float | None = None  # when the 30-day archive expires

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "data_type": self.data_type,
            "value_score": round(self.value_score, 4),
            "retention": self.retention.value,
            "promotion": self.promotion.value,
            "dimensions": {k: round(v, 3) for k, v in self.dimensions.items()},
            "legal_reasons": self.legal_reasons,
            "reasons": self.reasons,
            "delete_after": self.delete_after,
        }


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _legal_floor(meta: dict[str, Any]) -> list[str]:
    """Hard reasons deletion is unavailable. Evaluated before any weighting."""
    reasons = []
    if meta.get("legal_hold"):
        reasons.append("legal_hold is set")
    jur = str(meta.get("jurisdiction") or "").upper()
    if jur == "LOCAL_ONLY":
        reasons.append(
            "LOCAL_ONLY jurisdiction — residency-bound, cannot be moved or purged freely"
        )
    rc = str(meta.get("retention_class") or "").lower()
    if rc in ("permanent", "statutory", "regulatory"):
        reasons.append(f"retention_class={rc!r} has no expiry")
    elif rc:
        until = meta.get("retention_until")
        if isinstance(until, (int, float)) and until > time.time():
            reasons.append(f"retention_class={rc!r} runs until {until}")
    cls = str(meta.get("classification") or "").lower()
    if cls in ("restricted", "top_secret"):
        # Not a value judgement: these must survive for audit even when nothing
        # is learned from them, and they must never be promoted.
        reasons.append(f"classification={cls!r} requires audit retention")
    if meta.get("security_event") or str(meta.get("source", "")).lower() == "security":
        reasons.append("security-source records are always retained")
    return reasons


def _sensitivity(meta: dict[str, Any], content: str) -> float:
    """0..1. High sensitivity blocks promotion; it does not raise value."""
    cls = str(meta.get("classification") or "").lower()
    base = {
        "public": 0.0,
        "internal": 0.2,
        "confidential": 0.6,
        "restricted": 0.85,
        "top_secret": 1.0,
    }.get(cls, 0.3)
    if meta.get("contains_pii"):
        base = max(base, 0.7)
    else:
        # Prometheus's own primitive — already implemented, so use it rather
        # than a second, divergent pattern set.
        try:
            from src.security.log_redactor import contains_pii

            if content and contains_pii(content):
                base = max(base, 0.7)
        except Exception:  # noqa: BLE001 — detection must not break scoring
            pass
    return _clamp(base)


def assess(record: Any, signals: dict[str, Any] | None = None) -> Assessment:
    """Score one Basement record.

    `signals` carries what the record cannot know about itself — corroboration
    count, link count, last-read time, whether it contradicts an article. Absent
    signals are treated as neutral-to-unfavourable rather than assumed good: a
    record with no evidence of value should not inherit value by default.
    """
    signals = signals or {}
    meta = dict(getattr(record, "metadata", {}) or {})
    content = str(getattr(record, "content", "") or "")
    now = time.time()

    a = Assessment(
        record_id=str(getattr(record, "id", "") or ""),
        data_type=str(meta.get("data_type") or getattr(record, "event_type", "") or "unknown"),
    )

    a.legal_reasons = _legal_floor(meta)
    sensitivity = _sensitivity(meta, content)

    corr = int(signals.get("corroboration", 0) or 0)
    links = int(signals.get("linkage_count", 0) or 0)
    derived = int(signals.get("derived_artifacts", 0) or 0)
    last_read = signals.get("last_read_at")
    duplicates = int(signals.get("duplicate_count", 0) or 0)

    d = a.dimensions
    # Diminishing returns: the fifth corroboration matters far less than the second.
    d["corroboration"] = _clamp(corr / 5.0)
    d["linkage_density"] = _clamp(links / 6.0)
    d["contradiction"] = 1.0 if signals.get("contradicts_article") else 0.0
    d["novelty"] = _clamp(1.0 - (duplicates / 10.0))
    d["provenance"] = 1.0 if signals.get("human_authored") else 0.35
    d["irreplaceability"] = (
        1.0 if signals.get("irreplaceable") else (0.2 if signals.get("regenerable") else 0.5)
    )
    d["learning_value"] = _clamp(
        float(signals.get("learning_value", 0.0)) or (0.5 if (corr >= 2 or derived) else 0.15)
    )
    d["usefulness"] = _clamp(float(signals.get("usefulness", 0.0)) or (0.6 if derived else 0.2))

    if isinstance(last_read, (int, float)) and last_read > 0:
        age_days = (now - last_read) / DAY
        d["access_recency"] = _clamp(1.0 - (age_days / STALE_ACCESS_DAYS))
    else:
        d["access_recency"] = 0.0
        a.reasons.append("never read — strongest available evidence of low usefulness")

    a.value_score = sum(d[k] * w for k, w in WEIGHTS.items() if k in d)

    # ── Retention verdict ──────────────────────────────────────────────────
    if a.legal_reasons:
        a.retention = Retention.MUST_RETAIN
        a.reasons.append("legal floor applies — deletion unavailable regardless of value")
    elif d["irreplaceability"] >= 0.9:
        a.retention = Retention.RETAIN
        a.reasons.append("irreplaceable — cannot be regenerated if wrong")
    elif a.value_score >= DELETE_BELOW:
        a.retention = Retention.RETAIN
    elif signals.get("age_days", 0) and float(signals["age_days"]) < 7:
        # Too young to judge. Corroboration arrives late; deleting at day two
        # destroys the evidence that would have made it a pattern by day ten.
        a.retention = Retention.REVIEW
        a.reasons.append("under 7 days old — too early to judge value")
    else:
        a.retention = Retention.MARK_FOR_DELETION
        a.delete_after = now + (ARCHIVE_GRACE_DAYS * DAY)
        a.reasons.append(
            f"value {a.value_score:.2f} below {DELETE_BELOW} with no legal floor — "
            f"leaves the Basement, held compressed for {ARCHIVE_GRACE_DAYS} days"
        )

    # ── Promotion verdict ──────────────────────────────────────────────────
    # Sensitivity gates promotion independently of value. A Library article is
    # user-visible; restricted material must not become one however much could
    # be learned from it.
    if sensitivity >= 0.85:
        a.promotion = Promotion.NO_VALUE
        a.reasons.append(
            f"sensitivity {sensitivity:.2f} blocks promotion — the Library is user-visible"
        )
    elif d["contradiction"]:
        # Promoted on the contradiction alone, without needing to clear the value
        # threshold. A record that disagrees with a published article means either
        # the article or the record is wrong, and a wrong article is actively
        # misleading everyone who reads it. Waiting for corroboration here would
        # leave known-bad guidance standing. This is the one signal allowed to
        # promote on a single observation.
        a.promotion = Promotion.PROMOTE
        a.reasons.append(
            "contradicts a published Library article — the article or the record is "
            "wrong, and a wrong article misleads every reader until resolved"
        )
    elif corr < 2:
        a.promotion = Promotion.WATCH
        a.reasons.append("single uncorroborated observation — an incident, not yet a pattern")
    elif a.value_score >= PROMOTE_AT:
        a.promotion = Promotion.PROMOTE
        a.reasons.append(f"value {a.value_score:.2f} at or above {PROMOTE_AT} with corroboration")
    else:
        a.promotion = Promotion.WATCH

    a.dimensions["sensitivity"] = sensitivity  # recorded, deliberately unweighted
    return a


def summarise(assessments: list[Assessment]) -> dict[str, Any]:
    """Roll up a batch — the shape a Basement /holding-score endpoint returns."""
    out: dict[str, Any] = {
        "assessed": len(assessments),
        "retention": {r.value: 0 for r in Retention},
        "promotion": {p.value: 0 for p in Promotion},
        "promote_ids": [],
        "delete_ids": [],
    }
    for a in assessments:
        out["retention"][a.retention.value] += 1
        out["promotion"][a.promotion.value] += 1
        if a.promotion is Promotion.PROMOTE:
            out["promote_ids"].append(a.record_id)
        if a.retention is Retention.MARK_FOR_DELETION:
            out["delete_ids"].append(a.record_id)
    return out
