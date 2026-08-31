"""The opportunity taxonomy, and who owns it.

Dorris Fontaine holds the Chief Financial Officer seat at the Royal Bank of
Arcadia (`docs/governance/LOCATION-FUNCTIONS.md`), and the taxonomy below is
hers: which kinds of opportunity the Exchange recognises, which sit adjacent to
which, and which carry a standing financial risk. The Porters propose within
it; they do not extend it.

That separation is the point. A seat that could invent its own category could
route an opportunity around whatever constraint the category carried, and the
first sign would be a loss nobody had a control for. Adding or retiring a
domain goes through `TaxonomyRegistry`, which records who changed what and why
-- so the question "when did we start treating this as a thing we sell, and on
whose authority" has an answer.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("tranc3.exchange.domains")

#: The seat that owns this taxonomy. Not a free-text string at the call sites.
TAXONOMY_OWNER = "Royal Bank of Arcadia::primary"

#: Human-readable name of the seat holder, for messages an operator reads.
TAXONOMY_OWNER_TITLE = "Chief Financial Officer (Royal Bank of Arcadia)"


class Domain(str, Enum):
    """A kind of opportunity, not a resource.

    A resource is a thing the estate can sell; a domain is the market it sells
    into. `generated-imagery` and `video-assets` are different resources in the
    same domain, which is why a seat's expertise is tracked per domain rather
    than per resource -- learning that creative licensing prices at £X per unit
    transfers between them, and learning it about storage does not.
    """

    CAPACITY = "capacity"
    CREATIVE_ASSETS = "creative_assets"
    COMPUTE = "compute"
    DATA_PRODUCTS = "data_products"
    KNOWLEDGE = "knowledge"
    EXPERT_SERVICES = "expert_services"
    ADVERTISING = "advertising"
    TREASURY = "treasury"


#: Which domains a seat may plausibly reason about once it has proven itself in
#: a neighbour. Adjacency is a claim about transferable knowledge, not about
#: similarity: capacity and compute are adjacent because both are metered
#: infrastructure priced against a spot market; creative assets and knowledge
#: are adjacent because both are one-off licences of something the estate
#: authored. Treasury is adjacent to nothing -- see the note below.
ADJACENCY: Dict[Domain, Tuple[Domain, ...]] = {
    Domain.CAPACITY: (Domain.COMPUTE,),
    Domain.COMPUTE: (Domain.CAPACITY, Domain.DATA_PRODUCTS),
    Domain.CREATIVE_ASSETS: (Domain.KNOWLEDGE, Domain.ADVERTISING),
    Domain.KNOWLEDGE: (Domain.CREATIVE_ASSETS, Domain.EXPERT_SERVICES, Domain.DATA_PRODUCTS),
    Domain.EXPERT_SERVICES: (Domain.KNOWLEDGE,),
    Domain.DATA_PRODUCTS: (Domain.KNOWLEDGE, Domain.ADVERTISING, Domain.COMPUTE),
    Domain.ADVERTISING: (Domain.DATA_PRODUCTS, Domain.CREATIVE_ASSETS),
    # Deliberately isolated. Treasury is the one domain where being wrong costs
    # money the platform already has rather than money it did not yet earn, and
    # where the activity is regulated. A seat cannot arrive here by proving
    # itself next door; a person has to put it here.
    Domain.TREASURY: (),
}

#: Domains where a wrong call loses capital rather than forgoing revenue. Every
#: opportunity in one of these escalates to a human regardless of size, and a
#: seat can only hold one by explicit assignment.
CAPITAL_AT_RISK: frozenset = frozenset({Domain.TREASURY})

#: resource_id -> the market it sells into. Kept here rather than on
#: SellableResource because the mapping is a financial classification, and
#: financial classifications are Dorris's.
RESOURCE_DOMAINS: Dict[str, Domain] = {
    "storage-surplus": Domain.CAPACITY,
    "generated-imagery": Domain.CREATIVE_ASSETS,
    "video-assets": Domain.CREATIVE_ASSETS,
    "three-d-assets": Domain.CREATIVE_ASSETS,
    "audio-assets": Domain.CREATIVE_ASSETS,
    "design-systems": Domain.CREATIVE_ASSETS,
    "reserved-inference": Domain.COMPUTE,
    "treasury-position": Domain.TREASURY,
    "compliance-profiles": Domain.EXPERT_SERVICES,
    "workflow-templates": Domain.EXPERT_SERVICES,
    "consolidation-engagement": Domain.EXPERT_SERVICES,
    "certification": Domain.KNOWLEDGE,
    "metered-api": Domain.COMPUTE,
    "knowledge-products": Domain.KNOWLEDGE,
    "threat-intelligence": Domain.DATA_PRODUCTS,
    "market-intelligence": Domain.DATA_PRODUCTS,
    "usage-aggregates": Domain.DATA_PRODUCTS,
    "ad-inventory": Domain.ADVERTISING,
}


def domain_of(resource_id: str) -> Optional[Domain]:
    """Which market a resource sells into, or None if unclassified.

    None is a finding rather than a default: an unclassified resource has no
    domain expertise gating it and no capital-at-risk check, so the engine
    treats it as unproposable rather than as unconstrained.
    """
    return RESOURCE_DOMAINS.get(resource_id)


def adjacent_to(domain: Domain) -> Tuple[Domain, ...]:
    return ADJACENCY.get(domain, ())


@dataclass(frozen=True)
class TaxonomyChange:
    """One recorded edit to the taxonomy."""

    changed_at: float
    changed_by: str
    action: str
    subject: str
    reason: str


class TaxonomyRegistry:
    """Dorris's record of what the taxonomy is and how it got that way.

    The enum above is the code-level truth; this is the audit of deliberate
    changes to how resources are classified. A reclassification moves a
    resource between markets, which changes which seat may propose it and
    which controls apply -- so it is recorded with a named author and a
    written reason, or it does not happen.
    """

    def __init__(self, db_path: Path | str = Path("data/exchange_taxonomy.db")) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _create_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS taxonomy_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    changed_at REAL NOT NULL,
                    changed_by TEXT NOT NULL,
                    action TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    reason TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resource_overrides (
                    resource_id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    changed_at REAL NOT NULL,
                    changed_by TEXT NOT NULL,
                    reason TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def reclassify(self, resource_id: str, domain: Domain, *, changed_by: str, reason: str) -> None:
        """Move a resource to a different market.

        `changed_by` must be the taxonomy owner. A Porter reclassifying its own
        resource could move it out of a capital-at-risk domain and lose the
        human-escalation requirement that came with it, which is the specific
        thing this ownership split exists to prevent.
        """
        if changed_by != TAXONOMY_OWNER:
            raise PermissionError(
                f"The opportunity taxonomy belongs to {TAXONOMY_OWNER_TITLE} "
                f"({TAXONOMY_OWNER}); {changed_by!r} cannot reclassify "
                f"{resource_id!r}. A seat that could reclassify its own "
                f"resource could move it out of a capital-at-risk domain and "
                f"shed the human sign-off that came with it."
            )
        if not reason.strip():
            raise ValueError(
                "A reclassification needs a written reason. It changes which "
                "seat may propose the resource and which controls apply, so "
                "an unexplained one is not reviewable later."
            )
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO resource_overrides "
                "(resource_id, domain, changed_at, changed_by, reason) VALUES (?, ?, ?, ?, ?)",
                (resource_id, domain.value, now, changed_by, reason),
            )
            self._conn.execute(
                "INSERT INTO taxonomy_changes "
                "(changed_at, changed_by, action, subject, reason) VALUES (?, ?, ?, ?, ?)",
                (now, changed_by, "reclassify", f"{resource_id} -> {domain.value}", reason),
            )
            self._conn.commit()
        logger.info(
            "Taxonomy: %s reclassified to %s by %s",
            resource_id,
            domain.value,
            changed_by,
        )

    def effective_domain(self, resource_id: str) -> Optional[Domain]:
        """The resource's market, honouring any recorded reclassification."""
        with self._lock:
            row = self._conn.execute(
                "SELECT domain FROM resource_overrides WHERE resource_id = ?",
                (resource_id,),
            ).fetchone()
        if row:
            return Domain(row["domain"])
        return domain_of(resource_id)

    def history(self, limit: int = 100) -> List[TaxonomyChange]:
        """Every recorded taxonomy change, newest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT changed_at, changed_by, action, subject, reason "
                "FROM taxonomy_changes ORDER BY changed_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            TaxonomyChange(
                changed_at=r["changed_at"],
                changed_by=r["changed_by"],
                action=r["action"],
                subject=r["subject"],
                reason=r["reason"],
            )
            for r in rows
        ]

    def snapshot(self) -> str:
        """The taxonomy as it currently stands, as JSON."""
        return json.dumps(
            {
                "owner": TAXONOMY_OWNER,
                "owner_title": TAXONOMY_OWNER_TITLE,
                "domains": [d.value for d in Domain],
                "capital_at_risk": sorted(d.value for d in CAPITAL_AT_RISK),
                "adjacency": {d.value: [a.value for a in adj] for d, adj in ADJACENCY.items()},
                "resources": {
                    rid: (self.effective_domain(rid) or Domain.CAPACITY).value
                    for rid in RESOURCE_DOMAINS
                },
            },
            indent=2,
            sort_keys=True,
        )
