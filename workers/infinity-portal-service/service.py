"""
Service — Infinity Portal Service
===================================
Business logic: InfinityGate routing, auth-service client,
and database helper functions.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from models import GateRoutingResponse

from config import AUTH_SERVICE_URL
from database import db
from Dimensional.infinity.nomenclature import (
    GATE_ROUTING,
    INFINITY_LOCATIONS,
    InfinityLocation,
    InfinityRole,
    Tier,
    TransferSystem,
)

# ---------------------------------------------------------------------------
# Infinity Gate
# ---------------------------------------------------------------------------


class InfinityGate:
    """The Infinity Gate — role-based post-authentication routing.

    After a user authenticates at the Infinity Portal, the Gate determines
    which Infinity Location they should be routed to based on their role.

    Routing Rules (from nomenclature):
        admin      → Infinity-Admin (management OS)
        user       → Arcadia (user space)
        developer  → The Citadel (developer space)
        devops     → The Citadel (developer space)
        prime      → Infinity-Admin (domain management)
        ai         → Infinity (central hub)
        agent      → Infinity (central hub)
        bot        → Infinity (central hub)
        service    → Infinity (central hub)
    """

    # Extended routing beyond the base GATE_ROUTING from nomenclature
    EXTENDED_ROUTING: dict[str, InfinityLocation] = {
        **GATE_ROUTING,
        "prime": InfinityLocation.ADMIN,
        "ai": InfinityLocation.CENTRAL,
        "agent": InfinityLocation.CENTRAL,
        "bot": InfinityLocation.CENTRAL,
        "service": InfinityLocation.CENTRAL,
    }

    # Role to Tier mapping
    ROLE_TIER_MAP: dict[str, Tier] = {
        "admin": Tier.HUMAN,
        "user": Tier.HUMAN,
        "developer": Tier.HUMAN,
        "devops": Tier.HUMAN,
        "prime": Tier.PRIME,
        "ai": Tier.AI,
        "agent": Tier.AGENT,
        "bot": Tier.BOT,
        "service": Tier.BOT,
    }

    # Role to InfinityRole mapping
    ROLE_INFINITY_ROLE_MAP: dict[str, InfinityRole] = {
        "admin": InfinityRole.ADMIN,
        "user": InfinityRole.USER,
        "developer": InfinityRole.USER,
        "devops": InfinityRole.USER,
        "prime": InfinityRole.PRIME,
        "ai": InfinityRole.AI,
        "agent": InfinityRole.AGENT,
        "bot": InfinityRole.BOT,
        "service": InfinityRole.SERVICE,
    }

    @classmethod
    def route(cls, role: str) -> GateRoutingResponse:
        """Route a user based on their role to the appropriate Infinity Location.

        This is the core of the Infinity Gate — after Portal authentication,
        the user is routed through the Gate to their destination.
        """
        role_lower = role.lower().strip()
        destination = cls.EXTENDED_ROUTING.get(role_lower, InfinityLocation.ARCADIA)
        location_info = INFINITY_LOCATIONS.get(destination, {})
        tier = cls.ROLE_TIER_MAP.get(role_lower, Tier.HUMAN)
        infinity_role = cls.ROLE_INFINITY_ROLE_MAP.get(role_lower, InfinityRole.USER)

        # Determine transfer system based on destination
        if destination in (
            InfinityLocation.ADMIN,
            InfinityLocation.ARCADIA,
            InfinityLocation.CITADEL,
        ):
            transfer = TransferSystem.BRIDGE
        elif destination in (InfinityLocation.CENTRAL,):
            transfer = TransferSystem.NEXUS
        else:
            transfer = TransferSystem.BRIDGE

        # Build routing URL based on destination
        routing_urls = {
            InfinityLocation.PORTAL: "/infinity-portal",
            InfinityLocation.GATE: "/infinity-gate",
            InfinityLocation.CENTRAL: "/infinity",
            InfinityLocation.ONE: "/infinity-one",
            InfinityLocation.ADMIN: "/infinity-admin",
            InfinityLocation.BRIDGE: "/infinity-bridge",
            InfinityLocation.ARCADIA: "/arcadia",
            InfinityLocation.CITADEL: "/the-citadel",
            InfinityLocation.SENTINEL: "/sentinel-station",
        }

        return GateRoutingResponse(
            user_id="",  # Filled by caller
            username="",  # Filled by caller
            role=role_lower,
            tier=tier.value,
            infinity_role=infinity_role.value,
            routed_to=destination.value,
            routing_url=routing_urls.get(destination, "/arcadia"),
            location_name=location_info.get("name", destination.value),
            location_purpose=location_info.get("purpose", ""),
            transfer_system=transfer.value,
        )


# Module-level gate singleton
gate = InfinityGate()


# ---------------------------------------------------------------------------
# Auth Service Client
# ---------------------------------------------------------------------------


async def call_auth_service(method: str, path: str, json_data: dict | None = None) -> dict:
    """Call the Infinity Auth service for authentication operations."""
    url = f"{AUTH_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if method == "POST":
                response = await client.post(url, json=json_data)
            elif method == "GET":
                response = await client.get(url)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if response.status_code >= 400:
                try:
                    error_detail = response.json().get("detail", response.text)
                except Exception:
                    error_detail = response.text
                raise HTTPException(status_code=response.status_code, detail=error_detail)

            return response.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Infinity Auth service unavailable. Please try again later.",
        ) from None
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Infinity Auth service timeout. Please try again later.",
        ) from None


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _log_portal_event(
    event_type: str,
    user_id: str | None = None,
    username: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    payload: dict | None = None,
) -> None:
    """Log a portal event to the database."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO portal_events (id, event_type, user_id, username, ip_address, user_agent, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            uuid.uuid4().hex[:16],
            event_type,
            user_id,
            username,
            ip_address,
            user_agent,
            json.dumps(payload) if payload else "{}",
            now,
        ),
    )
    db.commit()


def _create_portal_session(
    user_id: str,
    username: str,
    role: str,
    tier: Tier,
    infinity_role: InfinityRole,
    routed_to: str,
    access_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Create a portal session in the database."""
    session_id = uuid.uuid4().hex[:24]
    now = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

    db.execute(
        """INSERT INTO portal_sessions
           (session_id, user_id, username, role, tier, infinity_role, routed_to,
            access_token, created_at, expires_at, ip_address, user_agent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            user_id,
            username,
            role,
            tier.value,
            infinity_role.value,
            routed_to,
            access_token,
            now,
            expires_at,
            ip_address,
            user_agent,
        ),
    )
    db.commit()
    return session_id


def _log_gate_routing(
    user_id: str,
    username: str,
    role: str,
    from_location: str,
    to_location: str,
    transfer_system: str = "bridge",
) -> None:
    """Log a gate routing event."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT INTO gate_routing_log
           (id, user_id, username, role, from_location, to_location, routed_at, transfer_system)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            uuid.uuid4().hex[:16],
            user_id,
            username,
            role,
            from_location,
            to_location,
            now,
            transfer_system,
        ),
    )
    db.commit()
