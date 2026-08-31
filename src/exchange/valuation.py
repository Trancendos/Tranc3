"""What an opportunity is worth, and how much of that figure to believe.

The hard constraint on this module is that it must not invent revenue. A
monetisation engine that produces confident projections from nothing is worse
than no engine: it reads as evidence, gets quoted in a plan, and the plan is
built on a number nobody measured.

So a valuation carries its own basis. Where the platform has a real price
signal -- a rate card, an observed transaction, a metered unit cost -- the
estimate is grounded and says so. Where it does not, the valuation is returned
with `Basis.NONE` and a zero estimate, and the engine reports it as an
opportunity that cannot yet be priced rather than guessing. "We do not know
what this is worth" is a useful answer; a fabricated £4,200 is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Basis(str, Enum):
    """Where the unit price came from, strongest first."""

    #: Observed in a settled transaction of this same resource.
    REALISED = "realised"
    #: A published rate card or a metered cost the platform actually charges.
    RATE_CARD = "rate_card"
    #: A comparable market price for an equivalent unit, supplied by the caller.
    COMPARABLE = "comparable"
    #: No price signal at all. Estimate is 0 and confidence is 0.
    NONE = "none"


#: How much to believe each basis, before per-source calibration. Ordering is
#: the point rather than the exact figures: a settled transaction of the same
#: thing beats a rate card, which beats somebody's comparable.
BASIS_CONFIDENCE = {
    Basis.REALISED: 0.90,
    Basis.RATE_CARD: 0.70,
    Basis.COMPARABLE: 0.40,
    Basis.NONE: 0.0,
}


@dataclass(frozen=True)
class Valuation:
    resource_id: str
    units: float
    unit_price: float
    #: units * unit_price, before cost to serve.
    gross: float
    cost_to_serve: float
    #: gross - cost_to_serve. Can be negative, and is reported that way; an
    #: opportunity that costs more to fulfil than it earns is a finding.
    net: float
    basis: Basis
    #: 0.0-1.0. BASIS_CONFIDENCE adjusted by the source's realisation ratio.
    confidence: float
    #: One sentence a reader can check. Never omitted, including for NONE.
    rationale: str

    @property
    def priceable(self) -> bool:
        """Whether a price signal existed at all.

        False means the estimate is zero because nothing was known, not
        because the opportunity is worthless -- the two read identically
        from `net` alone, which is why this is asked separately.
        """
        return self.basis is not Basis.NONE

    @property
    def risk_adjusted(self) -> float:
        """Net weighted by how much of the estimate is believable.

        The ranking sorts on this rather than on `net`, so a large number
        resting on a weak basis does not outrank a smaller measured one.
        """
        return self.net * self.confidence


def value(
    resource_id: str,
    *,
    units: float,
    unit_price: Optional[float] = None,
    basis: Basis = Basis.NONE,
    cost_to_serve: float = 0.0,
    realisation_ratio: float = 1.0,
) -> Valuation:
    """Value one opportunity.

    `realisation_ratio` is the adaptive term: the engine tracks, per source,
    what fraction of previously estimated value actually settled, and passes it
    in here. A source that has consistently over-promised sees its confidence
    fall without anyone editing a table, which is what makes the ranking
    improve with use rather than staying as accurate as its first guess.
    """
    # Validated before the unpriced branch, not after it. With the checks
    # below the branch, `value(units=10, cost_to_serve=-100)` returned an
    # unpriced valuation with net=+100 -- a negative cost silently becoming
    # £100 of profit on a resource with no price signal at all. This module
    # exists to make fabricated revenue unrepresentable, and that was a way
    # to fabricate it. Caught by CodeRabbit on #992.
    if units < 0 or cost_to_serve < 0 or (unit_price is not None and unit_price < 0):
        raise ValueError(
            "units, unit_price and cost_to_serve must all be non-negative; "
            f"got units={units}, unit_price={unit_price}, cost_to_serve={cost_to_serve}"
        )

    if unit_price is None or basis is Basis.NONE:
        return Valuation(
            resource_id=resource_id,
            units=units,
            unit_price=0.0,
            gross=0.0,
            cost_to_serve=cost_to_serve,
            # `-0.0` otherwise, which is true but reads as a bug in a report.
            net=(-cost_to_serve if cost_to_serve else 0.0),
            basis=Basis.NONE,
            confidence=0.0,
            rationale=(
                "No price signal for this resource -- no settled transaction, no "
                "rate card, and no comparable supplied. Reported unpriced rather "
                "than estimated, because a made-up figure here would be quoted "
                "later as though it had been measured."
            ),
        )

    gross = units * unit_price
    net = gross - cost_to_serve
    # Clamped because a ratio above 1 means a source under-promised, which is
    # good news about that source but not a reason to believe a *different*
    # estimate more than its basis warrants.
    ratio = max(0.0, min(1.0, realisation_ratio))
    confidence = round(BASIS_CONFIDENCE[basis] * ratio, 4)

    return Valuation(
        resource_id=resource_id,
        units=units,
        unit_price=unit_price,
        gross=round(gross, 2),
        cost_to_serve=round(cost_to_serve, 2),
        net=round(net, 2),
        basis=basis,
        confidence=confidence,
        rationale=(
            f"{units:g} x £{unit_price:,.2f} = £{gross:,.2f} gross, less "
            f"£{cost_to_serve:,.2f} to serve. Priced from {basis.value}; "
            f"confidence {BASIS_CONFIDENCE[basis]:.2f} scaled by a realisation "
            f"ratio of {ratio:.2f} observed on this source."
        ),
    )
