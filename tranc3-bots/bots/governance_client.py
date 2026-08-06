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
# to the main backend's availability. A network/timeout error talking to the
# governance endpoint fails OPEN (logged, dispatch proceeds) — that is an
# infrastructure availability problem, not a policy signal. An actual 'rejected'
# or 'halted' FSM decision fails CLOSED (raises GovernanceBlockedError).
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_GATE_ENABLED = os.getenv("GOVERNANCE_GATE_ENABLED", "false").strip().lower() == "true"
_BACKEND_URL = os.getenv("TRANC3_ENGINE_URL", "")
_INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")
_TIMEOUT = float(os.getenv("GOVERNANCE_GATE_TIMEOUT", "5.0"))

_BLOCKED_STATES = frozenset({"rejected", "halted"})


class GovernanceBlockedError(RuntimeError):
    """The escalation FSM resolved this action to 'rejected' or 'halted'."""


def gate_enabled() -> bool:
    return _GATE_ENABLED


async def check_action(bot_type: str, requestor: str) -> Optional[Dict[str, Any]]:
    """Submit a Tier 5 ActionRequest for `bot_type` to the main backend's escalation FSM.

    Returns the resolved escalation record dict, or None when the gate is disabled,
    unconfigured, or the governance call itself failed (see module docstring for why
    that fails open rather than closed). Raises GovernanceBlockedError when the FSM
    resolved to 'rejected' or 'halted'.
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

    try:
        import httpx

        url = _BACKEND_URL.rstrip("/") + "/governance/actions"
        headers = {"X-Internal-Secret": _INTERNAL_SECRET} if _INTERNAL_SECRET else {}
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
            resp.raise_for_status()
            record = resp.json()
    except Exception as exc:  # network error, timeout, non-2xx, bad JSON — infra, not policy
        logger.warning(
            "Governance gate call failed for bot_type=%s (%s) — failing open", bot_type, exc
        )
        return None

    if record.get("state") in _BLOCKED_STATES:
        raise GovernanceBlockedError(
            f"Bot dispatch for {bot_type!r} blocked by governance "
            f"({record.get('state')}): {record.get('reason') or ''}".strip()
        )
    return record
