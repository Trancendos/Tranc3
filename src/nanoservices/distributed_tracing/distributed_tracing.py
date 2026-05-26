"""Distributed Tracing Service — Phase 12

Cross-nanoservice request tracing with span propagation,
service graph construction, and latency analysis.
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SpanKind(Enum):
    INTERNAL = "internal"
    CLIENT = "client"
    SERVER = "server"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus(Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class SpanContext:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    baggage: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "baggage": self.baggage,
        }


@dataclass
class Span:
    context: SpanContext
    name: str
    kind: SpanKind = SpanKind.INTERNAL
    status: SpanStatus = SpanStatus.OK
    service_name: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    links: List[SpanContext] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    @property
    def trace_id(self) -> str:
        return self.context.trace_id

    @property
    def span_id(self) -> str:
        return self.context.span_id

    def finish(self, status: SpanStatus = SpanStatus.OK) -> None:
        self.end_time = time.time()
        self.status = status

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        self.events.append({"name": name, "timestamp": time.time(), "attributes": attributes or {}})

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value


@dataclass
class Trace:
    trace_id: str
    spans: List[Span] = field(default_factory=list)
    root_span: Optional[Span] = None
    service_count: int = 0

    def add_span(self, span: Span) -> None:
        self.spans.append(span)
        if span.context.parent_span_id is None:
            self.root_span = span
        services = set(s.service_name for s in self.spans if s.service_name)
        self.service_count = len(services)

    @property
    def duration_ms(self) -> float:
        if not self.spans:
            return 0.0
        start = min(s.start_time for s in self.spans)
        end = max(s.end_time or s.start_time for s in self.spans)
        return (end - start) * 1000

    @property
    def error_count(self) -> int:
        return sum(1 for s in self.spans if s.status == SpanStatus.ERROR)

    def get_service_graph(self) -> Dict[str, List[str]]:
        """Build a directed graph of service dependencies."""
        graph: Dict[str, List[str]] = defaultdict(list)
        span_by_id = {s.context.span_id: s for s in self.spans}
        for span in self.spans:
            if span.context.parent_span_id and span.context.parent_span_id in span_by_id:
                parent = span_by_id[span.context.parent_span_id]
                if (
                    parent.service_name
                    and span.service_name
                    and parent.service_name != span.service_name
                ):
                    if span.service_name not in graph[parent.service_name]:
                        graph[parent.service_name].append(span.service_name)
        return dict(graph)


class TraceCollector:
    """Collects and stores traces for analysis."""

    def __init__(self, max_traces: int = 10000, sample_rate: float = 1.0):
        self._traces: Dict[str, Trace] = {}
        self._max_traces = max_traces
        self._sample_rate = sample_rate
        self._total_received = 0
        self._total_sampled = 0

    def should_sample(self) -> bool:
        return random.random() < self._sample_rate

    def add_trace(self, trace: Trace) -> bool:
        self._total_received += 1
        if not self.should_sample():
            return False
        self._total_sampled += 1
        self._traces[trace.trace_id] = trace
        if len(self._traces) > self._max_traces:
            oldest_key = min(
                self._traces.keys(),
                key=lambda k: (
                    min(s.start_time for s in self._traces[k].spans) if self._traces[k].spans else 0
                ),
            )
            del self._traces[oldest_key]
        return True

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        return self._traces.get(trace_id)

    def get_recent_traces(self, limit: int = 50) -> List[Trace]:
        traces = sorted(
            self._traces.values(),
            key=lambda t: min(s.start_time for s in t.spans) if t.spans else 0,
            reverse=True,
        )
        return traces[:limit]

    def get_error_traces(self, limit: int = 50) -> List[Trace]:
        return [t for t in self._traces.values() if t.error_count > 0][:limit]

    def get_slow_traces(self, threshold_ms: float = 1000.0, limit: int = 50) -> List[Trace]:
        return [t for t in self._traces.values() if t.duration_ms > threshold_ms][:limit]


class Tracer:
    """Creates and manages spans for distributed tracing."""

    def __init__(self, service_name: str, collector: TraceCollector):
        self._service_name = service_name
        self._collector = collector
        self._active_spans: Dict[str, Span] = {}
        self._current_trace_id: Optional[str] = None

    def start_trace(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
        trace_id = uuid.uuid4().hex[:16]
        span_id = uuid.uuid4().hex[:12]
        context = SpanContext(trace_id=trace_id, span_id=span_id)
        span = Span(
            context=context,
            name=name,
            kind=SpanKind.SERVER,
            service_name=self._service_name,
            attributes=attributes or {},
        )
        self._active_spans[span_id] = span
        self._current_trace_id = trace_id
        return span

    def start_span(
        self,
        name: str,
        parent: Optional[Span] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Span:
        trace_id = (
            parent.context.trace_id if parent else (self._current_trace_id or uuid.uuid4().hex[:16])
        )
        parent_id = parent.context.span_id if parent else None
        span_id = uuid.uuid4().hex[:12]
        context = SpanContext(trace_id=trace_id, span_id=span_id, parent_span_id=parent_id)
        span = Span(
            context=context,
            name=name,
            kind=kind,
            service_name=self._service_name,
            attributes=attributes or {},
        )
        self._active_spans[span_id] = span
        return span

    def finish_span(self, span: Span, status: SpanStatus = SpanStatus.OK) -> None:
        span.finish(status)
        if span.context.span_id in self._active_spans:
            del self._active_spans[span.context.span_id]

        # Add to trace
        trace = self._collector.get_trace(span.trace_id)
        if trace is None:
            trace = Trace(trace_id=span.trace_id)
            self._collector.add_trace(trace)
        trace.add_span(span)

    def inject_context(self, span: Span) -> Dict[str, str]:
        return {
            "trace-id": span.context.trace_id,
            "span-id": span.context.span_id,
            "parent-span-id": span.context.parent_span_id or "",
        }

    def extract_context(self, headers: Dict[str, str]) -> Optional[SpanContext]:
        trace_id = headers.get("trace-id")
        span_id = headers.get("span-id")
        if not trace_id:
            return None
        parent_id = headers.get("parent-span-id") or None
        return SpanContext(
            trace_id=trace_id, span_id=span_id or uuid.uuid4().hex[:12], parent_span_id=parent_id
        )


class LatencyAnalyzer:
    """Analyzes latency patterns across services and endpoints."""

    def __init__(self, collector: TraceCollector):
        self._collector = collector

    def get_service_latencies(self) -> Dict[str, List[float]]:
        latencies: Dict[str, List[float]] = defaultdict(list)
        for trace in self._collector._traces.values():
            for span in trace.spans:
                if span.service_name and span.duration_ms > 0:
                    latencies[span.service_name].append(span.duration_ms)
        return dict(latencies)

    def get_endpoint_latencies(self) -> Dict[str, List[float]]:
        latencies: Dict[str, List[float]] = defaultdict(list)
        for trace in self._collector._traces.values():
            for span in trace.spans:
                if span.name and span.duration_ms > 0:
                    key = f"{span.service_name}:{span.name}"
                    latencies[key].append(span.duration_ms)
        return dict(latencies)

    def get_p50_p95_p99(self, service_name: str) -> Dict[str, float]:
        latencies = self.get_service_latencies().get(service_name, [])
        if not latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        sorted_l = sorted(latencies)
        return {
            "p50": sorted_l[int(len(sorted_l) * 0.50)],
            "p95": sorted_l[int(len(sorted_l) * 0.95)],
            "p99": sorted_l[min(len(sorted_l) - 1, int(len(sorted_l) * 0.99))],
        }

    def get_service_dependency_map(self) -> Dict[str, Dict[str, int]]:
        deps: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for trace in self._collector._traces.values():
            graph = trace.get_service_graph()
            for source, targets in graph.items():
                for target in targets:
                    deps[source][target] += 1
        return {k: dict(v) for k, v in deps.items()}


class DistributedTracingService:
    """Main service: distributed tracing infrastructure."""

    def __init__(self, sample_rate: float = 1.0, max_traces: int = 10000):
        self._collector = TraceCollector(max_traces=max_traces, sample_rate=sample_rate)
        self._tracers: Dict[str, Tracer] = {}
        self._analyzer = LatencyAnalyzer(self._collector)

    def initialize(self) -> None:
        logger.info(
            "DistributedTracingService initialized (sample_rate=%.2f)", self._collector._sample_rate
        )

    def get_tracer(self, service_name: str) -> Tracer:
        if service_name not in self._tracers:
            self._tracers[service_name] = Tracer(service_name, self._collector)
        return self._tracers[service_name]

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        return self._collector.get_trace(trace_id)

    def get_recent_traces(self, limit: int = 50) -> List[Trace]:
        return self._collector.get_recent_traces(limit)

    def get_error_traces(self, limit: int = 50) -> List[Trace]:
        return self._collector.get_error_traces(limit)

    def get_slow_traces(self, threshold_ms: float = 1000.0, limit: int = 50) -> List[Trace]:
        return self._collector.get_slow_traces(threshold_ms, limit)

    def get_latency_stats(self, service_name: str) -> Dict[str, float]:
        return self._analyzer.get_p50_p95_p99(service_name)

    def get_service_dependencies(self) -> Dict[str, Dict[str, int]]:
        return self._analyzer.get_service_dependency_map()
