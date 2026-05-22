# src/auth/dependencies.py
# Shim: re-export get_current_user from root-level auth.py
# The MCP server imports from src.auth.dependencies for packaging consistency.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from auth import get_current_user  # codeql[py/cyclic-import]
except ImportError:
    from fastapi import HTTPException, status

    async def get_current_user(credentials=None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth module not available",
        )


__all__ = ["get_current_user"]
