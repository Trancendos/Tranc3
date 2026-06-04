"""
Master Worker — Sovereign Orchestration Engine
===============================================
Replaces GitHub Actions and Cloudflare Workers with a self-hosted,
zero-cost MAPE-K (Monitor, Analyse, Plan, Execute, Knowledge) control loop.

Components:
  mape_k.py              — MAPE-K orchestration loop
  adaptive_blueprints.py — Smart platform-agnostic deployment templates
  zero_cost_enforcer.py  — Quota monitoring + automatic platform rotation
  platform_registry.py   — Free-tier platform inventory and health
"""

from .adaptive_blueprints import BlueprintEngine, BlueprintType
from .mape_k import ControlLoopState, MapeKConfig, MapeKLoop
from .platform_registry import PlatformRegistry
from .zero_cost_enforcer import QuotaStatus, ZeroCostEnforcer

__all__ = [
    "MapeKLoop",
    "MapeKConfig",
    "ControlLoopState",
    "ZeroCostEnforcer",
    "QuotaStatus",
    "BlueprintEngine",
    "BlueprintType",
    "PlatformRegistry",
]
