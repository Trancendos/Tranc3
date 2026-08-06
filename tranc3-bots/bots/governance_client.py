# bots/governance_client.py — AI Governance Constitution Phase 3
# (docs/governance/AI-GOVERNANCE-CONSTITUTION.md §3, main repo Trancendos/Tranc3).
#
# tranc3-bots is a separately deployed package — its own pyproject.toml, its own
# Dockerfile (which does not COPY the main repo's src/ tree), no jsonschema
# dependency — so it cannot import src.compliance.escalation_fsm directly the way
# src/agents/orchestrator.py does. Instead it calls the main backend's
# POST /governance/actions route over HTTP (src/compliance/governance_routes.py),
# reusing TRANC3_ENGINE_URL — the env var this package already uses to reach the
# main backend for inference bot dispatch (bots/handlers.py).
#
# Gated by GOVERNANCE_GATE_ENABLED, mirroring cab_gate.py's CAB_GATE_ENABLED
# precedent, so this can ship without unconditionally coupling every bot dispatch
# to the main backend's availability. The fail-open/fail-closed line is drawn at
# "did we get a response at all", not at status code: a network/timeout error
# (no response — the backend is genuinely unreachable) fails OPEN, since that's
# an infrastructure availability problem, not a policy signal. Any actual HTTP
# response — 2xx with bad/non-object JSON, 401/403, other 4xx, or 5xx — means the
# backend IS reachable and something else is wrong (misconfiguration, backend bug,
# overload), which fails CLOSED. Treating a reachable-but-broken backend the same
# as an unreachable one would mean governance silently stops being enforced the
# moment the governance service itself has a bad day — indistinguishable from it
# never being enforced at all.
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_GATE_ENABLED = os.getenv("GOVERNANCE_GATE_ENABLED", "false").strip().lower() == "true"
_BACKEND_URL = os.getenv("TRANC3_ENGINE_URL", "")
_INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")

try:
    _TIMEOUT = float(os.getenv("GOVERNANCE_GATE_TIMEOUT", "5.0"))
except (TypeError, ValueError):
    # A typo'd or empty override must not prevent the whole package from
    # importing, even when the gate is disabled — fall back to the default.
    logger.warning(
        "GOVERNANCE_GATE_TIMEOUT=%r is not a valid float — using the 5.0s default",
        os.getenv("GOVERNANCE_GATE_TIMEOUT"),
    )
    _TIMEOUT = 5.0

_BLOCKED_STATES = frozenset({"rejected", "frozen", "halted"})


class GovernanceBlockedError(RuntimeError):
    """The escalation FSM resolved this action to a blocking state, or the
    governance call couldn't be trusted (bad response, auth failure, etc.) —
    see module docstring for the fail-open/fail-closed split."""


async def check_action(bot_type: str, requestor: str) -> Optional[Dict[str, Any]]:
    """Submit a Tier 5 ActionRequest for `bot_type` to the main backend's escalation FSM.

    Returns the resolved escalation record dict, or None when the gate is disabled
    or unconfigured. Raises GovernanceBlockedError for every other outcome except a
    genuine network/timeout failure — see module docstring for the fail-open (no
    response) vs. fail-closed (got a response, but it's not usable) split.
    """
    if not _GATE_ENABLED:
        return None
    if not _BACKEND_URL:
        logger.warning(
            "GOVERNANCE_GATE_ENABLED=true but TRANC3_ENGINE_URL is unset — skipping "
            "governance gate for bot_type=%s",
            bot_type,
        )
        return None

    import httpx

    url = _BACKEND_URL.rstrip("/") + "/governance/actions"
    headers = {"X-Internal-Secret": _INTERNAL_SECRET} if _INTERNAL_SECRET else {}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                json={
                    "tier": 5,
                    "domain": "unassigned",
                    "action": bot_type,
                    "requestor": requestor,
                },
                headers=headers,
            )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        # No response at all — network unreachable / connection refused / timed
        # out. A genuine infra availability problem, not a policy signal. Fail open.
        logger.warning(
            "Governance gate call failed for bot_type=%s (%s) — failing open", bot_type, exc
        )
        return None

    # Everything past this point means the backend responded — fail closed on
    # anything that isn't a clean, usable 'approved'-or-otherwise decision.
    if resp.status_code != 200:
        raise GovernanceBlockedError(
            f"Governance gate call for bot_type={bot_type!r} got HTTP {resp.status_code} "
            "from a reachable backend — treated as a block, not an outage, so a "
            "misconfigured secret or a struggling governance service can't silently "
            "disable enforcement"
        )

    try:
        record = resp.json()
    except ValueError as exc:
        raise GovernanceBlockedError(
            f"Governance gate response for bot_type={bot_type!r} was not valid JSON "
            f"({exc}) — treated as a block, not an outage"
        ) from exc

    if not isinstance(record, dict):
        raise GovernanceBlockedError(
            f"Governance gate response for bot_type={bot_type!r} was not a JSON "
            f"object ({type(record).__name__}) — treated as a block, not an outage"
        )

    if record.get("state") in _BLOCKED_STATES:
        raise GovernanceBlockedError(
            f"Bot dispatch for {bot_type!r} blocked by governance "
            f"({record.get('state')}): {record.get('reason') or ''}".strip()
        )
    return record
