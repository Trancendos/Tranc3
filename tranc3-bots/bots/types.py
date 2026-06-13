# bots/types.py — shared data types for TRANC3 bots
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class BotType(str, Enum):
    # ── Inference (proxied to Tranc3 engine) ──────────────────────────────────
    GENERATE = "generate"
    EMBED = "embed"
    EMOTION = "emotion"
    TOKENIZE = "tokenize"
    CONSCIOUSNESS = "consciousness"
    PERSONALITY = "personality"
    PREDICT = "predict"
    # ── Utility (standalone — no ML needed) ───────────────────────────────────
    CODE = "code"
    MEMORY = "memory"
    MONITOR = "monitor"
    SEARCH = "search"
    SUMMARISE = "summarise"


@dataclass
class JobSpec:
    bot_type: str
    payload: Dict[str, Any]
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 5
    created_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "JobSpec":
        return cls(**json.loads(raw))


@dataclass
class JobResult:
    job_id: str
    status: str  # JobStatus value
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    bot_id: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "JobResult":
        return cls(**json.loads(raw))
