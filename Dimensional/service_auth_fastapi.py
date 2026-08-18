"""FastAPI adapter for the canonical service-to-service check (SFSC).

`Dimensional.service_auth` deliberately imports no web framework: it deals in
strings and raises a plain exception, so a script or a non-HTTP caller can use
it. That leaves every FastAPI service to write the same four-line translation
from `ServiceAuthError` to `HTTPException` — which is how one concern became 84
hand-rolled gates in the first place. This module writes that translation once.

Import cost stays honest: this imports fastapi, which every service using it
already installs. Anything that must not depend on a web framework imports
`Dimensional.service_auth` directly and translates the error itself.

WHY THE STATUS CODES ARE PARAMETERS

The estate is not consistent: some gates answer 401, others 403, for the same
condition. Normalising that silently would change the contract every existing
caller is written against, so the migration preserves each service's own code
and this module takes it as an argument. The one code that is *not* negotiable
is the unconfigured case: a service with no INTERNAL_SECRET set answers 503,
because "I cannot authenticate anyone" is a fault in this service, not a
judgement about the caller.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException

from Dimensional.service_auth import ServiceAuthError, verify_internal_secret

__all__ = [
    "guard_internal_secret",
    "require_internal_secret",
    "internal_secret_dependency",
]


def guard_internal_secret(
    presented: str | None,
    expected: str | None = None,
    *,
    unconfigured_status: int = 503,
    mismatch_status: int = 403,
    detail: str = "Forbidden",
) -> None:
    """Verify a presented secret, raising HTTPException instead of ServiceAuthError.

    The mismatch detail is caller-supplied and defaults to a bare "Forbidden".
    The unconfigured detail is not caller-supplied: it names the missing variable,
    because that message is read by the operator who has to fix it, never by the
    caller who cannot.
    """
    try:
        verify_internal_secret(
            presented,
            expected,
            unconfigured_status=unconfigured_status,
            mismatch_status=mismatch_status,
        )
    except ServiceAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc) if exc.status_code == unconfigured_status else detail,
        ) from exc


async def require_internal_secret(
    x_internal_secret: Optional[str] = Header(default=None),
) -> None:
    """Ready-made FastAPI dependency for the common case.

    Use as `Depends(require_internal_secret)`, or on a router:
    `APIRouter(dependencies=[Depends(require_internal_secret)])`. Reads
    INTERNAL_SECRET from the environment and answers 403 on mismatch. Services
    needing a different code use `internal_secret_dependency` instead.
    """
    guard_internal_secret(x_internal_secret)


def internal_secret_dependency(
    *,
    expected: str | None = None,
    unconfigured_status: int = 503,
    mismatch_status: int = 403,
    detail: str = "Forbidden",
):
    """Build a dependency that keeps one service's existing status code and detail.

    Returned as a closure rather than as a class with `__call__` so that FastAPI
    reads the signature of the inner function and sees the `Header` default —
    a callable instance would need the same signature declared anyway, with more
    ceremony and one more place to get it wrong.

    `expected` is captured at call time, not at build time, when left as None:
    passing a module-level constant here would freeze whatever INTERNAL_SECRET
    held at import, and a worker that reloads its configuration would keep
    authenticating against the old value.
    """

    async def _dependency(
        x_internal_secret: Optional[str] = Header(default=None),
    ) -> None:
        guard_internal_secret(
            x_internal_secret,
            expected,
            unconfigured_status=unconfigured_status,
            mismatch_status=mismatch_status,
            detail=detail,
        )

    return _dependency
