"""Backward-compatibility shim — canonical auth lives in src/auth/facade.py.

All workers and API routes should import from there:
    from src.auth.facade import AuthFacade, get_current_user, create_token, verify_token
"""
from src.auth.facade import (  # noqa: F401
    AuthFacade,
    create_token,
    get_current_user,
    get_current_user_dep,
    hash_password,
    verify_password,
    verify_token,
)
