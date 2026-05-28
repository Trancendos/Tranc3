# src/auth/dependencies.py
# Shim: re-export get_current_user from root-level auth.py
# The MCP server imports from src.auth.dependencies for packaging consistency.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from auth import get_current_user  # noqa: F401
except ImportError:
    from fastapi import HTTPException, status
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    _bearer = HTTPBearer(auto_error=False)

    async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth module not available",
        )


__all__ = ["get_current_user"]
