"""What the estate can actually sell, and which seat owns selling it.

The Arcadian Exchange's external mandate needs an inventory before it needs
a price. This module is that inventory: for every Location that produces
something a counterparty outside Trancendos could pay for, it names the
resource, the external seat responsible, the revenue stream it books into,
and the constraint class the eligibility gate has to apply.

Two deliberate properties:

**Every source names a real Location.** The catalogue is validated against
`PLATFORM_ENTITIES` at import, so a renamed or removed Location fails loudly
here rather than producing an opportunity book that quietly references a
service the platform no longer has.

**Every source names a real revenue stream.** `PassiveRevenueEngine` already
books realised income across twelve streams. This module is the missing front
half -- what *could* be sold and for how much -- so it maps onto those streams
rather than inventing a parallel ledger that would then have to be reconciled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple


class Constraint(str, Enum):
    """Why an opportunity might not be free to pursue.

    The gate in `governance.py` turns these into decisions. They are declared
    on the source rather than inferred at valuation time, because whether a
    resource is sellable is a property of the resource, not of how attractive
    a particular deal looks.
    """

    #: Nothing beyond ordinary commercial terms.
    NONE = "none"
    #: Contains or derives from identifiable user data. Sellable only in
    #: aggregate, non-identifying form, and never without consent.
    PERSONAL_DATA = "personal_data"
    #: The platform holds it under a licence that forbids redistribution --
    #: third-party analyst research, vendor documentation, purchased datasets.
    LICENSED_IN = "licensed_in"
    #: Selling or acting on it is a regulated activity (financial advice,
    #: trade execution, security testing of third-party systems).
    REGULATED = "regulated"
    #: Derived from a customer's own environment or engagement. Belongs to
    #: them; resale needs their explicit agreement.
    CLIENT_DERIVED = "client_derived"


@dataclass(frozen=True)
class SellableResource:
    """One thing a Location produces that someone outside might pay for."""

    resource_id: str
    #: Canonical Location name -- validated against PLATFORM_ENTITIES.
    location: str
    description: str
    #: `seat_id` of the external Arcadian Exchange seat that owns selling it.
    owning_seat: str
    #: Key in PassiveRevenueEngine.STREAMS that realised income books into.
    revenue_stream: str
    #: What one unit is, for anyone reading a valuation later.
    unit: str
    constraint: Constraint = Constraint.NONE
    #: Written where the constraint is anything but NONE, so the reason
    #: travels with the resource instead of living in a separate policy doc.
    constraint_note: str = ""


SELLABLE_RESOURCES: Tuple[SellableResource, ...] = (
    # ── Ann Porter: capacity and finished assets ────────────────────────────
    SellableResource(
        resource_id="storage-surplus",
        location="DocUtari",
        description="Storage and IPFS capacity held above the estate's own need",
        owning_seat="ann-porter-external",
        revenue_stream="marketplace_fees",
        unit="GiB-month",
    ),
    SellableResource(
        resource_id="generated-imagery",
        location="Sashas Photo Studio",
        description="Rendered images the studio produced and the estate holds rights to",
        owning_seat="ann-porter-external",
        revenue_stream="marketplace_fees",
        unit="licensed image",
    ),
    SellableResource(
        resource_id="video-assets",
        location="TateKing",
        description="Finished video segments and edits available for licensing",
        owning_seat="ann-porter-external",
        revenue_stream="marketplace_fees",
        unit="licensed clip",
    ),
    SellableResource(
        resource_id="three-d-assets",
        location="TranceFlow",
        description="3D models and game-ready assets built in-house",
        owning_seat="ann-porter-external",
        revenue_stream="marketplace_fees",
        unit="licensed model",
    ),
    SellableResource(
        resource_id="audio-assets",
        location="Warp Radio",
        description="Original audio beds and stings produced for the estate",
        owning_seat="ann-porter-external",
        revenue_stream="marketplace_fees",
        unit="licensed track",
    ),
    SellableResource(
        resource_id="design-systems",
        location="Fabulousa",
        description="Design systems, component kits and UI templates",
        owning_seat="ann-porter-external",
        revenue_stream="personality_packs",
        unit="licensed kit",
    ),
    # ── George Porter: compute and market positions ─────────────────────────
    SellableResource(
        resource_id="reserved-inference",
        location="Luminous",
        description="Inference and compute reserved below spot and not consumed",
        owning_seat="george-porter-external",
        revenue_stream="api_metering",
        unit="1k tokens",
    ),
    SellableResource(
        resource_id="treasury-position",
        location="Royal Bank of Arcadia",
        description="Treasury and market exposure modelling on the estate's own balance",
        owning_seat="george-porter-external",
        revenue_stream="marketplace_fees",
        unit="advisory note",
        constraint=Constraint.REGULATED,
        constraint_note=(
            "Advisory only. Executing trades in securities or crypto on another "
            "party's behalf is a regulated activity Trancendos is not authorised "
            "for, so this resource can produce a recommendation and a rationale "
            "and never an order."
        ),
    ),
    # ── Edward Porter: expertise as a product ───────────────────────────────
    SellableResource(
        resource_id="compliance-profiles",
        location="The Town Hall",
        description=(
            "Governance and compliance profiles the estate wrote for itself -- "
            "sector profiles, control mappings, audit evidence packs"
        ),
        owning_seat="edward-porter-external",
        revenue_stream="white_label_licenses",
        unit="profile licence",
    ),
    SellableResource(
        resource_id="workflow-templates",
        location="The Digital Grid",
        description="Workflow DAG templates proven in the estate's own operation",
        owning_seat="edward-porter-external",
        revenue_stream="white_label_licenses",
        unit="template licence",
    ),
    SellableResource(
        resource_id="consolidation-engagement",
        location="Think Tank",
        description=(
            "Scoped engagement replacing a client's several tools with one Location of the platform"
        ),
        owning_seat="edward-porter-external",
        revenue_stream="white_label_licenses",
        unit="engagement",
        constraint=Constraint.CLIENT_DERIVED,
        constraint_note=(
            "Findings from one client's estate belong to that client. A "
            "consolidation engagement is sellable; the evidence gathered inside "
            "it is not resellable without their explicit agreement."
        ),
    ),
    SellableResource(
        resource_id="certification",
        location="The Academy",
        description="Trancendos developer certification and course material",
        owning_seat="edward-porter-external",
        revenue_stream="certification_fees",
        unit="certification",
    ),
    # ── James Porter: data, knowledge, audience ─────────────────────────────
    SellableResource(
        resource_id="metered-api",
        location="API Marketplace",
        description="Metered access to platform APIs above the free tier",
        owning_seat="james-porter-external",
        revenue_stream="api_metering",
        unit="1k requests",
    ),
    SellableResource(
        resource_id="knowledge-products",
        location="The Library",
        description="Knowledge products written by the estate from its own practice",
        owning_seat="james-porter-external",
        revenue_stream="data_insights",
        unit="report",
        constraint=Constraint.LICENSED_IN,
        constraint_note=(
            "The Library holds both material the estate authored and material it "
            "only licenses -- analyst research, vendor documentation, purchased "
            "datasets. Only the former is sellable. The licence on the latter "
            "forbids redistribution, and a knowledge product is redistribution."
        ),
    ),
    SellableResource(
        resource_id="threat-intelligence",
        location="Cryptex",
        description="Threat intelligence and CVE analysis produced by the estate's own defence",
        owning_seat="james-porter-external",
        revenue_stream="data_insights",
        unit="feed-month",
        constraint=Constraint.REGULATED,
        constraint_note=(
            "Observations from the estate's own perimeter are sellable. Anything "
            "requiring active testing of a third party's systems is not -- that "
            "needs their written authorisation, which a feed subscription is not."
        ),
    ),
    SellableResource(
        resource_id="market-intelligence",
        location="Section 7",
        description="Market and sector intelligence assembled from public sources",
        owning_seat="james-porter-external",
        revenue_stream="data_insights",
        unit="report",
        constraint=Constraint.LICENSED_IN,
        constraint_note=(
            "Section 7 reads licensed sources as well as public ones. A report "
            "built on the estate's own synthesis of public material is sellable; "
            "one reproducing licensed content is not."
        ),
    ),
    SellableResource(
        resource_id="usage-aggregates",
        location="The Observatory",
        description="Aggregate, non-identifying platform usage and reliability trends",
        owning_seat="james-porter-external",
        revenue_stream="data_insights",
        unit="report",
        constraint=Constraint.PERSONAL_DATA,
        constraint_note=(
            "Built from audit records of real people's activity. Sellable only "
            "where aggregation is genuinely non-identifying -- small cohorts "
            "re-identify, so cohort size is the control, not the intention."
        ),
    ),
    SellableResource(
        resource_id="ad-inventory",
        location="Arcadia",
        description="Opt-in contextual advertising inventory on platform surfaces",
        owning_seat="james-porter-external",
        revenue_stream="ad_revenue",
        unit="1k impressions",
        constraint=Constraint.PERSONAL_DATA,
        constraint_note=(
            "Contextual only, and only for users who opted in. Behavioural "
            "targeting would make a user's activity the product, which the "
            "external mandate excludes."
        ),
    ),
)


def by_seat(seat_id: str) -> List[SellableResource]:
    """Every resource one external seat is responsible for selling."""
    return [r for r in SELLABLE_RESOURCES if r.owning_seat == seat_id]


def by_location(location: str) -> List[SellableResource]:
    """Every sellable resource one Location produces."""
    return [r for r in SELLABLE_RESOURCES if r.location == location]


def get_resource(resource_id: str) -> SellableResource | None:
    return next((r for r in SELLABLE_RESOURCES if r.resource_id == resource_id), None)


def constrained_resources() -> Dict[Constraint, List[SellableResource]]:
    """Resources carrying a constraint, grouped by which one.

    Exposed because "what can we not simply sell, and why" is a question an
    operator will ask before any individual valuation matters.
    """
    grouped: Dict[Constraint, List[SellableResource]] = {}
    for resource in SELLABLE_RESOURCES:
        if resource.constraint is not Constraint.NONE:
            grouped.setdefault(resource.constraint, []).append(resource)
    return grouped


def _external_seat_ids() -> set:
    from src.entities.platform import EXTERNAL_SEATS

    return {seat.seat_id for seats in EXTERNAL_SEATS.values() for seat in seats}


def validate_catalogue() -> List[str]:
    """Every problem with the catalogue, as readable sentences.

    Three references can rot independently: a Location can be renamed in
    `PLATFORM_ENTITIES`, an external seat can be renamed in `EXTERNAL_SEATS`,
    and a revenue stream can be renamed in `PassiveRevenueEngine.STREAMS`.
    Any of the three leaves an entry here pointing at something that no longer
    exists, and an opportunity book built on it would name a service the
    platform does not have or book income into a ledger that will not take it.

    Locations and seats are checked at import below, because both come from
    `src.entities.platform`, which this module already depends on and which is
    pure data. Revenue streams are checked only here, to keep importing the
    catalogue from pulling in the billing module; the engine calls this on
    construction and `tests/test_exchange_sources.py` calls it directly, so
    the check is enforced -- just not at import time.
    """
    from src.entities.platform import PLATFORM_ENTITIES
    from src.monetisation.billing import PassiveRevenueEngine

    problems: List[str] = []
    seat_ids = _external_seat_ids()
    seen: set = set()

    for resource in SELLABLE_RESOURCES:
        if resource.resource_id in seen:
            problems.append(f"{resource.resource_id}: duplicate resource_id")
        seen.add(resource.resource_id)

        if resource.location not in PLATFORM_ENTITIES:
            problems.append(
                f"{resource.resource_id}: location {resource.location!r} is not a "
                f"canonical Location in PLATFORM_ENTITIES"
            )
        if resource.owning_seat not in seat_ids:
            problems.append(
                f"{resource.resource_id}: owning_seat {resource.owning_seat!r} is not "
                f"an external seat in EXTERNAL_SEATS"
            )
        if resource.revenue_stream not in PassiveRevenueEngine.STREAMS:
            problems.append(
                f"{resource.resource_id}: revenue_stream {resource.revenue_stream!r} "
                f"is not a stream PassiveRevenueEngine can book into"
            )
        if resource.constraint is not Constraint.NONE and not resource.constraint_note:
            problems.append(
                f"{resource.resource_id}: carries constraint "
                f"{resource.constraint.value!r} with no written reason"
            )

    return problems


def _validate_references_available_at_import() -> None:
    """Fail on a rotted Location or seat reference as soon as this is imported.

    Deliberately loud. A revenue inventory naming a Location the platform no
    longer has is worse than no inventory: it reads as authoritative.
    """
    from src.entities.platform import PLATFORM_ENTITIES

    seat_ids = _external_seat_ids()
    broken = [
        f"{r.resource_id} -> {r.location!r}"
        for r in SELLABLE_RESOURCES
        if r.location not in PLATFORM_ENTITIES
    ] + [
        f"{r.resource_id} -> seat {r.owning_seat!r}"
        for r in SELLABLE_RESOURCES
        if r.owning_seat not in seat_ids
    ]
    if broken:
        raise ValueError(
            "src/exchange/sources.py references entities that no longer exist: " + "; ".join(broken)
        )


_validate_references_available_at_import()
