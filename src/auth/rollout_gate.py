"""Staged-rollout gate for public registration.

The platform launches in stages — owner testing, a private beta of under ten
testers, an extended beta of around twenty, then public — and the only thing
standing between a stage and the whole internet is `/auth/register`. This
module is that gate.

Configuration (environment):

    ROLLOUT_STAGE        owner | private_beta | extended_beta | public
    ROLLOUT_INVITE_CODE  optional shared invite code required to register in
                         any non-public stage when set

Stage semantics:

    owner          registration for the owner's own test accounts (cap 2)
    private_beta   first tester wave (cap 10)
    extended_beta  second tester wave (cap 25 — ~20 testers with headroom)
    public         open registration, no cap, invite code ignored

Fail-closed rule: when ``ENVIRONMENT`` is ``production`` and ``ROLLOUT_STAGE``
is unset or unrecognised, the gate resolves to ``owner`` — a production deploy
that forgot to configure its stage must not silently run open registration.
Everywhere else (dev, CI, tests) the default is ``public`` so local flows and
the existing test suite are untouched.

Advancing a stage is one command, no deploy:

    fly secrets set ROLLOUT_STAGE=private_beta --app tranc3-backend

`scripts/cloud_smoke_check.py --expect-stage <stage>` verifies the live gate
after each change.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Ordered rollout stages and their registration caps (None = uncapped).
STAGE_CAPS: dict[str, Optional[int]] = {
    "owner": 2,
    "private_beta": 10,
    "extended_beta": 25,
    "public": None,
}


def current_stage() -> str:
    """Resolve the active rollout stage from the environment.

    Unset/unknown values fail closed to "owner" in production and open to
    "public" everywhere else — see module docstring.
    """
    raw = os.getenv("ROLLOUT_STAGE", "").strip().lower()
    if raw in STAGE_CAPS:
        return raw
    in_production = os.getenv("ENVIRONMENT", "").strip().lower() == "production"
    if raw:
        logger.warning(
            "ROLLOUT_STAGE=%r is not a known stage (%s) — treating as %s",
            raw,
            "/".join(STAGE_CAPS),
            "owner (fail closed)" if in_production else "public",
        )
    return "owner" if in_production else "public"


@dataclass
class GateDecision:
    allowed: bool
    stage: str
    reason: str


def check_registration(
    invite_code: Optional[str],
    user_count: Optional[int],
) -> GateDecision:
    """Decide whether a registration attempt may proceed at the current stage.

    ``user_count`` is the number of existing accounts (None = unknown). An
    unknown count in a capped stage denies — the cap cannot be enforced, so
    the gate must not wave people through.
    """
    stage = current_stage()
    cap = STAGE_CAPS[stage]

    if stage == "public":
        return GateDecision(True, stage, "public stage — open registration")

    configured_code = os.getenv("ROLLOUT_INVITE_CODE", "")
    if configured_code:
        if not invite_code or not secrets.compare_digest(invite_code, configured_code):
            return GateDecision(
                False,
                stage,
                f"registration is invite-only during the {stage} stage — "
                "a valid invite_code is required",
            )

    if user_count is None:
        return GateDecision(
            False,
            stage,
            f"cannot verify the {stage} stage capacity — registration is temporarily unavailable",
        )
    if cap is not None and user_count >= cap:
        return GateDecision(
            False,
            stage,
            f"the {stage} stage is at capacity ({cap} accounts) — "
            "registration reopens at the next rollout stage",
        )

    return GateDecision(True, stage, f"{stage} stage — {user_count}/{cap} accounts used")
