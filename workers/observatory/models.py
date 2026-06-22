"""Observatory data models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BackendType(str, Enum):
    signoz = "signoz"
    jaeger = "jaeger"
    tempo = "tempo"
    victoriametrics = "victoriametrics"
    prometheus = "prometheus"
    loki = "loki"
    netdata = "netdata"


class SignalType(str, Enum):
    traces = "traces"
    metrics = "metrics"
    logs = "logs"
    node = "node"


class BackendStatus(BaseModel):
    backend: BackendType
    url: str
    healthy: bool
    pheromone: float = Field(ge=0.0, le=1.0)
    requests_in_window: int
    threshold: int
    blocked: bool
    latency_ms: Optional[float] = None
    last_error: Optional[str] = None


class TraceQuery(BaseModel):
    service: Optional[str] = None
    operation: Optional[str] = None
    trace_id: Optional[str] = None
    min_duration_ms: Optional[int] = None
    limit: int = Field(default=20, ge=1, le=200)
    lookback_hours: int = Field(default=1, ge=1, le=168)


class MetricsQuery(BaseModel):
    promql: str
    start: Optional[str] = None
    end: Optional[str] = None
    step: str = "60s"


class LogQuery(BaseModel):
    logql: str
    start: Optional[str] = None
    end: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=5000)
    direction: str = "backward"


class NodeMetricSummary(BaseModel):
    cpu_usage_pct: Optional[float] = None
    ram_used_mb: Optional[float] = None
    ram_total_mb: Optional[float] = None
    disk_io_read_kbs: Optional[float] = None
    disk_io_write_kbs: Optional[float] = None
    net_in_kbs: Optional[float] = None
    net_out_kbs: Optional[float] = None
    uptime_seconds: Optional[float] = None
    source: str = "netdata"


class ObservatoryHealth(BaseModel):
    worker: str
    status: str
    backends: List[BackendStatus]
    active_backends: Dict[SignalType, str]
    timestamp: str


class QueryResult(BaseModel):
    signal: SignalType
    backend_used: str
    data: Any
    latency_ms: float
    fallbacks_attempted: int = 0
