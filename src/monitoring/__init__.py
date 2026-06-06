"""
Monitoring — Zero-Cost Usage Tracking and Alerting
===================================================
Tracks free-tier consumption across all platform services to prevent
surprise costs. Exposes FastAPI routes for dashboard integration.
"""

from src.monitoring.zero_cost_tracker import UsageRecord, ZeroCostTracker, tracker

__all__ = ["ZeroCostTracker", "UsageRecord", "tracker"]
