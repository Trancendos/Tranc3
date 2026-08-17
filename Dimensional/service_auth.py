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

REACHABILITY — READ THIS BEFORE ASSUMING THIS MODULE FIXED ANYTHING

All 41 of those services build from their own directory, so none of them can
import `Dimensional/` today. Publishing a canonical module and declaring the
duplication solved would produce a 42nd implementation that nobody calls — which
is exactly what TASD-001 did when it consolidated four circuit breakers onto an
`src/`-only home that 74 workers could not reach, after which chaos-party wrote
a fifth.

So this module is the destination, not the migration. Two things make a service
actually use it:

  1. vendor `Dimensional/service_auth.py` into the worker's build context and
     COPY it in the Dockerfile — the route `hive-service` and
     `dimensional-nexus-service` already take, and which
     `scripts/check_worker_build_context.py` now guards against drift; or
  2. build that worker from the repo root, which puts the whole core on its
     path at the cost of image size.

Until a service takes one of those routes, the immediate defect — the
timing-unsafe comparison — is fixed in place with `hmac.compare_digest`. That
needs no import from here at all, because `hmac` is stdlib and reachable from
every build context. Getting the security outcome did not require waiting for
the architecture.

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

__all__ = ["ServiceAuthError", "verify_internal_secret", "internal_secret_configured"]


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
