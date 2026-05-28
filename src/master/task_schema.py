"""
src/master/task_schema.py — Pydantic models for YAML/JSON task definitions.

A task definition file looks like:

    name: health-check
    description: Ping every worker and report to The Observatory
    schedule:
      type: interval
      seconds: 60
    steps:
      - bot: monitor
        action: health_check
        params:
          targets: ["all"]
        retry:
          max_attempts: 3
          backoff_seconds: 5
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ScheduleType(str, Enum):
    cron = "cron"
    interval = "interval"
    date = "date"
    once = "once"


class ScheduleConfig(BaseModel):
    type: ScheduleType = ScheduleType.once
    # cron fields
    cron_expression: Optional[str] = Field(None, description="Full cron string (5-part)")
    # interval fields
    seconds: Optional[int] = None
    minutes: Optional[int] = None
    hours: Optional[int] = None
    # date field
    run_date: Optional[str] = Field(None, description="ISO-8601 datetime")
    # timezone
    timezone: str = "UTC"


class RetryPolicy(BaseModel):
    max_attempts: int = Field(3, ge=1, le=10)
    backoff_seconds: float = Field(2.0, ge=0)
    backoff_multiplier: float = Field(2.0, ge=1.0)
    max_backoff_seconds: float = Field(60.0, ge=0)


class TaskStep(BaseModel):
    bot: str = Field(..., description="BotRegistry handler key (e.g. 'monitor', 'search')")
    action: str = Field(..., description="Action name passed as kwarg to the bot")
    params: Dict[str, Any] = Field(default_factory=dict)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)  # type: ignore[arg-type]
    timeout_seconds: float = Field(30.0, ge=1)
    depends_on: List[str] = Field(default_factory=list, description="Step names that must complete first")
    name: Optional[str] = None

    @field_validator("bot")
    @classmethod
    def validate_bot_type(cls, v: str) -> str:
        # Core 12 tranc3-bots types
        _core = {
            "generate", "embed", "emotion", "tokenize", "consciousness",
            "personality", "predict", "code", "memory", "monitor",
            "search", "summarise",
        }
        # AeonMind Tier-5 capabilities (15 types)
        _aeonmind = {
            "aeonmind", "translate", "classify", "extract", "validate",
            "transform", "notify", "log", "cache", "route", "filter",
            "enrich", "summarize", "generic",
        }
        # NanoCodeBot autonomous repair modes (9 FailureModes + root type)
        _nanocode = {
            "nanocode",
            "compliance_metadata_missing", "stale_embedding",
            "free_tier_approaching", "rate_limit_hit", "service_unreachable",
            "config_drift", "memory_leak", "high_error_rate", "dependency_failed",
        }
        valid_bots = _core | _aeonmind | _nanocode
        if v not in valid_bots:
            raise ValueError(f"Unknown bot type '{v}'. Valid: {sorted(valid_bots)}")
        return v


class TaskDefinition(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    version: str = "1.0"
    enabled: bool = True
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)  # type: ignore[arg-type]
    steps: List[TaskStep] = Field(..., min_length=1)
    tags: List[str] = Field(default_factory=list)
    notify_on_failure: bool = True
    notify_on_success: bool = False
    # Ansible playbook to run before steps (optional)
    ansible_playbook: Optional[str] = Field(None, description="Path relative to ansible/ dir")
    ansible_inventory: Optional[str] = Field(None, description="Path relative to ansible/ dir")

    @field_validator("name")
    @classmethod
    def slugify_name(cls, v: str) -> str:
        import re
        return re.sub(r"[^a-z0-9_-]", "-", v.lower()).strip("-")
