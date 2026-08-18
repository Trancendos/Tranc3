"""Canonical service-to-service authentication for the platform (SFSC).

THE PROBLEM THIS EXISTS FOR

41 services each hand-rolled their own `X-Internal-Secret` check. One concern,
41 implementations, and they did not agree:

  * 4 failed **open** — an unset or blank INTERNAL_SECRET skipped the check
    entirely, and `.env.example` ships that variable blank. Fixed separately;
    the audit log, Fabulousa, infinity-ai and health-aggregator were all
    accepting unauthenticated calls whenever an operator copied the template
    without editing it.
  * 18 compared with `!=`, which returns on the first differing byte and leaks
    the secret's prefix through response timing.
  * The rest were already constant-time, by luck rather than by policy.

A single implementation cannot drift 41 ways. This is that implementation.

REACHABILITY — WHY THIS MODULE IS NOW ACTUALLY CALLED

Publishing a canonical module does not remove duplication on its own. TASD-001
consolidated four circuit breakers onto an `src/`-only home that 74 workers
could not import, after which chaos-party wrote a fifth. This module was written
into the same trap and stayed unused until two things were fixed:

  1. Delivery. Own-context workers receive `Dimensional/` through the
     `sharedcore` named build context, wired by
     `scripts/apply_shared_core_contexts.py`; `hive-service` and
     `dimensional-nexus-service` vendor it instead, guarded against drift by
     `scripts/check_worker_build_context.py`.
  2. Import cost. `Dimensional/__init__.py` used to import the package eagerly,
     which pulled torch and numpy through `genetics` and `liquid`. A worker
     installing five packages could not `from Dimensional.service_auth import
     ...` — it failed on torch before reaching this stdlib-only module. The
     package now resolves lazily, so importing this costs this.

`scripts/migrate_internal_auth.py` then rewrote every hand-rolled gate to call
here, and runs in CI with `--check` so an 85th cannot be added quietly.

The estate is not uniform behind this module and does not pretend to be: gates
answer 401 or 403 according to what their existing callers were written
against, which the migration preserved deliberately. What is uniform is the
comparison and the fail-closed behaviour — the two things that were wrong.

DESIGN

Fail closed. A missing secret raises rather than waving the request through:
silence is indistinguishable from working authentication, and the failure mode
of the alternative is an open service nobody notices.

No FastAPI import. This module deals in strings and raises a plain exception, so
it is usable from a worker, a script, or a non-HTTP caller. Callers translate
`ServiceAuthError` into whatever their framework expects — the two HTTP status
codes the platform already uses are 503 for "not configured" and 403/401 for
"wrong secret", which `status_code` preserves.
"""

from __future__ import annotations

import hmac
import os

__all__ = [
    "ServiceAuthError",
    "verify_internal_secret",
    "internal_secret_configured",
    "check_internal_secret",
]


class ServiceAuthError(Exception):
    """Raised when an internal service call cannot be authenticated.

    `status_code` distinguishes the two cases a caller must handle differently:
    503 means this service is misconfigured and no caller can succeed; 403 means
    the caller presented the wrong secret.
    """

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def internal_secret_configured(secret: str | None = None) -> bool:
    """True when an internal secret is actually set.

    Treats whitespace as unset: `INTERNAL_SECRET="   "` is a misconfiguration,
    not a secret, and accepting it would authenticate any caller who sent the
    same spaces.
    """
    value = os.getenv("INTERNAL_SECRET", "") if secret is None else secret
    return bool(value and value.strip())


def verify_internal_secret(
    presented: str | None,
    expected: str | None = None,
    *,
    unconfigured_status: int = 503,
    mismatch_status: int = 403,
) -> None:
    """Verify a presented X-Internal-Secret. Raises ServiceAuthError, or returns None.

    `expected` defaults to the INTERNAL_SECRET environment variable so the
    common case is a one-argument call.

    The comparison is `hmac.compare_digest`, not `!=`. A plain comparison exits
    at the first differing byte, so response latency reveals how many leading
    characters a guess got right and the secret can be recovered a byte at a
    time.
    """
    secret = os.getenv("INTERNAL_SECRET", "") if expected is None else (expected or "")
    if not internal_secret_configured(secret):
        raise ServiceAuthError(
            "INTERNAL_SECRET is not configured; refusing unauthenticated access",
            status_code=unconfigured_status,
        )
    if not hmac.compare_digest(presented or "", secret):
        raise ServiceAuthError("Forbidden", status_code=mismatch_status)


def check_internal_secret(
    presented: str | None,
    expected: str | None = None,
    *,
    unconfigured_status: int = 503,
    mismatch_status: int = 403,
    detail: str = "Forbidden",
) -> tuple[bool, int, str]:
    """Non-raising form: returns (ok, status_code, detail).

    Exists because not every gate on the platform can refuse by raising. ASGI
    middleware must *return* a response — raising inside it bypasses the
    remaining stack — and a WebSocket gate refuses with a close code rather than
    an HTTP status at all. Those callers previously had to reimplement the
    comparison because the only shared entry point raised; this gives them the
    same one verification with a return value they can act on.

    `status_code` and `detail` are meaningful only when `ok` is False.
    """
    try:
        verify_internal_secret(
            presented,
            expected,
            unconfigured_status=unconfigured_status,
            mismatch_status=mismatch_status,
        )
    except ServiceAuthError as exc:
        return (
            False,
            exc.status_code,
            (str(exc) if exc.status_code == unconfigured_status else detail),
        )
    return True, 200, ""
