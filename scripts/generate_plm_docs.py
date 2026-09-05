#!/usr/bin/env python3
"""Generate the PLM policy and procedure from the gate criteria themselves.

The brief asks that everything built carries documentation, guides, policies
and procedures. Hand-written governance documents are the ones that drift:
the criteria change in code, the procedure keeps describing last quarter's
gate, and the two disagree in the exact situation where somebody consults the
document instead of the source.

So the document is derived. `src/townhall/plm.py` is the single statement of
what a gate requires; this renders it. Run with `--check` to fail when the
committed copy no longer matches, which is how the drift is caught in CI
rather than by the next person to read it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.townhall.plm import (  # noqa: E402
    CRITERIA,
    STAGE_ORDER,
    DeliverableKind,
    Stage,
    criteria_for,
)

OUTPUT = REPO / "docs" / "governance" / "PLM-GATES.md"

_STAGE_PURPOSE = {
    Stage.CONCEPT: "Establish that the thing is worth building at all.",
    Stage.INITIATION: "Authorise the work and name who is accountable for it.",
    Stage.DESIGN: "Settle how it will look and behave before anyone builds it.",
    Stage.BUILD: "Produce the artefact and prove what went into it.",
    Stage.VALIDATION: "Prove it does what it was commissioned to do.",
    Stage.RELEASE: "Hand it over with the documentation somebody else can run it from.",
    Stage.CLOSED: "Terminal. Nothing leaves this stage.",
}


def _matrix() -> list[str]:
    """Which criteria apply to which deliverable kind, as a table."""
    kinds = list(DeliverableKind)
    lines = [
        "| Criterion | Stage | Evidence from | " + " | ".join(k.value for k in kinds) + " |",
        "|---|---|---|" + "---|" * len(kinds),
    ]
    for crit in CRITERIA:
        marks = []
        for kind in kinds:
            if not crit.applies(kind):
                marks.append("—")
            elif crit.mandatory:
                marks.append("**required**")
            else:
                marks.append("optional")
        lines.append(
            f"| `{crit.id}` | {crit.stage.value} | {crit.supplied_by} | " + " | ".join(marks) + " |"
        )
    return lines


def render() -> str:
    out: list[str] = [
        "# Product Lifecycle Gates",
        "",
        "> **Generated from `src/townhall/plm.py` by `scripts/generate_plm_docs.py`.**",
        "> Do not edit by hand — change the criteria in code and regenerate.",
        "> `scripts/generate_plm_docs.py --check` fails CI when the two disagree.",
        "",
        "## Policy",
        "",
        "Every deliverable the platform produces — an application, a game, an",
        "image, a video, a design system, a module, a template or a document —",
        "is raised in The Town Hall as a lifecycle record and moves through the",
        "stages below in order. A stage boundary is a gate.",
        "",
        "A gate opens only when every mandatory criterion for that deliverable's",
        "kind carries **passing** evidence, or an approved waiver. Three",
        "consequences follow, and they are the whole point of the control:",
        "",
        "1. **Evidence that failed does not satisfy a criterion.** A test suite",
        "   that ran and went red is evidence against the gate. The most recent",
        "   evidence is the one that counts, so a re-run that fails takes the",
        "   satisfaction away again.",
        "2. **A blocked gate refuses.** `advance()` raises `GateBlocked` and the",
        "   HTTP surface answers 409 with the unmet criteria. It does not return",
        "   a warning, because a gate a caller may ignore is a report.",
        "3. **A waiver is not a pass.** Skipping a criterion requires a written",
        "   reason and a named approver, and the decision is recorded as",
        "   `waived`. The register can always distinguish work that was done",
        "   from work that was excused.",
        "",
        "Criteria are declared per deliverable kind. An image faces no build",
        "gate and a module faces no accessibility audit, because a checklist a",
        "deliverable can only half-satisfy trains everyone to waive the half",
        "that never applied.",
        "",
        "## Stages",
        "",
    ]

    for stage in STAGE_ORDER:
        out.append(f"### {stage.value.title()}")
        out.append("")
        out.append(_STAGE_PURPOSE[stage])
        out.append("")
        stage_criteria = [c for c in CRITERIA if c.stage is stage]
        if not stage_criteria:
            out.append("No gate leaves this stage.")
            out.append("")
            continue
        out.append("| Criterion | Evidence | Supplied by | Applies to | Mandatory |")
        out.append("|---|---|---|---|---|")
        for crit in stage_criteria:
            applies = (
                "every kind"
                if len(crit.applies_to) == len(DeliverableKind)
                else ", ".join(k.value for k in crit.applies_to)
            )
            out.append(
                f"| `{crit.id}` | {crit.evidence_kind.value} | {crit.supplied_by} "
                f"| {applies} | {'yes' if crit.mandatory else 'no'} |"
            )
        out.append("")
        for crit in stage_criteria:
            out.append(f"- **`{crit.id}`** — {crit.description}")
        out.append("")

    out.append("## Criteria by deliverable kind")
    out.append("")
    out.extend(_matrix())
    out.append("")

    out.append("## Procedure")
    out.append("")
    out.append("All paths are relative to the platform API.")
    out.append("")
    out.append("1. **Commission.** `POST /creative/commission` with the request in")
    out.append("   words. The creative route table names the Location and the")
    out.append("   deliverable kind, and the Town Hall record opens at *concept*.")
    out.append("   An unroutable request opens nothing — a deliverable naming no")
    out.append("   Location would stall forever at a gate nobody can evidence.")
    out.append("2. **Read the gate.** `GET /townhall/plm/deliverables/{id}/gate`")
    out.append("   lists what this deliverable still needs, and who supplies it.")
    out.append("3. **File evidence.** `POST /townhall/plm/deliverables/{id}/evidence`")
    out.append("   with the criterion id, a reference, and the outcome. File the")
    out.append("   failures too: an unrecorded failure is how a red result gets")
    out.append("   forgotten and re-run until it is green once.")
    out.append("4. **Waive, if you must.** `POST /townhall/plm/deliverables/{id}/waivers`")
    out.append("   with a reason and an approver. Both are required.")
    out.append("5. **Advance.** `POST /townhall/plm/deliverables/{id}/advance`. A 409")
    out.append("   carries the unmet criteria in its body; a 200 moves the record")
    out.append("   to the next stage and writes the gate decision.")
    out.append("6. **Audit.** `GET /townhall/plm/deliverables/{id}/history` returns")
    out.append("   every gate decision oldest first, including which criteria were")
    out.append("   waived and by whom.")
    out.append("")

    out.append("## Worked example — a game")
    out.append("")
    kind = DeliverableKind.GAME
    for stage in STAGE_ORDER:
        applicable = criteria_for(kind, stage)
        if not applicable:
            continue
        required = [c.id for c in applicable if c.mandatory]
        out.append(f"- Leaving **{stage.value}** needs: " + ", ".join(f"`{c}`" for c in required))
    out.append("")
    out.append(
        "Read that as boundaries, not as a checklist: each line is what the "
        "deliverable needs to *leave* that stage. So a game cannot reach the "
        "release stage at all without a business case, initiation approval, "
        "Fabulousa's design review and accessibility audit, an Artifactory "
        "build and Cryptex's scan, and The Chaos Party's test run — and it "
        "cannot leave release without The Library holding its documentation "
        "and The Town Hall approving the release itself."
    )
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the committed document does not match the criteria.",
    )
    args = parser.parse_args(argv)

    rendered = render()
    if args.check:
        if not OUTPUT.exists():
            print(f"MISSING: {OUTPUT.relative_to(REPO)} has never been generated.")
            print("Run: python scripts/generate_plm_docs.py")
            return 1
        if OUTPUT.read_text() != rendered:
            print(f"DRIFT: {OUTPUT.relative_to(REPO)} no longer matches src/townhall/plm.py.")
            print("Run: python scripts/generate_plm_docs.py")
            return 1
        print(f"PLM docs: PASSED — {OUTPUT.relative_to(REPO)} matches the gate criteria")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered)
    print(f"Wrote {OUTPUT.relative_to(REPO)} ({len(CRITERIA)} criteria)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
