"""
Section 7 — Background Intelligence & Investigation Service
===========================================================
Lead AI: (classified — internal placeholder name)
Role: Passive intelligence gathering, threat research, advancement study.

Section 7 operates entirely in the background. It:
  - Ingests CVE feeds, security advisories, research papers, web scans
  - Classifies intelligence by type (threat / research / knowledge / web_scan)
  - Routes intelligence through The Observatory (every event is logged)
  - Distributes to: Cryptex (threats), Think Tank (research), The Library (knowledge)
  - Triggers The Lab if analysis results in a required code change

Information flow:
  External Sources → Section 7 → Observatory → {Cryptex, Think Tank, Library} → [Lab]

This package does NOT expose any user-facing HTTP routes.
It is scheduled by the cron-service worker or run as a standalone daemon.
"""

from src.section7.information_router import InformationRouter, IntelligenceClass, get_router
from src.section7.intelligence_agent import IntelligenceAgent, IntelligenceItem

__all__ = [
    "IntelligenceAgent",
    "IntelligenceItem",
    "InformationRouter",
    "IntelligenceClass",
    "get_router",
]
