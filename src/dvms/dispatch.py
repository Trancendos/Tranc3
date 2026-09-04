"""Turn a census into the prioritised Requests and Changes The Lab acts on.

WHY THIS EXISTS

The intended flow is Cryptex assesses -> hands The Lab a priority order of
Requests and/or Changes -> The Lab remediates -> The Observatory records ->
The Basement learns. Every piece of that existed already and none of it was
connected: the census produced findings keyed by manifest path, and
`src/townhall/itsm.py` produced Incidents and Changes keyed by a service string
it resolves to a Location. Nothing turned one into the other, so the assessment
stopped at a report and the remediation queue stayed empty.

`surface_owner.py` supplies the missing key. This module supplies the verb.

WHY A CHANGE FOR ONE AND AN INCIDENT FOR THE OTHER

They are different questions and ITIL separates them for a reason:

  fixable -- a patched release exists and is reachable. There is a known,
             planned action, and that is a CHANGE.
  blocked -- a patch exists but an upstream exact-pin puts it out of reach.
             Nobody can act on it today; it needs a decision, and something
             being wrong with no available action is an INCIDENT.
  errored -- the surface could not be scanned at all. Exposure is unknown,
             which is worse than known-and-blocked, so it is an INCIDENT and
             it outranks everything else.
  accepted -- no fix exists AND the risk is dispositioned in the register.
             Raising anything would be noise against a decision already taken.

PRIORITY

Highest first, because a queue that is not ordered is a list:

  P1  a surface that could not be scanned -- unknown exposure
  P2  fixable findings on a Location that owns the surface outright
  P3  fixable findings on a cross-cutting surface, and blocked findings
  P4  everything else that still warrants a record

Volume breaks ties within a band: a Location with eleven fixable findings is
ahead of one with two. This is deliberately simple and deliberately visible --
a scoring formula nobody can reproduce by hand is one nobody trusts, and an
untrusted queue gets worked in whatever order somebody prefers.

PLANNING IS SEPARATE FROM APPLYING

`plan()` is pure: a census in, a prioritised list out, no database and no side
effects, so the ordering can be tested without standing anything up. `apply()`
is the thin part that writes the records. That split is not tidiness -- the
ordering is the part with judgement in it, and judgement that cannot be tested
does not stay correct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.dvms.surface_owner import resolve_surface

# The ITSM record kinds this module raises.
KIND_CHANGE = "change"
KIND_INCIDENT = "incident"

# Priority bands, highest first. Strings rather than an enum so a plan can be
# serialised to JSON and read by something that is not this process.
P1, P2, P3, P4 = "p1", "p2", "p3", "p4"


@dataclass
class DispatchItem:
    """One record to raise, against one Location, for one reason."""

    kind: str
    priority: str
    location: Optional[str]
    responsible: Optional[str]
    surface: str
    title: str
    detail: str
    findings: List[Dict[str, Any]] = field(default_factory=list)
    owner_kind: str = ""

    @property
    def is_routable(self) -> bool:
        """False when nothing on the platform can receive this record.

        An unrouted item is still returned by `plan()` rather than dropped:
        the whole failure mode this work exists to close is exposure that
        vanishes because nobody owned it.
        """
        return bool(self.responsible)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "priority": self.priority,
            "location": self.location,
            "responsible": self.responsible,
            "surface": self.surface,
            "title": self.title,
            "detail": self.detail,
            "owner_kind": self.owner_kind,
            "finding_ids": [f.get("id") for f in self.findings],
        }


_ORDER = {P1: 0, P2: 1, P3: 2, P4: 3}


def _describe(findings: List[Dict[str, Any]], limit: int = 6) -> str:
    """`package id`, a few of them, then a count. Readable in a ticket title."""
    shown = [f"{f.get('package') or '?'} ({f.get('id')})" for f in findings[:limit]]
    if len(findings) > limit:
        shown.append(f"and {len(findings) - limit} more")
    return ", ".join(shown)


def _owner_of(surface: Dict[str, Any]):
    """The surface's owner, from the census record or resolved on demand.

    A census built before owners were attached still dispatches correctly --
    the resolver is the same one either way, so this is a fallback, not a
    second source of truth.
    """
    embedded = surface.get("owner")
    if isinstance(embedded, dict) and embedded.get("kind") in {"location", "shared", "unmapped"}:
        return (
            embedded.get("kind"),
            embedded.get("location"),
            embedded.get("responsible"),
        )
    owner = resolve_surface(surface.get("surface", ""))
    return owner.kind, owner.location, owner.responsible


def plan(census: Dict[str, Any]) -> List[DispatchItem]:
    """The prioritised Requests and Changes a census implies. No side effects."""
    items: List[DispatchItem] = []

    for surface in census.get("surfaces", []):
        path = surface.get("surface", "")
        owner_kind, location, responsible = _owner_of(surface)

        if surface.get("errored"):
            items.append(
                DispatchItem(
                    kind=KIND_INCIDENT,
                    priority=P1,
                    location=location,
                    responsible=responsible,
                    surface=path,
                    owner_kind=owner_kind,
                    title=f"Dependency surface {path} could not be scanned",
                    detail=(
                        f"{surface.get('reason') or 'no reason recorded'} — exposure here "
                        "is unknown, which ranks above every known finding: a surface "
                        "that cannot be read is not a surface that is clean."
                    ),
                )
            )
            continue

        findings = surface.get("findings", []) or []
        fixable = [f for f in findings if f.get("classification") == "fixable"]
        blocked = [f for f in findings if f.get("classification") == "blocked"]

        if fixable:
            items.append(
                DispatchItem(
                    kind=KIND_CHANGE,
                    priority=P2 if owner_kind == "location" else P3,
                    location=location,
                    responsible=responsible,
                    surface=path,
                    owner_kind=owner_kind,
                    findings=fixable,
                    title=(
                        f"Upgrade {len(fixable)} vulnerable "
                        f"{'dependency' if len(fixable) == 1 else 'dependencies'} in {path}"
                    ),
                    detail=(
                        f"A patched release exists and is reachable for: {_describe(fixable)}. "
                        "Raised as a Change because the action is known and planned."
                    ),
                )
            )

        if blocked:
            items.append(
                DispatchItem(
                    kind=KIND_INCIDENT,
                    priority=P3,
                    location=location,
                    responsible=responsible,
                    surface=path,
                    owner_kind=owner_kind,
                    findings=blocked,
                    title=f"{len(blocked)} blocked vulnerability fix in {path}",
                    detail=(
                        f"A patch exists but is out of reach for: {_describe(blocked)}. "
                        "Raised as an Incident rather than a Change because there is no "
                        "action available today — it needs a decision, not a deployment."
                    ),
                )
            )

    # Highest band first; within a band the biggest pile of findings first, so
    # the queue reads top-down as the order somebody should actually work it.
    # Surface breaks the final tie, so two runs over an unchanged census
    # produce the same plan -- a queue that reshuffles itself is one nobody can
    # tell has changed.
    items.sort(key=lambda i: (_ORDER.get(i.priority, 9), -len(i.findings), i.surface))
    return items


def summarise(items: List[DispatchItem]) -> Dict[str, Any]:
    """Counts a human reads before deciding whether to apply the plan."""
    by_priority: Dict[str, int] = {}
    by_location: Dict[str, int] = {}
    for item in items:
        by_priority[item.priority] = by_priority.get(item.priority, 0) + 1
        who = item.responsible or "unrouted"
        by_location[who] = by_location.get(who, 0) + 1
    return {
        "total": len(items),
        "changes": sum(1 for i in items if i.kind == KIND_CHANGE),
        "incidents": sum(1 for i in items if i.kind == KIND_INCIDENT),
        "unroutable": sum(1 for i in items if not i.is_routable),
        "by_priority": dict(sorted(by_priority.items())),
        "by_location": dict(sorted(by_location.items())),
    }


def apply(items: List[DispatchItem], service=None) -> List[Dict[str, Any]]:
    """Write the plan into The Town Hall's ITSM store.

    An unroutable item is SKIPPED rather than filed against a placeholder.
    `resolve_ownership` already refuses to guess an owner for the same reason —
    an incident with a plausible-looking owner routes the page to somebody who
    is not on the hook, and then everybody believes it is handled.
    """
    from src.townhall.itsm import IncidentPriority, get_itsm_service

    itsm = service or get_itsm_service()
    written: List[Dict[str, Any]] = []
    for item in items:
        if not item.is_routable:
            written.append({"skipped": item.surface, "reason": "no Location answers for it"})
            continue
        if item.kind == KIND_CHANGE:
            record = itsm.create_change(item.title, change_type="normal", service=item.responsible)
        else:
            record = itsm.create_incident(
                item.title,
                item.detail,
                priority=IncidentPriority(item.priority),
                service=item.responsible,
            )
        written.append(record.to_dict())
    return written
