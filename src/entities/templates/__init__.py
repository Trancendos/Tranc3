"""
AI Base Templates — Tier 1 through Tier 5 base classes.

Each template encodes the tier's behavioural contract, adaptive traits,
and lifecycle hooks. Concrete AI personalities sub-class from here.

Tier hierarchy (canonical):
    Tier 0  — Human (Trancendos operator)
    Tier 1  — Orchestrators:  TrancOne, The Queen, tAImra (off by default)
    Tier 2  — Primes:         T2ance
    Tier 3  — AIs:            Tranc3  ← the platform's flagship AI base
    Tier 4  — Agents:         InfinityAgent
    Tier 5  — Bots / Workers: InfinityBot
"""

from .infinity_agent_base import InfinityAgent
from .infinity_bot_base import InfinityBot
from .t2ance_base import T2ance
from .tranc3_base import Tranc3
from .trance_one_base import TrancOne

__all__ = ["TrancOne", "T2ance", "Tranc3", "InfinityAgent", "InfinityBot"]
