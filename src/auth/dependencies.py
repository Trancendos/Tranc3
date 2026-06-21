"""Re-export shim — canonical auth dependency lives in src/auth/facade.py."""

from src.auth.facade import get_current_user, get_current_user_dep  # noqa: F401

__all__ = ["get_current_user", "get_current_user_dep"]
