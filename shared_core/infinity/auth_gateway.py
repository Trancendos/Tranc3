"""Backward-compatibility shim — canonical: Dimensionals.infinity.auth_gateway"""

from Dimensionals.infinity.auth_gateway import *  # noqa: F401, F403
from Dimensionals.infinity.auth_gateway import (  # noqa: F401
    _extract_api_key,
    _extract_bearer_token,
    _tier_to_role,
    _validate_api_key,
    _validate_jwt_token,
)
