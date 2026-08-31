"""Whether an opportunity may be pursued, and by whom it must be signed off.

The external mandate is a decision about what Trancendos is willing to sell.
This module holds that decision, and it *blocks* rather than annotates: a
refused opportunity never reaches the ranked book, and an escalated one is
carried with its decision attached so nobody has to remember to look.

That distinction matters here more than usual. This estate has repeatedly
produced controls that run, report, and never hold -- a merge gate missing its
vulnerability census, a freshness check charging the wrong pull request. A
revenue engine that scored a regulated opportunity 0.9 and left the reader to
notice the word "regulated" would be the same shape of mistake with money
attached.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.exchange.sources import Constraint, SellableResource


class Decision(str, Enum):
    #: Free to pursue on ordinary commercial terms.
    CLEAR = "clear"
    #: May be pursued only after a named human signs it off. Carried in the
    #: book with the reason, never silently downgraded to CLEAR.
    ESCALATE = "escalate"
    #: Not sellable in the form proposed. Never enters the book.
    REFUSED = "refused"


@dataclass(frozen=True)
class Ruling:
    decision: Decision
    reason: str
    #: Who has to agree before an ESCALATE opportunity proceeds. The Chief
    #: Revenue Officer's seat holds the estate's own risk limits; anything
    #: touching regulation or personal data goes past a person as well.
    sign_off: Optional[str] = None

    @property
    def blocks(self) -> bool:
        """True for both ESCALATE and REFUSED.

        Callers that only need "may this proceed unattended" should ask
        this rather than testing for REFUSED, which would let an
        unsigned-off escalation through.
        """
        return self.decision is not Decision.CLEAR


#: Above this, even an unconstrained opportunity goes past the Chief Revenue
#: Officer. Not a risk model -- a deliberately blunt limit, so that the first
#: large deal is a decision somebody made rather than one the ranking made for
#: them. GBP.
ESCALATION_VALUE_THRESHOLD = 5_000.0

#: Below this many subjects an "aggregate" is not reliably non-identifying.
#: The estate had no such floor anywhere before this -- grep for "cohort"
#: across src/ returns nothing -- so this establishes one rather than
#: inheriting it. 50 is the common k-anonymity working figure for published
#: aggregates; it is a starting position a privacy review should confirm or
#: raise, not a derived number, and it is written here as a single constant
#: precisely so that review has one place to change.
MIN_AGGREGATION_COHORT = 50


def rule(
    resource: SellableResource,
    *,
    estimated_value: float,
    aggregation_cohort: Optional[int] = None,
    counterparty_authorisation: bool = False,
    content_is_own_work: Optional[bool] = None,
) -> Ruling:
    """Decide whether this opportunity may proceed.

    The keyword arguments are the facts a constraint needs to be resolved.
    Each defaults to the *unsafe-to-assume* value, so an opportunity raised
    without the relevant fact is escalated or refused rather than cleared --
    silence is not evidence that a condition was met.
    """
    if resource.constraint is Constraint.LICENSED_IN:
        if content_is_own_work is not True:
            return Ruling(
                Decision.REFUSED,
                (
                    f"{resource.resource_id} draws on material the platform holds "
                    f"under licence, and the proposal has not established that this "
                    f"instance is the estate's own work. {resource.constraint_note}"
                ),
            )
        return Ruling(
            Decision.ESCALATE,
            (
                f"Confirmed as the estate's own work, but {resource.location} mixes "
                f"authored and licensed material, so provenance is checked by a "
                f"person before publication."
            ),
            sign_off="edward-porter-external",
        )

    if resource.constraint is Constraint.PERSONAL_DATA:
        if aggregation_cohort is None:
            return Ruling(
                Decision.REFUSED,
                (
                    f"{resource.resource_id} derives from real people's activity and "
                    f"no cohort size was stated. {resource.constraint_note}"
                ),
            )
        if aggregation_cohort < MIN_AGGREGATION_COHORT:
            return Ruling(
                Decision.REFUSED,
                (
                    f"Cohort of {aggregation_cohort} is below the minimum of "
                    f"{MIN_AGGREGATION_COHORT}. Small cohorts re-identify, so the "
                    f"aggregate would not be non-identifying in the way the mandate "
                    f"requires."
                ),
            )
        return Ruling(
            Decision.ESCALATE,
            (
                f"Cohort of {aggregation_cohort} clears the re-identification "
                f"minimum, but selling anything derived from users' activity is "
                f"reviewed by a person."
            ),
            sign_off="human",
        )

    if resource.constraint is Constraint.REGULATED:
        return Ruling(
            Decision.ESCALATE,
            (f"{resource.resource_id} sits in a regulated class. {resource.constraint_note}"),
            sign_off="human",
        )

    if resource.constraint is Constraint.CLIENT_DERIVED:
        if not counterparty_authorisation:
            return Ruling(
                Decision.REFUSED,
                (
                    f"{resource.resource_id} is derived from a client's own estate "
                    f"and no authorisation from them was recorded. "
                    f"{resource.constraint_note}"
                ),
            )
        return Ruling(
            Decision.CLEAR,
            "Client authorisation recorded.",
        )

    if estimated_value >= ESCALATION_VALUE_THRESHOLD:
        return Ruling(
            Decision.ESCALATE,
            (
                f"Estimated value of £{estimated_value:,.2f} is at or above the "
                f"£{ESCALATION_VALUE_THRESHOLD:,.0f} limit, so the Chief Revenue "
                f"Officer's seat signs it off rather than the ranking deciding."
            ),
            sign_off="clarence-porter-external",
        )

    return Ruling(Decision.CLEAR, "No constraint, and below the escalation limit.")
