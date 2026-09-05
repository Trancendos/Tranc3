#!/usr/bin/env python3
"""Collate every outstanding action the documentation records into one backlog.

The problem
-----------
The estate records its outstanding work in 44 separate registers — an ISO
27001 statement of applicability, a DefStan compliance register, a creative
forensic assessment, a flow contract, a pen-test programme, and forty others.
Each is correct about its own domain and blind to the rest. Nobody can answer
"what is outstanding across the platform" without reading 320 documents, so
in practice nobody asks, and an action recorded in a register nobody sweeps
is an action nobody does.

What this produces
------------------
`docs/governance/ACTION-BACKLOG.md` — every open row, harvested from the
registers themselves, grouped into Epics, sized, and routed to the Location
that owns it. Regenerated rather than maintained: a hand-kept backlog is a
45th register.

How an item is sized
--------------------
Story points are DERIVED and the reasons are printed beside them, for the
same reason the solution packs derive readiness: a number nobody can
interrogate is a number nobody trusts. The scale is Fibonacci, and the
inputs are facts about the item, not impressions:

  +1  baseline — every item costs something
  +1  the owning Location has no code path on disk (nothing to change yet)
  +2  the status is blocked, funding-gated, or needs an owner (not just work)
  +2  the register is a compliance or audit register (evidence, not code)
  +1  the row names no Location this estate knows (routing has to happen first)

Sized 1, 2, 3, 5, 8 by the nearest Fibonacci below the total, so a 13 means
something genuinely unusual rather than a rounding artefact.

Definition of Ready and Definition of Done are stated once, at the top, and
apply to every item — they are properties of this estate's gates
(`src/townhall/plm.py`), not per-item prose.

Usage:
    python3 scripts/build_action_backlog.py [--check]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUTPUT = REPO / "docs" / "governance" / "ACTION-BACKLOG.md"

_SKIP = ("compliance/magna-carta", "workers/cranbania", "node_modules")

#: A status cell that means "not finished". Matched against a whole cell, so
#: a sentence merely containing the word "open" is not harvested.
_OPEN_STATUS = re.compile(
    r"(Open|Needs owner|Blocked|Funding[- ]gated|Pending|Planned|Not started|"
    r"In progress|Partial)",
    re.IGNORECASE,
)

#: Statuses that mean the work cannot simply be picked up.
_IMPEDED = ("blocked", "funding", "needs owner")

#: Registers whose items are evidence and attestation rather than code.
_EVIDENCE_REGISTERS = ("compliance/", "defstan/", "evidence/", "audit", "iso", "soc2")

#: Epic grouping, by the register a row came from. Ordered: first match wins.
_EPICS: tuple[tuple[str, str, str], ...] = (
    (
        "compliance/ISO27001",
        "ISO 27001 controls",
        "Statement-of-applicability controls not yet evidenced.",
    ),
    (
        "defstan/",
        "DefStan alignment",
        "UK Defence Standard clauses awaiting evidence or exemption.",
    ),
    ("compliance/SOC2", "SOC 2 evidence", "Trust-services criteria awaiting an evidence artefact."),
    ("compliance/", "Regulatory alignment", "FCA, AI governance and other regulatory registers."),
    ("evidence/", "Assurance programmes", "Penetration testing and independent assurance."),
    ("governance/INTERNAL-AUDIT", "Internal audit", "Audit programme findings and follow-ups."),
    (
        "FORENSIC-ASSESSMENT-CREATIVE",
        "Creative delivery",
        "The creative routing and PLM remediation register.",
    ),
    (
        "LOCATION-FLOW-CONTRACT",
        "Location flow wiring",
        "Declared Location-to-Location flows that nothing routes to.",
    ),
    (
        "wiki-content/Historical",
        "Historical findings",
        "Items carried from earlier assessments — verify before working.",
    ),
    ("", "Platform engineering", "Everything else the estate has recorded as outstanding."),
)

_FIBONACCI = (1, 2, 3, 5, 8, 13)

#: Where a Location's solution pack lives, relative to this document.
_PACKS = REPO / "docs" / "solution-packs"


def _pack_slug(location: str) -> str:
    """A Location name as its solution-pack filename."""
    return re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")


def _design_link(location: str | None) -> str:
    """The Location's solution pack — its storyboard, blueprint and wireframes.

    Every routed item already had design material: 43 packs, one per Location,
    each carrying the architecture, the Traefik routing derived from compose,
    the user journey and the acceptance criteria. Nothing said so. A backlog
    that names the work and not where its design lives sends the reader to
    guess at a directory, and the packs go unread — which is the same failure
    as the 44 registers this document exists to sweep, one level over.

    An unrouted item genuinely has no pack: routing it to a Location is the
    first story, and that is already what its sizing says.
    """
    if not location:
        return "—"
    pack = _PACKS / f"{_pack_slug(location)}.md"
    if not pack.is_file():
        # Said plainly rather than linked into the void. A dead link in a
        # generated document is worse than an admission.
        return "_no pack_"
    return f"[pack](../solution-packs/{pack.name})"


def _documents() -> list[Path]:
    """Every register this sweep reads — never its own output.

    The backlog is a markdown document full of tables, so it reads as a
    register like any other and every generation re-ingested the previous
    one: 163 items became 326, then 489, compounding by the same 163 each
    run. `--check` could therefore never pass, because regenerating produced
    a different file than the one just written. A generated document is not
    evidence of outstanding work; it is a restatement of it.

    -z and a NUL split, not whitespace: a path containing a space would
    otherwise become two names that resolve to nothing, silently dropping a
    register from the sweep.
    """
    listed = [
        entry
        for entry in subprocess.run(
            ["git", "ls-files", "-z", "*.md"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split("\0")
        if entry
    ]
    generated = OUTPUT.relative_to(REPO).as_posix()
    return [
        REPO / p
        for p in listed
        if p != generated and not any(skip in p for skip in _SKIP) and (REPO / p).is_file()
    ]


def _locations() -> dict[str, str]:
    """Location name -> worker path, from the canonical entity register."""
    from src.entities.platform import PLATFORM_ENTITIES  # noqa: PLC0415

    return {name: getattr(e, "worker_path", "") for name, e in PLATFORM_ENTITIES.items()}


#: Header names that hold the action itself, best first. Registers vary —
#: "Action", "Item", "Control", "Requirement", "Clause", "Finding" — and the
#: column that holds the work is not the widest one. Taking the longest cell
#: reported a register's *notes* as its action ("Fabulousa is reachable but
#: unauthenticated" instead of "Issue PENPOT_TOKEN into The Void"), which is
#: a backlog that says the wrong thing about work it correctly found.
_ACTION_HEADERS = (
    "action",
    "remediation",
    "item",
    "task",
    "story",
    "requirement",
    "control",
    "clause",
    "finding",
    "gap",
    "description",
    "claim",
)

#: Header names that never hold the action.
_NOT_ACTION_HEADERS = ("status", "state", "owner", "due", "date", "priority", "severity", "#", "id")


_WRAPPERS = ("**", "__", "`", "*", "_")


def _unwrap(text: str) -> str:
    """Strip whole-value markdown wrapping, and only when it is matched.

    `str.strip("* `")` removes any of those characters from either end
    independently, so an action that merely *begins* with inline code —
    "`PENPOT_TOKEN` into The Void" — lost its opening backtick and kept its
    closing one, and the backlog rendered a row with unbalanced markup. Only
    a wrapper present at both ends is removed, and only whole pairs.
    """
    value = text.strip()
    changed = True
    while changed:
        changed = False
        for wrapper in _WRAPPERS:
            if (
                len(value) > 2 * len(wrapper)
                and value.startswith(wrapper)
                and value.endswith(wrapper)
                # A value wrapped end to end, not two separate spans: the
                # marker must not reappear in between, or "`a` and `b`" would
                # be read as one span and lose both delimiters.
                and wrapper not in value[len(wrapper) : -len(wrapper)]
            ):
                value = value[len(wrapper) : -len(wrapper)].strip()
                if wrapper == "`":
                    # Stop at a code span. Its contents are code, and
                    # continuing to unwrap read the underscores in
                    # `__init__` as emphasis and returned `init` — a
                    # corruption of the very thing the span exists to
                    # protect from markdown.
                    return value
                changed = True
    return value


def _action_column(header: list[str]) -> int | None:
    """The index of the column holding the action, from the table's own header."""
    lowered = [h.strip("* `").lower() for h in header]
    for wanted in _ACTION_HEADERS:
        for index, name in enumerate(lowered):
            if wanted in name and not any(bad == name for bad in _NOT_ACTION_HEADERS):
                return index
    return None


#: An unchecked markdown task: `- [ ] do the thing`.
_UNCHECKED = re.compile(r"^\s*[-*]\s*\[ \]\s+(.+?)\s*$")

#: Documents whose `- [ ]` items are NOT outstanding work.
#:
#: The distinction is a property of the document's role, not of the item's
#: wording, so it is drawn by path and stated rather than guessed per line:
#:
#:   * `config/townhall/templates/` — blanks to fill in when instantiating a
#:     template. `- [ ] Authentication via Infinity` there is a prompt, not a
#:     task somebody has failed to do.
#:   * `docs/runbooks/` and `*RUNBOOK*` — steps performed *during* an
#:     incident or a drill. `- [ ] PRAGMA integrity_check returns ok` is a
#:     verification to run then, not work outstanding now.
#:   * The CAB approval workflow and change-request process — process forms
#:     whose items are literally "Step 1:", "Step 2:", "Verification:".
#:
#: Sweeping these would put ~50 procedure steps into the backlog as though
#: they were unbuilt features, which is worse than missing them: it buries the
#: real ones and makes the total meaningless.
_PROCEDURE_DOCUMENTS = (
    "config/townhall/templates/",
    "docs/runbooks/",
    "runbook",
    "docs/cab/approval_workflow",
    "docs/change-request-process",
)


def _is_procedure(rel: str) -> bool:
    """Are this document's checkboxes steps to follow rather than work to do?"""
    lowered = rel.lower()
    return any(marker in lowered for marker in _PROCEDURE_DOCUMENTS)


def _checkbox_items(rel: str, text: str, locations: dict[str, str]) -> list[dict]:
    """Unchecked task-list items in one document.

    The sweep read markdown TABLES only, and 81 unchecked `- [ ]` items across
    13 documents therefore reached no register at all — including all three
    `wiki-content/Todo-*` lists, which exist for no other purpose. A backlog
    claiming "every outstanding item the estate records" that cannot see the
    single most common way of recording one was overstating its coverage.

    A checkbox carries no status column, so its status is the checkbox: it is
    unchecked, therefore open. `Open` is recorded rather than inferring
    something richer that the source does not say.
    """
    if _is_procedure(rel):
        return []
    found: list[dict] = []
    for number, line in enumerate(text.splitlines(), 1):
        match = _UNCHECKED.match(line)
        if not match:
            continue
        action = _unwrap(match.group(1))
        if len(action) < 12:
            # Too short to be an action anybody could act on — "Step 2:",
            # "TBD", a stray bullet. The same floor the table sweep uses.
            continue
        named = [name for name in locations if name.lower() in action.lower()]
        found.append(
            {
                "source": rel,
                "line": number,
                "action": action,
                "status": "Open",
                "location": named[0] if named else "",
            }
        )
    return found


def _apply_routing(items: list[dict]) -> list[dict]:
    """Overlay the Town Hall's routing decisions onto the swept items.

    A Location named inside a register row is a hint the register's author
    left; a Town Hall decision is a governed answer with an authority, a
    written reason and an Observatory record. Where both exist the decision
    wins, because the point of routing through the Town Hall is that the
    decision is appealable and a mention in prose is not.

    Reading a file rather than the registry's database is deliberate: this
    runs in CI on a fresh checkout with no service. The export is what makes
    a routing decision visible in a diff.
    """
    try:
        from src.townhall.routing import load_decisions  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        # Only the case this fallback is for: `src/` is not on the path at
        # all. Catching every exception meant a broken import — a missing
        # dependency, a syntax error, a regression in the registry — read as
        # "no decisions recorded" and produced a backlog that looked valid
        # and was entirely unrouted. A control that fails quietly into the
        # answer you would have got anyway is the defect this file's own
        # subject matter is about.
        if (exc.name or "").split(".")[0] != "src":
            raise
        return items
    decisions = load_decisions()
    for item in items:
        decision = decisions.get(f"{item['source']}:{item['line']}")
        if decision:
            item["location"] = decision["location"]
            item["routed_by"] = decision["authority"]
            item["routing_reason"] = decision["reason"]
    return items


def harvest() -> list[dict]:
    """Every open register row in the documentation estate.

    Two shapes are swept: rows in a markdown table carrying an open status,
    and unchecked task-list items. Tables were the only shape until
    2026-09-05; see `_checkbox_items` for what that missed.
    """
    locations = _locations()
    items: list[dict] = []

    for document in _documents():
        rel = document.relative_to(REPO).as_posix()
        items.extend(
            _checkbox_items(rel, document.read_text(encoding="utf-8", errors="replace"), locations)
        )
        header: list[str] = []
        action_index: int | None = None
        for number, line in enumerate(
            document.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            stripped = line.strip()
            if not stripped.startswith("|"):
                header, action_index = [], None
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                # The separator row: the line above it was the header.
                action_index = _action_column(header) if header else None
                continue
            if not header:
                header = cells
                continue
            if len(cells) < 3:
                continue
            status = next((c for c in cells if _OPEN_STATUS.fullmatch(c.strip("* `"))), None)
            if status is None:
                continue

            action = ""
            if action_index is not None and action_index < len(cells):
                candidate = _unwrap(cells[action_index])
                if candidate and candidate is not status:
                    action = candidate
            if len(action) < 12:
                # No usable header column: fall back to the longest non-status
                # cell, which is right for the registers that have no header
                # naming their action column.
                body = [c for c in cells if c is not status and c.strip("* `")]
                action = _unwrap(max(body, key=len)) if body else ""
            if len(action) < 12:
                continue

            named = [name for name in locations if name.lower() in line.lower()]
            items.append(
                {
                    "source": rel,
                    "line": number,
                    "action": action,
                    "status": status.strip("* `"),
                    "location": named[0] if named else "",
                }
            )
    return _apply_routing(items)


def size(item: dict, locations: dict[str, str]) -> tuple[int, list[str]]:
    """Story points, and every reason that contributed to them."""
    points, why = 1, ["baseline (+1)"]

    location = item["location"]
    if not location:
        points += 1
        why.append("no Location named — routing first (+1)")
    elif not (REPO / locations[location]).exists() if locations.get(location) else False:
        points += 1
        why.append("owning Location has no code path on disk (+1)")

    if any(flag in item["status"].lower() for flag in _IMPEDED):
        points += 2
        why.append(f"status `{item['status']}` — impeded, not merely unstarted (+2)")

    if any(marker in item["source"].lower() for marker in _EVIDENCE_REGISTERS):
        points += 2
        why.append("evidence/attestation register, not a code change (+2)")

    nearest = max(f for f in _FIBONACCI if f <= points) if points >= 1 else 1
    return nearest, why


def epic_for(source: str) -> tuple[str, str]:
    """The epic a register belongs to, as `(title, blurb)`.

    Matched on the source path so a new register lands in an existing epic
    without anyone editing this file; an unmatched one falls to the catch-all
    rather than being dropped.
    """
    for marker, title, blurb in _EPICS:
        if marker and marker in source:
            return title, blurb
    return _EPICS[-1][1], _EPICS[-1][2]


def render(items: list[dict]) -> str:
    """The whole backlog document, as text.

    A pure function of `items` — no filesystem reads, no clock — which is what
    lets `--check` compare a fresh render against the committed copy and lets
    the idempotence test assert two renders are identical.
    """
    locations = _locations()
    grouped: dict[str, list[dict]] = defaultdict(list)
    blurbs: dict[str, str] = {}
    for item in items:
        title, blurb = epic_for(item["source"])
        grouped[title].append(item)
        blurbs[title] = blurb

    out: list[str] = []
    add = out.append

    add("# Action Backlog — every outstanding item the estate records")
    add("")
    add(
        f"**Generated** by `scripts/build_action_backlog.py` from "
        f"{len({i['source'] for i in items})} registers across the documentation estate. "
        "Do not edit by hand — a hand-kept backlog becomes one more register nobody sweeps."
    )
    add("")
    add(
        "The estate records outstanding work in dozens of separate registers, each "
        "correct about its own domain and blind to the rest. Nobody can answer *what "
        "is outstanding across the platform* without reading 320 documents, so nobody "
        "asks — and an action in a register nobody sweeps is an action nobody does. "
        "This is that sweep."
    )
    add("")
    add(f"**{len(items)} open items** across **{len(grouped)} epics**.")
    add("")
    routed = sum(1 for item in items if item["location"])
    decided = sum(1 for item in items if item.get("routed_by"))
    add(
        f"**{routed} of {len(items)} are routed to a Location** and link to that "
        f"Location's solution pack — its architecture, compose-derived routing, user "
        f"journey and acceptance criteria. The other {len(items) - routed} name no "
        f"Location, so they have no design material and no one accountable; routing "
        f"them is the first story in each case, which is what the +1 in their sizing "
        f"says. That ratio is the single most useful number in this document."
    )
    add("")
    add(
        f"**{decided} of those {routed} carry a Town Hall routing decision** "
        "(`/townhall/routing`, exported to `config/estate/backlog_routing.yaml`): a "
        "named authority, a written reason, the Location's design pack and an "
        "Observatory event. The rest are routed only because a register row happens "
        "to mention a Location by name, which is a hint its author left rather than "
        "a decision anybody made or can appeal."
    )
    add("")
    add(
        f"The remaining **{len(items) - routed} are a queue the Town Hall owes an "
        "answer to**, not a number to be made to go away. Assigning them here by "
        "judgement would write a decision nobody made into a generated file that "
        "reads as derived fact — the same move that made a routing defect read as "
        "deliberate design in twenty solution packs."
    )
    add("")

    add("## Definition of Ready")
    add("")
    add("An item is ready to start when all of these hold. They are properties of this")
    add("estate's own gates (`src/townhall/plm.py`), not per-item prose.")
    add("")
    add("| # | Condition | Why it is here |")
    add("|---|---|---|")
    add(
        "| 1 | The owning Location is named, and its code path exists | An item routed "
        "nowhere is an item nobody is accountable for — the defect the CMDB alignment "
        "check now prevents |"
    )
    add(
        "| 2 | The register row it came from is still open | Registers are swept by "
        "regenerating this file; an item closed at source disappears from it |"
    )
    add(
        '| 3 | Acceptance is stated as something observable | "Improve X" cannot be '
        'gated; "`GET /x` answers 200 in the deployed image" can |'
    )
    add(
        "| 4 | Any dependency is itself Ready or Done | PLM refuses a gate whose "
        "evidence depends on unfinished work |"
    )
    add("")

    add("## Definition of Done")
    add("")
    add("| # | Condition | Enforced by |")
    add("|---|---|---|")
    add(
        "| 1 | The change is in the deployed entrypoint, not only in the repository | "
        "`scripts/check_creative_routes.py` — several workers ship two apps and only "
        "the Dockerfile `CMD` decides which runs |"
    )
    add(
        "| 2 | A test exists that fails when the change is reverted | Mutation, by "
        "hand: inject the fault, watch the named test fail, restore |"
    )
    add(
        "| 3 | Any control added is invoked by something | "
        "`scripts/check_guards_are_wired.py` — a control nobody runs reports PASSED "
        "and gates nothing |"
    )
    add(
        "| 4 | The source register row is closed, and this file regenerated | Otherwise "
        "the backlog and the register disagree, which is the condition this file exists "
        "to end |"
    )
    add(
        "| 5 | A PLM gate decision is recorded | `/townhall/plm` — the Town Hall, not "
        "the building Location, decides the gate opened |"
    )
    add("")

    add("## Sizing")
    add("")
    add("Story points are derived from facts about the item, never estimated. Each")
    add("item's reasons are printed beside it, so a number can be argued with.")
    add("")
    add("| Contribution | Points |")
    add("|---|---|")
    add("| Baseline — every item costs something | +1 |")
    add("| No Location named; routing has to happen first | +1 |")
    add("| Owning Location has no code path on disk | +1 |")
    add("| Status is blocked, funding-gated, or needs an owner | +2 |")
    add("| Evidence or attestation register rather than a code change | +2 |")
    add("")
    add("Totals are rounded down to the nearest Fibonacci value, so a 13 means")
    add("something genuinely unusual rather than a rounding artefact.")
    add("")

    total_points = 0
    for title in [t for _, t, _ in _EPICS if t in grouped]:
        rows = grouped[title]
        sized = [(item, *size(item, locations)) for item in rows]
        epic_points = sum(points for _, points, _ in sized)
        total_points += epic_points
        add(f"## Epic — {title}")
        add("")
        add(f"{blurbs[title]}")
        add("")
        add(f"**{len(rows)} stories · {epic_points} points**")
        add("")
        add("| Story | Location | Design | Status | Pts | Sized because | Source |")
        add("|---|---|---|---|---|---|---|")
        for item, points, why in sized:
            action = item["action"].replace("|", "\\|")
            if len(action) > 110:
                action = action[:107] + "…"
            add(
                f"| {action} | {item['location'] or '_unrouted_'} | {_design_link(item['location'])} "
                f"| {item['status']} | {points} | {'; '.join(why)} "
                f"| `{item['source']}:{item['line']}` |"
            )
        add("")

    add("---")
    add("")
    add(f"**Total: {len(items)} stories, {total_points} points.**")
    add("")
    add(
        "Velocity is not asserted here. This estate has no measured throughput to "
        "divide by, and a sprint count derived from an invented velocity would be the "
        "kind of confident, unfounded number the rest of these documents exist to "
        "avoid."
    )
    return "\n".join(line.rstrip() for line in out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the backlog, or verify the committed copy. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed copy is stale")
    args = parser.parse_args(argv)

    rendered = render(harvest())

    if args.check:
        if not OUTPUT.exists():
            print(f"Action backlog: FAILED — {OUTPUT.relative_to(REPO)} is missing")
            return 1
        if OUTPUT.read_text(encoding="utf-8") != rendered:
            print("Action backlog: FAILED — the committed copy is stale")
            print("Run: python3 scripts/build_action_backlog.py")
            return 1
        print("Action backlog: PASSED — the committed copy matches the registers")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
