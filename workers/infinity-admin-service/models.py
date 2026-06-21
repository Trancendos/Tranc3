"""
Infinity-Admin Service — Pydantic Models
==========================================
All request/response schemas used by the admin service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigUpdate(BaseModel):
    """Update a system configuration value."""

    value: str
    category: str = Field(default="general")
    description: str | None = None


class FeatureFlagUpdate(BaseModel):
    """Update a feature flag."""

    enabled: bool
    description: str | None = None
    pillar: str | None = None
    tier_required: int | None = None


class AdminActionLog(BaseModel):
    """Log entry for an admin action."""

    id: str
    action_type: str
    actor_id: str
    actor_username: str | None
    target_type: str | None
    target_id: str | None
    details: str | None
    created_at: str


# Phase 25: Entity name management models


class EntityNameUpdate(BaseModel):
    """Request body for renaming any named entity (location, AI, agent, bot)."""

    new_name: str = Field(..., min_length=1, max_length=120, description="The new display name")
    reason: str | None = Field(
        default=None, max_length=500, description="Optional reason for rename"
    )


class EntityOverrideRecord(BaseModel):
    """A single persisted name override."""

    id: str
    location_pid: str
    entity_type: str
    slot: str | None
    original_name: str
    override_name: str
    updated_at: str
    updated_by: str | None


class AgentDetail(BaseModel):
    """Detail for a Tier 4 Agent."""

    code_name: str
    description: str | None
    sid: str | None
    has_override: bool = False


class BotDetail(BaseModel):
    """Detail for a Tier 5 Bot."""

    code_name: str
    description: str | None
    nid: str | None
    has_override: bool = False


class EntityTierUpdate(BaseModel):
    """Payload for assigning a display tier to an entity slot."""

    entity_ref: str
    tier: int
    reason: str | None = None


class EntityDetail(BaseModel):
    """Full detail for a platform entity with overrides applied."""

    pid: str
    location: str
    pillar: str | None
    lead_ai: str | None
    aid: str | None
    primes: list[str]
    agent_alpha: AgentDetail | None
    agent_beta: AgentDetail | None
    bots: dict[str, BotDetail | None]
    worker_port: int | None
    worker_path: str | None
    overrides_applied: dict[str, str]
    platform_available: bool


class OrchestratorRename(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=200)
    reason: str | None = None
