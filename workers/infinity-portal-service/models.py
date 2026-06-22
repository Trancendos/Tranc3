"""
Models — Infinity Portal Service
==================================
All Pydantic request/response models for the Infinity Portal.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class PortalLogin(BaseModel):
    """Login request for the Infinity Portal."""

    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = None
    redirect_to: str | None = None  # Optional post-login redirect


class PortalRegister(BaseModel):
    """Registration request for the Infinity Portal."""

    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=100)
    role: str = Field(default="user")  # user, admin, developer, devops


class PortalSessionResponse(BaseModel):
    """Response after successful login/registration."""

    session_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    username: str
    role: str
    tier: int
    infinity_role: str
    routed_to: str  # The Infinity Gate routing destination
    routing_url: str  # URL for the routed destination
    transfer_system: str  # bridge, nexus, hive


class GateRoutingResponse(BaseModel):
    """Response from the Infinity Gate routing."""

    user_id: str
    username: str
    role: str
    tier: int
    infinity_role: str
    routed_to: str
    routing_url: str
    location_name: str
    location_purpose: str
    transfer_system: str
    pillar: str | None = None


class PortalStatusResponse(BaseModel):
    """Current portal status and configuration."""

    status: str
    portal_name: str
    ecosystem_name: str
    universe_name: str
    locations: dict
    gate_routing: dict
    transfer_systems: dict
    active_sessions: int
    uptime: float
