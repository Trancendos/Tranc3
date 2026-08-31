"""The Arcadian Exchange's external mandate — the sell-side of the platform.

`src/monetisation/` books income the platform has already earned. This package
is the half that runs before that: what the estate could sell, what it is
plausibly worth, and what it is not permitted to sell at all.

    sources.py     the inventory -- what each Location produces, which
                   external seat owns selling it, and what constrains it
    valuation.py   what one opportunity is worth, and how much of that
                   figure to believe; refuses to invent a number
    governance.py  whether it may be pursued, and who signs it off
    engine.py      pulls, values, rules on, ranks, and learns from outcomes
    routes.py      /exchange, mounted in api.py

Realised income still books through `PassiveRevenueEngine`'s thirteen streams.
Every resource here names the stream it settles into, so there is one ledger
and one answer to "what did we earn".
"""
