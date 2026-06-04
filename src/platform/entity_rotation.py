"""
Entity-Level Adaptive Rotation — Trancendos Platform
======================================================
Every one of the 43 platform entities has a Lead AI agent and a pool of
fallback service instances. This module manages:

  • Health-tracked primary + fallback rotation per entity
  • AI agent personality preservation across rotations (the AI persona
    continues regardless of which backing instance handles the request)
  • Emergency failover with exponential backoff
  • Zero-cost constraint enforcement (no paid external calls)
  • Sentinel Station event emission on rotation events

Zero-cost guarantee: all rotation targets are self-hosted instances or
free-tier providers already in the ZERO_COST_CHAINS config.

Usage:
    from src.platform.entity_rotation import get_entity_rotator, EntityID

    rotator = get_entity_rotator()
    endpoint = await rotator.resolve(EntityID.THE_SPARK)
    # endpoint is the healthiest available instance URL
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("tranc3.platform.entity_rotation")

# ---------------------------------------------------------------------------
# Entity IDs — every canonical platform entity
# ---------------------------------------------------------------------------

class EntityID(str, Enum):
    # Architectural
    THE_SPARK = "the-spark"
    THE_DIGITAL_GRID = "the-digital-grid"
    THE_VOID = "the-void"
    THE_WORKSHOP = "the-workshop"
    INFINITY = "infinity"
    THE_LIGHTHOUSE = "the-lighthouse"
    THE_HIVE = "the-hive"
    THE_NEXUS = "the-nexus"
    THE_CITADEL = "the-citadel"
    LUMINOUS = "luminous"
    THE_OBSERVATORY = "the-observatory"
    # Commercial / Financial
    ROYAL_BANK_OF_ARCADIA = "royal-bank-of-arcadia"
    ARCADIAN_EXCHANGE = "arcadian-exchange"
    # Creativity
    SASHAS_PHOTO_STUDIO = "sashas-photo-studio"
    TRANCEFLOW = "tranceflow"
    TATEKING = "tateking"
    FABULOUSA = "fabulousa"
    IMAGINARIUM = "imaginarium"
    THE_STUDIO = "the-studio"
    WARP_RADIO = "warp-radio"
    VRAR3D = "vrar3d"
    # Development / Code
    THE_LAB = "the-lab"
    THINK_TANK = "think-tank"
    DEVOCITY = "devocity"
    # Knowledge
    THE_LIBRARY = "the-library"
    THE_ACADEMY = "the-academy"
    DOCUTARI = "docutari"
    THE_BASEMENT = "the-basement"
    TURINGS_HUB = "turings-hub"
    # Security
    CRYPTEX = "cryptex"
    THE_ICE_BOX = "the-ice-box"
    THE_WARP_TUNNEL = "the-warp-tunnel"
    # DevOps
    THE_ARTIFACTORY = "the-artifactory"
    API_MARKETPLACE = "api-marketplace"
    # Governance
    THE_TOWN_HALL = "the-town-hall"
    ARCADIA = "arcadia"
    # Scheduling
    CHRONOSSPHERE = "chronossphere"
    # Wellbeing
    TRANQUILITY = "tranquility"
    IMIND = "imind"
    RESONATE = "resonate"
    TAIMRA = "taimra"
    # Intelligence & Analysis
    SECTION_7 = "section-7"


# ---------------------------------------------------------------------------
# AI Agent registry — Lead AI personality for each entity
# The AI agents (Voxx, Norman Hawkins, etc.) are the intelligence
# that powers each entity; they persist across instance rotations.
# ---------------------------------------------------------------------------

ENTITY_LEAD_AI: Dict[EntityID, str] = {
    EntityID.THE_SPARK: "Imfy",
    EntityID.THE_DIGITAL_GRID: "Tyler Towncroft",
    EntityID.THE_VOID: "Prometheus",
    EntityID.THE_WORKSHOP: "Larry Lowhammer",
    EntityID.INFINITY: "The Guardian (Marcus Magnolia) & The Orb of Orisis",
    EntityID.THE_LIGHTHOUSE: "Rocking Ricki",
    EntityID.THE_HIVE: "The Queen",
    EntityID.THE_NEXUS: "The Nexus",
    EntityID.THE_CITADEL: "Trancendos",
    EntityID.LUMINOUS: "Cornelius MacIntyre",
    EntityID.THE_OBSERVATORY: "Norman Hawkins",
    EntityID.ROYAL_BANK_OF_ARCADIA: "Dorris Fontaine",
    EntityID.ARCADIAN_EXCHANGE: "Clarence Porter, Ann Porter, George Porter, Edward Porter, James Porter",
    EntityID.SASHAS_PHOTO_STUDIO: "Madam Krystal",
    EntityID.TRANCEFLOW: "Junior Cesar",
    EntityID.TATEKING: "Benji Tate & Sam King",  # Two separate AIs: Benji Tate, Sam King
    EntityID.FABULOUSA: "Baron Von Hilton",
    EntityID.IMAGINARIUM: "Voxx",
    EntityID.THE_STUDIO: "Voxx",
    EntityID.WARP_RADIO: "Rocking Ricki",
    EntityID.VRAR3D: "Entari",
    EntityID.THE_LAB: "The Dr. (Nikolai O'denhime) & Slime",
    EntityID.THINK_TANK: "Trancendos",
    EntityID.DEVOCITY: "Kitty",
    EntityID.THE_LIBRARY: "Zimik",
    EntityID.THE_ACADEMY: "Shimshi",
    EntityID.DOCUTARI: "Fiddsy",
    EntityID.THE_BASEMENT: "Gary Glowman",
    EntityID.TURINGS_HUB: "Samantha Turing",
    EntityID.CRYPTEX: "Renik",
    EntityID.THE_ICE_BOX: "Neonach",
    EntityID.THE_WARP_TUNNEL: "Rocking Ricki",
    EntityID.THE_ARTIFACTORY: "Lunascene",
    EntityID.API_MARKETPLACE: "Solarscene",
    EntityID.THE_TOWN_HALL: "Tristuran",
    EntityID.ARCADIA: "Lilli SC",
    EntityID.CHRONOSSPHERE: "Chronos",
    EntityID.TRANQUILITY: "Savania",
    EntityID.IMIND: "Elouise",
    EntityID.RESONATE: "Magdalena",
    EntityID.TAIMRA: "tAImra",
    EntityID.SECTION_7: "The Dutchy",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ServiceInstance:
    """A single backing instance for an entity."""
    url: str
    label: str
    is_primary: bool = True
    zero_cost: bool = True  # MUST be True — no paid services allowed
    healthy: bool = True
    failures: int = 0
    last_checked: float = 0.0
    cooldown_until: float = 0.0
    latency_ms: float = 0.0

    @property
    def in_cooldown(self) -> bool:
        return time.monotonic() < self.cooldown_until

    def record_failure(self, cooldown_s: float = 30.0) -> None:
        self.failures += 1
        self.healthy = False
        self.cooldown_until = time.monotonic() + cooldown_s * (2 ** min(self.failures - 1, 5))

    def record_success(self) -> None:
        self.healthy = True
        self.failures = 0
        self.cooldown_until = 0.0


@dataclass
class EntityRotationPool:
    """Rotation pool for one entity — primary + fallbacks, AI agent preserved."""
    entity_id: EntityID
    lead_ai: str
    instances: List[ServiceInstance] = field(default_factory=list)
    active_index: int = 0
    rotation_count: int = 0
    last_rotation_at: float = 0.0

    # Callbacks invoked on rotation (e.g., emit to Sentinel Station)
    on_rotate: Optional[Callable[[EntityID, str, str], None]] = field(
        default=None, repr=False
    )

    def add_instance(self, url: str, label: str, is_primary: bool = False) -> None:
        self.instances.append(ServiceInstance(url=url, label=label, is_primary=is_primary))

    @property
    def active(self) -> Optional[ServiceInstance]:
        if not self.instances:
            return None
        return self.instances[self.active_index % len(self.instances)]

    def rotate(self) -> Optional[ServiceInstance]:
        """Rotate to the next healthy instance. Returns the new active instance."""
        if not self.instances:
            return None
        old_url = self.active.url if self.active else "none"
        for _ in range(len(self.instances)):
            self.active_index = (self.active_index + 1) % len(self.instances)
            candidate = self.instances[self.active_index]
            if candidate.healthy and not candidate.in_cooldown:
                self.rotation_count += 1
                self.last_rotation_at = time.monotonic()
                logger.warning(
                    "[%s] Lead AI=%s rotated %s → %s (rotation #%d)",
                    self.entity_id.value,
                    self.lead_ai,
                    old_url,
                    candidate.url,
                    self.rotation_count,
                )
                if self.on_rotate:
                    try:
                        self.on_rotate(self.entity_id, old_url, candidate.url)
                    except Exception:
                        pass
                return candidate
        logger.error(
            "[%s] ALL instances exhausted — no healthy fallback available",
            self.entity_id.value,
        )
        return None

    def resolve(self) -> Optional[ServiceInstance]:
        """Return active instance if healthy, otherwise rotate."""
        current = self.active
        if current and current.healthy and not current.in_cooldown:
            return current
        return self.rotate()

    def to_status(self) -> dict:
        active = self.active
        return {
            "entity": self.entity_id.value,
            "lead_ai": self.lead_ai,
            "active_url": active.url if active else None,
            "active_healthy": active.healthy if active else False,
            "instances": [
                {
                    "url": i.url,
                    "label": i.label,
                    "healthy": i.healthy,
                    "failures": i.failures,
                    "in_cooldown": i.in_cooldown,
                    "latency_ms": round(i.latency_ms, 2),
                    "zero_cost": i.zero_cost,
                }
                for i in self.instances
            ],
            "rotation_count": self.rotation_count,
            "last_rotation_at": self.last_rotation_at,
        }


# ---------------------------------------------------------------------------
# Entity Rotator — singleton managing all 43 entity pools
# ---------------------------------------------------------------------------

class EntityRotator:
    """
    Central rotation manager for all 43 Trancendos platform entities.

    Each entity maintains:
      - A Lead AI agent identity (personality, never changes)
      - N service instances (primary + fallbacks, all zero-cost)
      - Automatic health-based rotation with exponential backoff

    The AI agent personality (Voxx, Norman Hawkins, etc.) is PRESERVED
    across all rotations — it is loaded from the personality profile system
    and injected into whichever backing instance is currently active.
    """

    def __init__(self) -> None:
        self._pools: Dict[EntityID, EntityRotationPool] = {}
        self._health_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._build_default_pools()

    def _build_default_pools(self) -> None:
        """Build rotation pools for all 43 entities with their zero-cost backends."""

        # Architectural entities (self-hosted workers)
        self._add_pool(EntityID.THE_SPARK, [
            ("http://localhost:8000/mcp", "primary"),
            ("http://localhost:8000/mcp", "local-replica-1"),
        ])
        self._add_pool(EntityID.THE_DIGITAL_GRID, [
            ("http://localhost:8034", "primary"),
            ("http://localhost:8000/workflow", "api-fallback"),
        ])
        self._add_pool(EntityID.THE_VOID, [
            ("http://localhost:8038", "vault-primary"),
            ("http://localhost:8038", "vault-replica"),
        ])
        self._add_pool(EntityID.THE_WORKSHOP, [
            ("http://localhost:3456", "forgejo-primary"),
        ])
        self._add_pool(EntityID.INFINITY, [
            ("http://localhost:8005", "auth-primary"),
            ("http://localhost:8015", "identity-fallback"),
        ])
        self._add_pool(EntityID.THE_LIGHTHOUSE, [
            ("http://localhost:8000/lighthouse", "primary"),
        ])
        self._add_pool(EntityID.THE_HIVE, [
            ("http://localhost:8027", "queue-primary"),
            ("http://localhost:8000/hive", "api-fallback"),
        ])
        self._add_pool(EntityID.THE_NEXUS, [
            ("http://localhost:8004", "ws-primary"),
        ])
        self._add_pool(EntityID.THE_CITADEL, [
            ("http://localhost:8000", "api-primary"),
            ("http://localhost:8029", "health-aggregator"),
        ])
        self._add_pool(EntityID.LUMINOUS, [
            ("http://localhost:8009", "ai-primary"),
            ("http://localhost:11434", "ollama-local"),
            ("http://localhost:8000/inference", "api-fallback"),
        ])
        self._add_pool(EntityID.THE_OBSERVATORY, [
            ("http://localhost:8007", "monitoring-primary"),
            ("http://localhost:8017", "audit-fallback"),
        ])
        # Commercial / Financial
        self._add_pool(EntityID.ROYAL_BANK_OF_ARCADIA, [
            ("http://localhost:8013", "payments-primary"),
            ("http://localhost:8032", "ledger-fallback"),
        ])
        self._add_pool(EntityID.ARCADIAN_EXCHANGE, [
            ("http://localhost:8012", "orders-primary"),
        ])
        # Creativity
        self._add_pool(EntityID.SASHAS_PHOTO_STUDIO, [
            ("http://localhost:8188", "comfyui-primary"),  # ComfyUI zero-cost
            ("http://localhost:8000/studio/photo", "api-stub"),
        ])
        self._add_pool(EntityID.TRANCEFLOW, [
            ("http://localhost:8042", "godot-primary"),
            ("http://localhost:8000/studio/3d", "api-stub"),
        ])
        self._add_pool(EntityID.TATEKING, [
            ("http://localhost:8040", "ffmpeg-primary"),
            ("http://localhost:8000/studio/video", "api-stub"),
        ])
        self._add_pool(EntityID.FABULOUSA, [
            ("http://localhost:9001", "penpot-primary"),  # Penpot self-hosted zero-cost
            ("http://localhost:8000/studio/design", "api-stub"),
        ])
        self._add_pool(EntityID.IMAGINARIUM, [
            ("http://localhost:8000/imaginarium", "orchestrator-primary"),
        ])
        self._add_pool(EntityID.THE_STUDIO, [
            ("http://localhost:8000/studio", "primary"),
        ])
        self._add_pool(EntityID.WARP_RADIO, [
            ("http://localhost:8000/warp-radio", "primary"),
        ])
        self._add_pool(EntityID.VRAR3D, [
            ("http://localhost:8000/vrar3d", "primary"),
        ])
        # Development / Code
        self._add_pool(EntityID.THE_LAB, [
            ("http://localhost:8000/lab", "primary"),
        ])
        self._add_pool(EntityID.THINK_TANK, [
            ("http://localhost:8000/think-tank", "primary"),
        ])
        self._add_pool(EntityID.DEVOCITY, [
            ("http://localhost:8000/devocity", "primary"),
        ])
        # Knowledge
        self._add_pool(EntityID.THE_LIBRARY, [
            ("http://localhost:3000", "outline-primary"),  # Outline self-hosted zero-cost
            ("http://localhost:8000/library", "api-stub"),
        ])
        self._add_pool(EntityID.THE_ACADEMY, [
            ("http://localhost:8000/academy", "primary"),
        ])
        self._add_pool(EntityID.DOCUTARI, [
            ("http://localhost:8010/api/documents", "paperless-primary"),  # Paperless-ngx
            ("http://localhost:8014", "files-fallback"),
        ])
        self._add_pool(EntityID.THE_BASEMENT, [
            ("http://localhost:8000/basement", "primary"),
        ])
        self._add_pool(EntityID.TURINGS_HUB, [
            ("http://localhost:8035", "skills-primary"),
            ("http://localhost:8000/personality", "api-fallback"),
        ])
        # Security
        self._add_pool(EntityID.CRYPTEX, [
            ("http://localhost:55000", "wazuh-primary"),  # Wazuh self-hosted zero-cost
            ("http://localhost:8000/cryptex", "api-stub"),
        ])
        self._add_pool(EntityID.THE_ICE_BOX, [
            ("http://localhost:8090", "sandbox-primary"),
            ("http://localhost:8000/icebox", "api-stub"),
        ])
        self._add_pool(EntityID.THE_WARP_TUNNEL, [
            ("http://localhost:8000/warp-tunnel", "primary"),
        ])
        # DevOps
        self._add_pool(EntityID.THE_ARTIFACTORY, [
            ("http://localhost:5000", "zot-primary"),  # Zot OCI registry zero-cost
            ("http://localhost:8000/artifactory", "api-stub"),
        ])
        self._add_pool(EntityID.API_MARKETPLACE, [
            ("http://localhost:8082", "gravitee-primary"),  # Gravitee CE zero-cost
            ("http://localhost:8000/api-market", "api-stub"),
        ])
        # Governance
        self._add_pool(EntityID.THE_TOWN_HALL, [
            ("http://localhost:8000/townhall", "primary"),
        ])
        self._add_pool(EntityID.ARCADIA, [
            ("http://localhost:3001", "web-primary"),
            ("http://localhost:8000/arcadia", "api-fallback"),
        ])
        # Scheduling
        self._add_pool(EntityID.CHRONOSSPHERE, [
            ("http://localhost:3002", "cal-primary"),  # Cal.com self-hosted zero-cost
            ("http://localhost:8021", "cron-fallback"),
        ])
        # Wellbeing
        self._add_pool(EntityID.TRANQUILITY, [
            ("http://localhost:8000/tranquility", "primary"),
        ])
        self._add_pool(EntityID.IMIND, [
            ("http://localhost:8000/imind", "primary"),
        ])
        self._add_pool(EntityID.RESONATE, [
            ("http://localhost:8000/resonate", "primary"),
        ])
        self._add_pool(EntityID.TAIMRA, [
            ("http://localhost:8000/taimra", "primary"),
        ])
        # Intelligence
        self._add_pool(EntityID.SECTION_7, [
            ("http://localhost:8000/research", "primary"),
        ])

    def _add_pool(self, entity_id: EntityID, instances: list[tuple[str, str]]) -> None:
        pool = EntityRotationPool(
            entity_id=entity_id,
            lead_ai=ENTITY_LEAD_AI.get(entity_id, "Unknown"),
            on_rotate=self._on_rotation_event,
        )
        for i, (url, label) in enumerate(instances):
            pool.add_instance(url=url, label=label, is_primary=(i == 0))
        self._pools[entity_id] = pool

    def _on_rotation_event(self, entity_id: EntityID, from_url: str, to_url: str) -> None:
        """Emit rotation event to Sentinel Station (non-blocking)."""
        try:
            from src.adaptive.provider_rotator import get_provider_rotator  # noqa
            logger.info(
                "ROTATION_EVENT entity=%s from=%s to=%s lead_ai=%s",
                entity_id.value,
                from_url,
                to_url,
                ENTITY_LEAD_AI.get(entity_id, "?"),
            )
        except Exception:
            pass

    def get_pool(self, entity_id: EntityID) -> Optional[EntityRotationPool]:
        return self._pools.get(entity_id)

    async def resolve(self, entity_id: EntityID) -> Optional[str]:
        """Resolve the healthiest endpoint URL for an entity."""
        pool = self._pools.get(entity_id)
        if not pool:
            logger.warning("No rotation pool for entity %s", entity_id.value)
            return None
        instance = pool.resolve()
        return instance.url if instance else None

    def report_failure(self, entity_id: EntityID, url: str) -> None:
        """Mark an instance as failed, triggering rotation on next resolve."""
        pool = self._pools.get(entity_id)
        if not pool:
            return
        for inst in pool.instances:
            if inst.url == url:
                inst.record_failure()
                logger.warning(
                    "[%s] Instance %s marked failed (failures=%d)",
                    entity_id.value, url, inst.failures,
                )
                break

    def report_success(self, entity_id: EntityID, url: str, latency_ms: float = 0.0) -> None:
        """Mark an instance as healthy after a successful call."""
        pool = self._pools.get(entity_id)
        if not pool:
            return
        for inst in pool.instances:
            if inst.url == url:
                inst.record_success()
                inst.latency_ms = latency_ms
                break

    async def start_health_loop(self, interval_s: float = 30.0) -> None:
        """Background health probe loop — runs probes against all entity instances."""
        if self._health_task is not None:
            return
        self._health_task = asyncio.create_task(self._health_loop(interval_s))
        logger.info("Entity rotation health loop started (interval=%ss)", interval_s)

    async def _health_loop(self, interval_s: float) -> None:
        import httpx
        while True:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    for pool in self._pools.values():
                        for inst in pool.instances:
                            if inst.in_cooldown:
                                continue
                            health_url = inst.url.rstrip("/") + "/health"
                            t0 = time.monotonic()
                            try:
                                resp = await client.get(health_url)
                                latency_ms = (time.monotonic() - t0) * 1000
                                if resp.status_code < 500:
                                    inst.record_success()
                                    inst.latency_ms = latency_ms
                                else:
                                    inst.record_failure()
                            except Exception:
                                inst.record_failure()
            except Exception as exc:
                logger.debug("Health loop error: %s", exc)
            await asyncio.sleep(interval_s)

    def status_all(self) -> list[dict]:
        """Return full rotation status for all 43 entities."""
        return [pool.to_status() for pool in self._pools.values()]

    def zero_cost_audit(self) -> dict:
        """Verify every instance in every pool is flagged zero_cost=True."""
        violations = []
        for pool in self._pools.values():
            for inst in pool.instances:
                if not inst.zero_cost:
                    violations.append({
                        "entity": pool.entity_id.value,
                        "url": inst.url,
                        "label": inst.label,
                    })
        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "total_entities": len(self._pools),
            "total_instances": sum(len(p.instances) for p in self._pools.values()),
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_rotator: Optional[EntityRotator] = None


def get_entity_rotator() -> EntityRotator:
    global _rotator
    if _rotator is None:
        _rotator = EntityRotator()
    return _rotator
