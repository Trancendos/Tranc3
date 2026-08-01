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

Scope — this gates the `/auth/register` in `api.py` (the `tranc3-backend` Fly
app), which is the only registration surface the cloud-only deployment exposes.
`workers/infinity-auth/router.py` has its own ungated `/auth/register`; it is a
compose service and is **not** deployed in cloud-only mode, so it is unreachable
today. Bringing the Citadel stack up would expose an ungated registration path —
apply this gate there (or route `/auth/*` to the gated app) before doing so.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
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


# Failed invite attempts are throttled because /auth/register is unauthenticated
# and this app registers no rate-limiting middleware — without this, the invite
# code can be guessed as fast as the network allows.
#
# The window is deliberately generous: a wave of at most 25 invited testers
# should never approach it, while it caps a guesser at a rate that makes even a
# weak code impractical to brute-force. The trade-off is that a determined
# attacker can burn the budget and briefly block legitimate registrations; for a
# closed beta that is the better failure (nobody registers) than the alternative
# (anybody registers). It is per-process, so it weakens as instances scale — the
# code's entropy is the real defence, which is why _warn_on_weak_code exists.
_FAILED_INVITE_WINDOW_SECONDS = 60
_MAX_FAILED_INVITES_PER_WINDOW = 20
_failed_invites: list[float] = []


def _record_failed_invite() -> None:
    now = time.monotonic()
    cutoff = now - _FAILED_INVITE_WINDOW_SECONDS
    _failed_invites[:] = [t for t in _failed_invites if t > cutoff]
    _failed_invites.append(now)


def _invite_attempts_exhausted() -> bool:
    cutoff = time.monotonic() - _FAILED_INVITE_WINDOW_SECONDS
    _failed_invites[:] = [t for t in _failed_invites if t > cutoff]
    return len(_failed_invites) >= _MAX_FAILED_INVITES_PER_WINDOW


_MIN_INVITE_CODE_LENGTH = 12
_warned_weak_code = False


def _warn_on_weak_code(code: str) -> None:
    """Log once if the configured invite code is short enough to guess."""
    global _warned_weak_code
    if not _warned_weak_code and len(code) < _MIN_INVITE_CODE_LENGTH:
        _warned_weak_code = True
        logger.warning(
            "ROLLOUT_INVITE_CODE is %d characters; use at least %d "
            "(secrets.token_urlsafe(12)). Throttling slows guessing but entropy "
            "is what prevents it.",
            len(code),
            _MIN_INVITE_CODE_LENGTH,
        )


def needs_user_count() -> bool:
    """True when the active stage is capped and therefore needs a user count.

    Lets the caller skip a per-request DB COUNT in the public stage, where the
    gate allows unconditionally — /auth/register is unauthenticated, so that
    query would otherwise be free load for anyone who finds the endpoint.
    """
    return STAGE_CAPS[current_stage()] is not None


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
        _warn_on_weak_code(configured_code)
        # Compare BEFORE consulting the throttle. Checking exhaustion first would
        # let anyone who can burn 20 guesses a minute lock out every legitimately
        # invited tester — turning a brute-force defence into a denial of service
        # against the beta itself. A correct code is always honoured.
        #
        # Compare as bytes: compare_digest() on str raises TypeError for any
        # non-ASCII character, and invite_code arrives straight from JSON. A
        # tester pasting a smart quote would get a 500, not a clean refusal.
        code_matches = bool(invite_code) and secrets.compare_digest(
            invite_code.encode("utf-8"), configured_code.encode("utf-8")
        )
        if not code_matches:
            if invite_code:
                # Only a *wrong* code counts as a guess. A missing one is someone
                # who simply wasn't invited (or an unauthenticated probe), and
                # charging those against the budget would let ordinary traffic
                # exhaust it.
                _record_failed_invite()
            if _invite_attempts_exhausted():
                return GateDecision(
                    False,
                    stage,
                    "too many invalid invite codes — registration is paused "
                    "briefly, please retry shortly",
                )
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
