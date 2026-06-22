"""Cryptex / The Ice Box — Pydantic models"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ScanEngine(str, Enum):
    wazuh = "wazuh"
    misp = "misp"
    openvas = "openvas"
    clamav = "clamav"
    yara = "yara"
    suricata = "suricata"
    semgrep = "semgrep"
    offline = "offline"


class ThreatSeverity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"
    unknown = "unknown"


class ScanType(str, Enum):
    file = "file"
    network = "network"
    vulnerability = "vulnerability"
    threat_intel = "threat_intel"
    sast = "sast"
    ioc = "ioc"


class ScanStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ScanRequest(BaseModel):
    scan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scan_type: ScanType
    target: str  # file path, IP, URL, or code snippet
    metadata: Dict[str, Any] = Field(default_factory=dict)
    preferred_engine: Optional[ScanEngine] = None


class ThreatIndicator(BaseModel):
    indicator_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ioc_type: str  # ip, domain, hash, url, email
    value: str
    severity: ThreatSeverity = ThreatSeverity.unknown
    source: str = ""
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScanResult(BaseModel):
    scan_id: str
    engine_used: Optional[str] = None
    status: ScanStatus = ScanStatus.pending
    threat_found: bool = False
    severity: ThreatSeverity = ThreatSeverity.unknown
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    raw_output: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class EngineStatus(BaseModel):
    engine: str
    healthy: bool
    pheromone: float
    requests_in_window: int
    threshold: int
    blocked: bool
