#!/usr/bin/env python3
"""Fail when the estate runs an AI system the governance register does not know.

A register written once is a snapshot, and a snapshot of a moving estate is
wrong within a month. Before this check, `MODEL_REGISTRY` held three cards
while the platform ran a crisis classifier, an empathy wrapper and a
third-party model router that were in it nowhere -- and nothing anywhere said
so.

Four things are enforced, in both directions:

  1. every AI-bearing code path below has a model card;
  2. every card maps to a path that still exists (a card for deleted code is
     worse than no card -- it asserts governance over nothing);
  3. HIGH-risk cards declare human oversight and real limitations, because a
     high-risk card with an empty limitations list is a claim nobody checked;
  4. no card claims a fairness metric it has measured, unless it says so --
     "unmeasured" is the honest default and must stay visible.

Adding an AI surface to the estate now fails CI until it is registered. That is
the point: the register cannot silently fall behind the code again.
"""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

#: model_id -> the code path that implements it. Curated deliberately rather
#: than auto-discovered: "does this perform inference or classify a person"
#: is a judgement, and a heuristic that guesses would either miss the ones
#: that matter or drown the check in false positives.
AI_BEARING: dict[str, str] = {
    "luminous": "src/bio_neural",
    "turings_hub": "src/personality",
    "imind_sensitivity": "src/imind/protocol.py",
    "resonate_empathy": "src/resonate/empathy.py",
    "ai_gateway": "src/ai_gateway",
    "mlflow_experiments": "workers/mlflow-service",
}


#: model_id -> the tier it may not be classified below without changing THIS
#: file. A risk tier is one enum value in one line of a large dict; lowering it
#: is the cheapest possible edit and, before this floor existed, the single most
#: consequential classification in the register could be quietly weakened with
#: nothing anywhere objecting. Downgrading now requires editing the check that
#: guards it, which is a visible act a reviewer sees.
MINIMUM_RISK: dict[str, str] = {
    # Infers a person's mental state from their words, and its output triggers
    # an intervention. The implementation being regular expressions makes it
    # less capable, not less consequential.
    "imind_sensitivity": "high",
}

_TIER_ORDER = ["minimal", "limited", "high", "unacceptable"]


def main() -> int:
    from src.compliance.ai_governance import MODEL_REGISTRY, RiskTier

    problems: list[str] = []

    for model_id, path in AI_BEARING.items():
        if not os.path.exists(os.path.join(REPO_ROOT, path)):
            problems.append(
                f"{model_id}: AI_BEARING points at {path!r}, which does not exist. "
                "Either the code moved (update the path) or the system is gone "
                "(remove the entry and its card)."
            )
        if model_id not in MODEL_REGISTRY:
            problems.append(
                f"{model_id}: runs at {path!r} with no model card. Add one to "
                "MODEL_REGISTRY in src/compliance/ai_governance.py before shipping it."
            )

    for model_id in MODEL_REGISTRY:
        if model_id not in AI_BEARING:
            problems.append(
                f"{model_id}: has a model card but no entry in AI_BEARING, so nothing "
                "checks that the code it governs still exists."
            )

    for model_id, floor in MINIMUM_RISK.items():
        card = MODEL_REGISTRY.get(model_id)
        if card is None:
            continue  # already reported above as a missing card
        if _TIER_ORDER.index(card.risk_tier.value) < _TIER_ORDER.index(floor):
            problems.append(
                f"{model_id}: classified {card.risk_tier.value!r} but MINIMUM_RISK "
                f"floors it at {floor!r}. Lowering this is a governance decision, "
                "not a field edit — change MINIMUM_RISK in this file, with a reason, "
                "so somebody reviews it."
            )

    for model_id, card in MODEL_REGISTRY.items():
        if card.risk_tier is RiskTier.HIGH:
            if not card.known_limitations:
                problems.append(
                    f"{model_id}: HIGH risk with an empty known_limitations list. "
                    "A high-risk system with no recorded limitations is a claim "
                    "nobody has checked."
                )
            if not any("14" in a or "oversight" in a.lower() for a in card.eu_ai_act_articles):
                problems.append(
                    f"{model_id}: HIGH risk without Art. 14 (human oversight) recorded."
                )
            if not card.prohibited_uses:
                problems.append(f"{model_id}: HIGH risk with no prohibited uses recorded.")

    if problems:
        print("AI register conformance: FAIL")
        for p in problems:
            print(f"  - {p}")
        return 1

    high = [m for m, c in MODEL_REGISTRY.items() if c.risk_tier is RiskTier.HIGH]
    print(
        f"AI register conformance: OK — {len(MODEL_REGISTRY)} systems registered, "
        f"{len(high)} high-risk ({', '.join(high) or 'none'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
