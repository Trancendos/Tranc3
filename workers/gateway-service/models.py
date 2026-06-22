"""
models.py — Gateway Service Pydantic schemas
All request/response models for gateway-service.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    source: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TopologySwitch(BaseModel):
    mode: str


class AgentCreate(BaseModel):
    name: str
    capabilities: list[str] = Field(default_factory=list)
    model_binding: str | None = None


class WorkflowCreate(BaseModel):
    name: str
    steps: list[dict[str, Any]]
    step_dependencies: list[list[str]] = Field(default_factory=list)
