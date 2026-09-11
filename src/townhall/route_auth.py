"""The Town Hall's write policy, defined once.

Three routers under `/townhall` — routing, ITSM and PLM — each carried their
own copy of the same two lines:

    if current_user.get("role") != "admin":
        raise HTTPException(403, ...)

Three copies of one policy is three places to change it and two places to
forget. The Town Hall is the estate's governance surface, so the failure mode
of forgetting one is not cosmetic: it is a write path that records a governance
decision without checking who made it. That is exactly the gap `plm_routes`
carried until it was found.

`_actor` is here for the same reason and a sharper one. `requested_by`,
`recorded_by` and `approver` were request-body fields written durably into the
lifecycle history, so the audit trail recorded whatever name the caller typed.
An attribution the caller chooses is not attribution.
"""

from __future__ import annotations

from typing import Any, Mapping

from fastapi import HTTPException

#: Where a principal's name is looked for, in order. `sub` is the JWT subject;
#: `username` is what `auth.get_current_user_dep` returns for a session.
_IDENTITY_KEYS = ("username", "sub", "id")


def require_admin(current_user: Mapping[str, Any]) -> None:
    """Refuse anyone who is not an admin.

    Reads stay open across the Town Hall by design — gate state, routing
    decisions and ITSM records are not secrets. Declaring one of them satisfied
    is what needs the role.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for this action")


def actor(current_user: Mapping[str, Any]) -> str:
    """The name to record against this action, taken from the token.

    Refuses rather than falling back to a placeholder. A governance record
    reading `approver: unknown` still reads as attributed, and is worse than
    one that was never written.
    """
    for key in _IDENTITY_KEYS:
        value = current_user.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HTTPException(status_code=403, detail="authenticated principal has no identity")
