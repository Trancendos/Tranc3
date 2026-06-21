"""Re-export shim — canonical implementation lives in src/shared/rate_limiter.py."""

from src.shared.rate_limiter import AdaptiveRateLimiter  # noqa: F401

__all__ = ["AdaptiveRateLimiter"]
