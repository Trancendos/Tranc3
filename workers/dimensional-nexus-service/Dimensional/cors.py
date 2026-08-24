"""Shared CORS origin resolution for the Dimensional service apps.

`Dimensional/nexus/nexus_core.py` and `Dimensional/hive/hive_core.py` each build
a FastAPI app with `CORSMiddleware`, and both previously handed it a hardcoded
wildcard allow-list. They now resolve their origins here rather than each
parsing the environment themselves — two copies of this logic is how they came
to disagree in the first place.

(This docstring deliberately describes the old pattern in words rather than
quoting it. `scripts/compliance_drift_audit.py`'s `no_wildcard_cors` rule is a
plain-text scan of worker sources, so a literal example of the forbidden
expression would trip it even inside a comment explaining its removal.)

Resolution order, first source producing at least one origin wins:

    CORS_ORIGINS  ->  ALLOWED_ORIGINS  ->  http://localhost:3000

A *set but blank* variable falls through rather than winning with an empty list.
``os.getenv("CORS_ORIGINS", os.getenv("ALLOWED_ORIGINS", default))`` looks like it
does this but does not: an exported ``CORS_ORIGINS=""`` is present, so getenv
returns ``""``, the fallback never applies, and the parsed list is empty — which
hands ``CORSMiddleware`` an empty allow-list and silently turns *all* cross-origin
access off. Nothing raises; it surfaces later as browser requests failing for no
visible reason.

Wildcard handling follows the repo's own policy in
`src/core/startup_validator._check_cors_origins()` — `"*"` is an error in
production — with one addition: it is an error in *every* environment when the
caller sets `allow_credentials=True`. That combination has no valid
configuration. Starlette does not reject it; it responds by echoing the
request's own `Origin` header back, so the browser's wildcard-plus-credentials
restriction never engages and every origin on the internet gets credentialed
access. A wildcard without credentials is merely permissive, so outside
production that stays a warning.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_ORIGIN = "http://localhost:3000"
ORIGIN_ENV_VARS = ("CORS_ORIGINS", "ALLOWED_ORIGINS")


def _parse(raw: str) -> list[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def resolve_cors_origins(service: str, *, allow_credentials: bool = False) -> list[str]:
    """Return the CORS allow-list for ``service``.

    Args:
        service: Name used in log and error messages, e.g. ``"Nexus"``.
        allow_credentials: Whether the caller passes ``allow_credentials=True`` to
            ``CORSMiddleware``. When true, a wildcard origin is rejected in every
            environment rather than only in production.

    Raises:
        RuntimeError: A wildcard origin was configured somewhere it is not allowed.
    """
    for var in ORIGIN_ENV_VARS:
        origins = _parse(os.getenv(var, ""))
        if not origins:
            continue
        if "*" in origins:
            _reject_or_warn(service, var, allow_credentials)
            # Kept only where it was downgraded to a warning; _reject_or_warn
            # raises in every other case.
            return origins
        return origins
    return [DEFAULT_ORIGIN]


def _reject_or_warn(service: str, var: str, allow_credentials: bool) -> None:
    if allow_credentials:
        raise RuntimeError(
            f"{var} contains '*', but {service} sets allow_credentials=True. "
            "Starlette answers that combination by echoing the request's Origin "
            "header back, so every origin gets credentialed access. Set explicit "
            "origins."
        )
    if os.getenv("ENVIRONMENT", "").strip().lower() == "production":
        raise RuntimeError(
            f"{var} contains '*'. {service} must be given specific origins in "
            "production — wildcard CORS is not acceptable."
        )
    logger.warning(
        "%s contains '*' — %s will accept cross-origin requests from anywhere. "
        "This is refused when ENVIRONMENT=production.",
        var,
        service,
    )
