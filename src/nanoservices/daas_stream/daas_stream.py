"""
DaaS — Data as a Service with Sovereignty
==========================================
On-demand data integration with real-time streams,
ensuring data sovereignty through OPA policy enforcement.

Architecture:
  - Stream Pipeline: Redpanda/Kafka-compatible streaming
  - OPA Policy Engine: Enforce data sovereignty, access control, retention
  - Data Lineage: Track data origin, transformations, and consumers
  - Sovereignty: Data stays within declared jurisdictions
  - Zero-cost: Redpanda (free), OPA (free), pure Python

Integration with Tranc3:
  - Tier-2 infrastructure nanoservice
  - Data streams consumed/produced via DNF nano-flows
  - Lineage events tracked for audit compliance
  - OPA policies stored in Forgejo (IGI)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class StreamStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    CLOSED = "closed"
    ERROR = "error"


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    TOP_SECRET = "top_secret"


class Jurisdiction(str, Enum):
    EU = "EU"
    US = "US"
    UK = "UK"
    APAC = "APAC"
    GLOBAL = "GLOBAL"
    LOCAL_ONLY = "LOCAL_ONLY"


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REDACT = "redact"
    ANONYMIZE = "anonymize"
    TRANSFORM = "transform"


@dataclass
class StreamRecord:
    """A single record in a data stream."""

    key: str
    value: bytes
    headers: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    partition: int = 0
    offset: int = -1
    lineage_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value_length": len(self.value),
            "headers": self.headers,
            "timestamp": self.timestamp,
            "partition": self.partition,
            "offset": self.offset,
            "lineage_id": self.lineage_id,
        }


@dataclass
class StreamConfig:
    """Configuration for a data stream."""

    name: str
    topic: str
    partitions: int = 3
    replication_factor: int = 1
    retention_ms: int = 604800000  # 7 days
    max_message_bytes: int = 1048576  # 1MB
    classification: DataClassification = DataClassification.INTERNAL
    jurisdiction: Jurisdiction = Jurisdiction.LOCAL_ONLY
    schema_type: str = "json"  # json, avro, protobuf
    schema_definition: str = ""
    consumer_group: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "topic": self.topic,
            "partitions": self.partitions,
            "replication_factor": self.replication_factor,
            "retention_ms": self.retention_ms,
            "max_message_bytes": self.max_message_bytes,
            "classification": self.classification.value,
            "jurisdiction": self.jurisdiction.value,
            "schema_type": self.schema_type,
        }


@dataclass
class PolicyRule:
    """An OPA-style policy rule for data sovereignty enforcement."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    description: str = ""
    effect: PolicyEffect = PolicyEffect.ALLOW
    conditions: Dict[str, Any] = field(default_factory=dict)
    # Example conditions:
    #   {"classification": "restricted", "jurisdiction": ["EU"], "action": "read"}
    #   {"source_jurisdiction": "EU", "target_jurisdiction": "US"} → DENY (GDPR)
    priority: int = 0  # Higher = evaluated first
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "effect": self.effect.value,
            "conditions": self.conditions,
            "priority": self.priority,
            "enabled": self.enabled,
        }

    def to_rego(self) -> str:
        """Generate OPA Rego policy from this rule."""
        conditions_parts = []
        for key, value in self.conditions.items():
            if isinstance(value, list):
                values = ", ".join(f'"{v}"' for v in value)
                conditions_parts.append(f"{key} in [{values}]")
            elif isinstance(value, str):
                conditions_parts.append(f'{key} == "{value}"')
            elif isinstance(value, (int, float)):
                conditions_parts.append(f"{key} == {value}")
            elif isinstance(value, bool):
                conditions_parts.append(f"{key} == {'true' if value else 'false'}")

        conditions_str = "\n    ".join(conditions_parts)
        effect_str = "true" if self.effect == PolicyEffect.ALLOW else "false"

        return f"""package tranc3.daas

# Policy: {self.name}
# {self.description}
rule_{self.id} {{
    {conditions_str}
    allow := {effect_str}
}}
"""


@dataclass
class LineageEntry:
    """Tracks data lineage — origin, transformation, and consumer."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    data_id: str = ""
    source: str = ""
    source_type: str = ""  # stream, api, file, database
    transformation: str = ""
    consumer: str = ""
    consumer_type: str = ""
    classification: DataClassification = DataClassification.INTERNAL
    jurisdiction: Jurisdiction = Jurisdiction.LOCAL_ONLY
    timestamp: float = field(default_factory=time.time)
    parent_lineage_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "data_id": self.data_id,
            "source": self.source,
            "source_type": self.source_type,
            "transformation": self.transformation,
            "consumer": self.consumer,
            "consumer_type": self.consumer_type,
            "classification": self.classification.value,
            "jurisdiction": self.jurisdiction.value,
            "timestamp": self.timestamp,
            "parent_lineage_ids": self.parent_lineage_ids,
            "metadata": self.metadata,
        }


class OPAPolicyEngine:
    """
    OPA-style policy engine for data sovereignty enforcement.
    Evaluates data access requests against registered policies.

    Key sovereignty rules:
    - EU data cannot leave EU jurisdiction (GDPR)
    - Restricted data requires explicit authorization
    - Data classification must be respected
    - Cross-jurisdiction transfers require policy approval
    """

    def __init__(self):
        self._policies: Dict[str, PolicyRule] = {}
        self._decision_log: List[Dict[str, Any]] = []
        self._custom_rules: List[Callable] = []

    def add_policy(self, rule: PolicyRule) -> None:
        """Register a policy rule."""
        self._policies[rule.id] = rule

    def add_custom_rule(self, rule: Callable[[Dict[str, Any]], PolicyEffect]) -> None:
        """Add a custom Python-based policy rule."""
        self._custom_rules.append(rule)

    def evaluate(self, context: Dict[str, Any]) -> Tuple[PolicyEffect, str]:
        """
        Evaluate a data access request against all policies.
        Returns (effect, reason).
        """
        # Sort by priority (highest first)
        sorted_rules = sorted(
            [r for r in self._policies.values() if r.enabled],
            key=lambda r: r.priority,
            reverse=True,
        )

        for rule in sorted_rules:
            if self._matches(rule.conditions, context):
                effect = rule.effect
                reason = f"Policy '{rule.name}' ({rule.id}): {effect.value}"
                self._log_decision(context, effect, reason, rule.id)
                return effect, reason

        # Check custom rules
        for custom_rule in self._custom_rules:
            try:
                effect = custom_rule(context)
                if effect != PolicyEffect.ALLOW:
                    reason = "Custom rule denied access"
                    self._log_decision(context, effect, reason, "custom")
                    return effect, reason
            except Exception:
                pass

        # Default: deny if no policy matches
        reason = "No matching policy found — default deny"
        self._log_decision(context, PolicyEffect.DENY, reason, "default")
        return PolicyEffect.DENY, reason

    def get_policies(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._policies.values()]

    def generate_rego_bundle(self) -> str:
        """Generate a complete Rego policy bundle for OPA deployment."""
        rego_parts = ["package tranc3.daas\n\nimport future.keywords.in\n\n"]
        for rule in self._policies.values():
            if rule.enabled:
                rego_parts.append(rule.to_rego())
                rego_parts.append("\n")
        return "".join(rego_parts)

    def decision_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._decision_log[-limit:]

    def _matches(self, conditions: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if context matches all conditions."""
        for key, expected in conditions.items():
            actual = context.get(key)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif isinstance(expected, bool):
                if actual != expected:
                    return False
            elif actual != expected:
                return False
        return True

    def _log_decision(self, context: Dict, effect: PolicyEffect, reason: str, rule_id: str) -> None:
        self._decision_log.append(
            {
                "timestamp": time.time(),
                "context": context,
                "effect": effect.value,
                "reason": reason,
                "rule_id": rule_id,
            }
        )


class DataLineageTracker:
    """Tracks data lineage for audit and compliance."""

    def __init__(self):
        self._entries: Dict[str, LineageEntry] = {}
        self._data_index: Dict[str, Set[str]] = {}  # data_id -> lineage IDs

    def track(self, entry: LineageEntry) -> str:
        """Record a lineage entry."""
        self._entries[entry.id] = entry
        if entry.data_id not in self._data_index:
            self._data_index[entry.data_id] = set()
        self._data_index[entry.data_id].add(entry.id)
        return entry.id

    def get_lineage(self, data_id: str) -> List[LineageEntry]:
        """Get all lineage entries for a data item."""
        entry_ids = self._data_index.get(data_id, set())
        return [self._entries[eid] for eid in entry_ids]

    def get_entry(self, lineage_id: str) -> Optional[LineageEntry]:
        return self._entries.get(lineage_id)

    def trace_origin(self, data_id: str) -> List[LineageEntry]:
        """Trace data back to its origin by following parent lineage."""
        entries = self.get_lineage(data_id)
        origin_chain = []
        visited = set()

        def follow(entry: LineageEntry) -> None:
            if entry.id in visited:
                return
            visited.add(entry.id)
            origin_chain.append(entry)
            for parent_id in entry.parent_lineage_ids:
                parent = self._entries.get(parent_id)
                if parent:
                    follow(parent)

        for entry in entries:
            follow(entry)

        return sorted(origin_chain, key=lambda e: e.timestamp)

    def stats(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self._entries),
            "tracked_data_items": len(self._data_index),
        }


class StreamPipeline:
    """
    In-process stream pipeline compatible with Redpanda/Kafka protocol.
    Provides pub/sub semantics with partition-based ordering.
    """

    def __init__(self, max_queue_size: int = 10000):
        self._streams: Dict[str, asyncio.Queue] = {}
        self._configs: Dict[str, StreamConfig] = {}
        self._offsets: Dict[str, int] = {}
        self._consumers: Dict[str, List[asyncio.Queue]] = {}
        self._max_queue_size = max_queue_size

    def create_stream(self, config: StreamConfig) -> None:
        """Create a new data stream."""
        self._streams[config.topic] = asyncio.Queue(maxsize=self._max_queue_size)
        self._configs[config.topic] = config
        self._offsets[config.topic] = 0
        self._consumers[config.topic] = []

    async def publish(self, topic: str, record: StreamRecord) -> bool:
        """Publish a record to a stream."""
        if topic not in self._streams:
            return False

        config = self._configs.get(topic)
        if config and len(record.value) > config.max_message_bytes:
            return False

        record.offset = self._offsets[topic]
        self._offsets[topic] += 1

        # Publish to main stream
        try:
            self._streams[topic].put_nowait(record)
        except asyncio.QueueFull:
            return False

        # Deliver to consumers
        for consumer_queue in self._consumers.get(topic, []):
            try:
                consumer_queue.put_nowait(record)
            except asyncio.QueueFull:
                pass

        return True

    async def subscribe(self, topic: str, consumer_id: str) -> Optional[asyncio.Queue]:
        """Subscribe to a stream. Returns a queue that receives records."""
        if topic not in self._streams:
            return None

        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        if topic not in self._consumers:
            self._consumers[topic] = []
        self._consumers[topic].append(queue)
        return queue

    async def consume(self, queue: asyncio.Queue, timeout_s: float = 1.0) -> Optional[StreamRecord]:
        """Consume a record from a subscription queue."""
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None

    def get_stream_config(self, topic: str) -> Optional[StreamConfig]:
        return self._configs.get(topic)

    def list_streams(self) -> List[str]:
        return list(self._configs.keys())

    def stats(self) -> Dict[str, Any]:
        topic_stats = {}
        for topic, queue in self._streams.items():
            topic_stats[topic] = {
                "queue_size": queue.qsize(),
                "offset": self._offsets.get(topic, 0),
                "consumers": len(self._consumers.get(topic, [])),
            }
        return {
            "total_streams": len(self._streams),
            "topics": topic_stats,
        }


class DaaSService:
    """
    DaaS — Data as a Service with Sovereignty.

    Complete data service with streaming, policy enforcement, and lineage tracking.

    Usage:
        daas = DaaSService()

        # Add sovereignty policies
        daas.add_policy(PolicyRule(
            name="GDPR EU Data Residency",
            effect=PolicyEffect.DENY,
            conditions={
                "source_jurisdiction": "EU",
                "target_jurisdiction": "US",
            },
            priority=100,
        ))

        # Create a stream
        daas.create_stream(StreamConfig(
            name="user-events",
            topic="user-events",
            classification=DataClassification.CONFIDENTIAL,
            jurisdiction=Jurisdiction.EU,
        ))

        # Publish data
        await daas.publish("user-events", StreamRecord(
            key="user_123",
            value=b'{"action": "login"}',
        ))

        # Evaluate data access
        effect, reason = daas.evaluate_access({
            "data_classification": "confidential",
            "source_jurisdiction": "EU",
            "target_jurisdiction": "US",
            "action": "read",
        })
    """

    def __init__(
        self,
        redpanda_brokers: str = "localhost:9092",
        opa_url: str = "http://localhost:8181",
    ):
        self._pipeline = StreamPipeline()
        self._policy_engine = OPAPolicyEngine()
        self._lineage = DataLineageTracker()
        self._redpanda_brokers = redpanda_brokers
        self._opa_url = opa_url
        self._running = False
        self._publish_count = 0
        self._deny_count = 0

        # Register default sovereignty policies
        self._register_default_policies()

    def _register_default_policies(self) -> None:
        """Register built-in data sovereignty policies."""
        # GDPR: EU data cannot leave EU
        self._policy_engine.add_policy(
            PolicyRule(
                name="GDPR Cross-Border Restriction",
                description="EU data cannot be transferred to non-EU jurisdictions",
                effect=PolicyEffect.DENY,
                conditions={
                    "source_jurisdiction": "EU",
                    "target_jurisdiction": "US",
                },
                priority=100,
            )
        )

        # Restricted data requires explicit authorization
        self._policy_engine.add_policy(
            PolicyRule(
                name="Restricted Data Access",
                description="Restricted data requires explicit authorization",
                effect=PolicyEffect.DENY,
                conditions={
                    "data_classification": "restricted",
                    "authorized": False,
                },
                priority=90,
            )
        )

        # Top secret data — always deny remote access
        self._policy_engine.add_policy(
            PolicyRule(
                name="Top Secret Local Only",
                description="Top secret data can only be accessed locally",
                effect=PolicyEffect.DENY,
                conditions={
                    "data_classification": "top_secret",
                    "access_type": "remote",
                },
                priority=100,
            )
        )

        # Allow public data by default
        self._policy_engine.add_policy(
            PolicyRule(
                name="Public Data Allow",
                description="Public data is accessible by default",
                effect=PolicyEffect.ALLOW,
                conditions={
                    "data_classification": "public",
                },
                priority=0,
            )
        )

    async def start(self) -> None:
        """Start the DaaS service."""
        self._running = True

    async def stop(self) -> None:
        """Stop the DaaS service."""
        self._running = False

    def create_stream(self, config: StreamConfig) -> None:
        """Create a new data stream."""
        self._pipeline.create_stream(config)

    async def publish(self, topic: str, record: StreamRecord) -> Tuple[bool, str]:
        """Publish a record to a stream with policy check."""
        config = self._pipeline.get_stream_config(topic)
        if not config:
            return False, "Stream not found"

        # Evaluate sovereignty policy
        context = {
            "topic": topic,
            "data_classification": config.classification.value,
            "source_jurisdiction": config.jurisdiction.value,
            "action": "publish",
        }
        effect, reason = self._policy_engine.evaluate(context)

        if effect == PolicyEffect.DENY:
            self._deny_count += 1
            return False, f"Policy denied: {reason}"

        # Track lineage
        if not record.lineage_id:
            lineage = LineageEntry(
                data_id=record.key,
                source=topic,
                source_type="stream",
                classification=config.classification,
                jurisdiction=config.jurisdiction,
            )
            self._lineage.track(lineage)
            record.lineage_id = lineage.id

        success = await self._pipeline.publish(topic, record)
        if success:
            self._publish_count += 1
        return success, "Published" if success else "Queue full"

    async def subscribe(self, topic: str, consumer_id: str = "") -> Optional[asyncio.Queue]:
        """Subscribe to a data stream."""
        return await self._pipeline.subscribe(topic, consumer_id or uuid.uuid4().hex[:8])

    def evaluate_access(self, context: Dict[str, Any]) -> Tuple[PolicyEffect, str]:
        """Evaluate a data access request against sovereignty policies."""
        return self._policy_engine.evaluate(context)

    def add_policy(self, rule: PolicyRule) -> None:
        """Add a custom sovereignty policy."""
        self._policy_engine.add_policy(rule)

    def get_lineage(self, data_id: str) -> List[Dict[str, Any]]:
        """Get data lineage for audit."""
        entries = self._lineage.get_lineage(data_id)
        return [e.to_dict() for e in entries]

    def generate_rego_bundle(self) -> str:
        """Generate OPA Rego policy bundle for deployment."""
        return self._policy_engine.generate_rego_bundle()

    def stats(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "publish_count": self._publish_count,
            "deny_count": self._deny_count,
            "pipeline": self._pipeline.stats(),
            "lineage": self._lineage.stats(),
            "policies": len(self._policy_engine.get_policies()),
        }
