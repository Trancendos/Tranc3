#!/usr/bin/env python3
"""Render the gate-engine specification from the gate engine.

The specification and the resolver must agree about what the decisions are,
which tiers fail closed, and how several violations resolve. Written by hand
they agree until the first change; generated, the document is the code's own
account of itself and `--check` fails when the two drift.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.compliance.ai_governance import RiskTier  # noqa: E402
from src.gates.decision import (  # noqa: E402
    _SEVERITY,
    Decision,
    GateContext,
    Violation,
    decide,
    fails_closed,
)

OUTPUT = REPO / "docs" / "governance" / "GATE-ENGINE.md"

_MEANING = {
    Decision.ALLOW: "Continue normally.",
    Decision.BLOCK: "Refuse the request or action.",
    Decision.HOLD: "Pause for a named human approver.",
    Decision.REDACT: "Continue without the offending content.",
    Decision.DEGRADE: "Continue with reduced capability or a safe fallback.",
}


def _context(tier) -> GateContext:
    return GateContext(
        trace_id="trc_example",
        tenant_id="tenant_acme",
        actor_id="user_1",
        action="create_change_recommendation",
        risk_tier=tier,
    )


def render() -> str:
    out: list[str] = [
        "# Deterministic Gate Engine",
        "",
        "> **Generated from `src/gates/decision.py` by",
        "> `scripts/generate_gate_engine_doc.py`.** Do not edit by hand — change",
        "> the resolver and regenerate. `--check` fails CI when the two disagree.",
        "",
        "## What it is for",
        "",
        "The platform already had a request-path gate before this one:",
        "`MagnaCartaMiddleware`, installed on the app at `api.py`, inside",
        "`ZeroTrustASGIMiddleware` so it can read decoded claims. Two things stop",
        "it being a control.",
        "",
        "`MAGNA_CARTA_ENABLED` defaults to `false` — in",
        "`src/compliance/magna_carta.py` and again in",
        "`docker-compose.production.yml` as `${MAGNA_CARTA_ENABLED:-false}` — so",
        "`dispatch` returns before a single rule runs. And when it is switched on",
        "it is advisory: the outcome is a boolean, and blocking needs a second",
        "flag in a config file.",
        "",
        "A boolean also cannot say what governance needs to say. *Not compliant*",
        "collapses four different responses into one: refuse it, hold it for a",
        "human, strip the offending part and continue, or continue with less",
        "capability. This engine is that vocabulary and the resolver over it.",
        "",
        "It does not change the default. Turning a security control from advisory",
        "to enforcing changes production behaviour and belongs to the owner, not",
        "to the change that supplied the decision model it lacked.",
        "",
        "## Decisions",
        "",
        "| Decision | Meaning |",
        "|---|---|",
    ]
    for decision in Decision:
        out.append(f"| `{decision.value}` | {_MEANING[decision]} |")

    out += [
        "",
        "### Severity order",
        "",
        "A request carrying several violations takes the strongest response any",
        "one of them demands. Severity is ranked by how much is withheld from the",
        "caller, ascending:",
        "",
        "```text",
        "  " + "  <  ".join(d.value for d in _SEVERITY),
        "```",
        "",
        "Not alphabetically. Sorted as text the order would be "
        + ", ".join(sorted(d.value for d in Decision))
        + ", which ranks `redact` above `block` — so a prohibited action would",
        "proceed with its address masked.",
        "",
        "## Risk tiers",
        "",
        "Tiers are `RiskTier` from `src/compliance/ai_governance.py`, mapped to",
        "the EU AI Act. When policy cannot be read, what happens depends on what",
        "is at stake:",
        "",
        "| Tier | Policy unreadable | Why |",
        "|---|---|---|",
    ]
    for tier in RiskTier:
        outcome = decide(_context(tier), policy_available=False).decision
        why = (
            "an unenforceable control on a consequential action is worse than an "
            "outage, because it looks like it worked"
            if fails_closed(tier)
            else "refusing everything on a policy-store hiccup teaches operators to "
            "disable the gate, which is the failure it exists to prevent"
        )
        out.append(f"| `{tier.value}` | `{outcome.value}` | {why} |")

    out += [
        "",
        "### The unrecognised tier",
        "",
        "A tier the engine does not recognise — absent, empty, misspelled, or",
        "from a newer policy version — is treated as the **highest**, never the",
        "lowest. That is the fail-open this engine exists to avoid: an",
        "unclassified request is the one most likely to need the gate, and",
        "mapping it to `minimal` waves exactly that through.",
        "",
        "## Prohibited actions",
        "",
        "`unacceptable` is Article 5 — prohibited outright. It blocks with no",
        "violation required, and a clean rule evaluation cannot excuse it.",
        "",
        "## Determinism",
        "",
        "`decide()` is pure: no clock, no randomness, no I/O, no model. The same",
        "context and violations give the same outcome, which is what makes a",
        "trace replayable and a policy change regression-testable. Models may",
        "classify, score and recommend *into* the context; they never decide.",
        "",
        "`GateContext` is frozen for the same reason — a decision re-derived from",
        "a mutated context is not the decision that was taken.",
        "",
        "## Worked outcomes",
        "",
        "| Situation | Decision |",
        "|---|---|",
    ]

    examples = [
        ("clean evaluation, limited risk", decide(_context(RiskTier.LIMITED), [])),
        (
            "prohibited action, nothing flagged",
            decide(_context(RiskTier.UNACCEPTABLE), []),
        ),
        (
            "policy unreadable, high risk",
            decide(_context(RiskTier.HIGH), policy_available=False),
        ),
        (
            "policy unreadable, minimal risk",
            decide(_context(RiskTier.MINIMAL), policy_available=False),
        ),
        (
            "one rule wants redaction, another wants approval",
            decide(
                _context(RiskTier.LIMITED),
                [
                    Violation("C1", "mask the address", Decision.REDACT),
                    Violation("C2", "needs a named approver", Decision.HOLD),
                ],
            ),
        ),
    ]
    for label, outcome in examples:
        out.append(f"| {label} | `{outcome.decision.value}` |")

    out += [
        "",
        "## What an outcome carries",
        "",
        "Every decision records the trace id, tenant, actor, action, resolved",
        "risk tier, policy version, the control ids of every rule that fired —",
        "not only the strongest — and whether policy was readable at all. An",
        "operator fixing a blocked request needs the whole set; the winning rule",
        "alone tells them to fix one thing and hit the next block immediately.",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    rendered = render()
    if args.check:
        if not OUTPUT.exists():
            print(f"MISSING: {OUTPUT.relative_to(REPO)} has never been generated.")
            return 1
        if OUTPUT.read_text() != rendered:
            print(f"DRIFT: {OUTPUT.relative_to(REPO)} no longer matches src/gates/decision.py.")
            print("Run: python scripts/generate_gate_engine_doc.py")
            return 1
        print(f"Gate engine doc: PASSED — {OUTPUT.relative_to(REPO)} matches the resolver")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered)
    print(f"Wrote {OUTPUT.relative_to(REPO)} ({len(list(Decision))} decisions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
