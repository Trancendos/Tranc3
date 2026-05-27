"""
src/master/adapters — Unification bridge layer for all bot/worker/scraper systems.

Unifies 4 separate registry systems under a single BotSwarm dispatch contract:

  1. tranc3_bots   — tranc3-bots/bots/registry.py (async HANDLERS, 12 types)
  2. src_workers   — src/workers/bot_registry.py (Redis WorkerPool, 7 types)
  3. nanocode      — src/healing/nanocode_bots.py (FailureMode repair, 9 modes)
  4. aeonmind      — AeonMind BotServiceWorker (15 capabilities, Tier 5)

Each adapter exposes:
    async def dispatch(action: str, params: dict) -> Any
"""

from __future__ import annotations

from .aeonmind_adapter import AeonMindAdapter
from .nanocode_adapter import NanocodeAdapter
from .src_workers_adapter import SrcWorkersAdapter
from .tranc3_bots_adapter import Tranc3BotsAdapter
from .registry import AdapterRegistry, get_adapter

__all__ = [
    "AdapterRegistry",
    "AeonMindAdapter",
    "NanocodeAdapter",
    "SrcWorkersAdapter",
    "Tranc3BotsAdapter",
    "get_adapter",
]
