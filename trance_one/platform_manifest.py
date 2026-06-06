"""
Platform Manifest — Trance-One Tier 1
======================================
Canonical mapping of all 43 platform entities to their tier assignments,
Lead AI agents, zero-cost foundations, and pillar classifications.

This is the single source of truth for the 5-tier AI hierarchy across the
entire Trancendos platform. All tiers resolve entity ownership through here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Pillar(str, Enum):
    ARCHITECTURAL = "Architectural"
    COMMERCIAL_FINANCIAL = "Commercial & Financial"
    CREATIVITY = "Creativity"
    DEVELOPMENT_CODE = "Development & Code"
    KNOWLEDGE = "Knowledge"
    SECURITY = "Security"
    DEVOPS = "DevOps"
    WELLBEING = "Wellbeing"
    GOVERNANCE = "Governance"


class TierLevel(int, Enum):
    TIER_1_SOVEREIGN = 1  # Trance-One
    TIER_2_PRIME = 2  # T2ance
    TIER_3_BASE_AI = 3  # Tranc3 (this repo)
    TIER_4_AGENT = 4  # Infinity-Agent (Alpha + Beta)
    TIER_5_WORKER = 5  # Infinity-Worker (Bots/Workers/Scrapers)


@dataclass
class EntityManifestEntry:
    entity_id: str
    display_name: str
    lead_ai: str  # primary Tier 3 AI that powers this entity
    pillar: Pillar
    src_path: str  # canonical code path within the repo
    foundation_keys: List[str] = field(default_factory=list)
    status: str = "planned"  # "live" | "partial" | "planned" | "migrating"
    port: Optional[int] = None
    lead_ais: List[str] = field(default_factory=list)  # all AIs when entity has multiple


# ---------------------------------------------------------------------------
# Canonical 43-entity manifest
# ---------------------------------------------------------------------------

ENTITY_MANIFEST: Dict[str, EntityManifestEntry] = {
    # ── Architectural ─────────────────────────────────────────────────────
    "the-spark": EntityManifestEntry(
        entity_id="the-spark",
        display_name="The Spark",
        lead_ai="Imfy",
        pillar=Pillar.ARCHITECTURAL,
        src_path="src/mcp/",
        foundation_keys=["nats"],
        status="live",
    ),
    "the-digital-grid": EntityManifestEntry(
        entity_id="the-digital-grid",
        display_name="The Digital Grid",
        lead_ai="Tyler Towncroft",
        pillar=Pillar.ARCHITECTURAL,
        src_path="src/workflow/",
        foundation_keys=["n8n"],
        status="live",
        port=8034,
    ),
    "the-void": EntityManifestEntry(
        entity_id="the-void",
        display_name="The Void",
        lead_ai="Prometheus",
        pillar=Pillar.SECURITY,
        src_path="cloudflare/infinity-void/",
        foundation_keys=["vault_hashicorp"],
        status="migrating",
        port=8038,
    ),
    "the-workshop": EntityManifestEntry(
        entity_id="the-workshop",
        display_name="The Workshop",
        lead_ai="Larry Lowhammer",
        pillar=Pillar.DEVELOPMENT_CODE,
        src_path="deploy/forgejo/",
        foundation_keys=["forgejo"],
        status="live",
    ),
    "infinity": EntityManifestEntry(
        entity_id="infinity",
        display_name="Infinity",
        lead_ai="The Guardian (Marcus Magnolia)",
        pillar=Pillar.ARCHITECTURAL,
        src_path="workers/infinity-auth/",
        foundation_keys=[],
        status="live",
        port=8005,
        lead_ais=["The Guardian (Marcus Magnolia)", "The Orb of Orisis"],
    ),
    "the-lighthouse": EntityManifestEntry(
        entity_id="the-lighthouse",
        display_name="The Lighthouse",
        lead_ai="Rocking Ricki",
        pillar=Pillar.SECURITY,
        src_path="src/auth/",
        foundation_keys=[],
        status="live",
    ),
    "the-hive": EntityManifestEntry(
        entity_id="the-hive",
        display_name="The HIVE",
        lead_ai="The Queen",
        pillar=Pillar.ARCHITECTURAL,
        src_path="src/event_bus/",
        foundation_keys=["nats"],
        status="live",
        port=8027,
    ),
    "the-nexus": EntityManifestEntry(
        entity_id="the-nexus",
        display_name="The Nexus",
        lead_ai="The Nexus",
        pillar=Pillar.ARCHITECTURAL,
        src_path="workers/infinity-ws/",
        foundation_keys=[],
        status="live",
        port=8004,
    ),
    "the-citadel": EntityManifestEntry(
        entity_id="the-citadel",
        display_name="The Citadel",
        lead_ai="Trancendos",
        pillar=Pillar.DEVOPS,
        src_path="src/citadel/",
        foundation_keys=["grafana", "prometheus"],
        status="live",
    ),
    "luminous": EntityManifestEntry(
        entity_id="luminous",
        display_name="Luminous",
        lead_ai="Cornelius MacIntyre",
        pillar=Pillar.ARCHITECTURAL,
        src_path="src/bio_neural/",
        foundation_keys=["ollama", "langgraph", "qdrant"],
        status="partial",
        port=8009,
    ),
    "the-observatory": EntityManifestEntry(
        entity_id="the-observatory",
        display_name="The Observatory",
        lead_ai="Norman Hawkins",
        pillar=Pillar.DEVOPS,
        src_path="src/observability/",
        foundation_keys=["grafana", "prometheus", "loki", "tempo"],
        status="live",
        port=8007,
    ),
    # ── Commercial & Financial ─────────────────────────────────────────────
    "royal-bank-of-arcadia": EntityManifestEntry(
        entity_id="royal-bank-of-arcadia",
        display_name="Royal Bank of Arcadia",
        lead_ai="Dorris Fontaine",
        pillar=Pillar.COMMERCIAL_FINANCIAL,
        src_path="cloudflare/arcadia-royal-bank/",
        foundation_keys=[],
        status="live",
        port=8013,
    ),
    "arcadian-exchange": EntityManifestEntry(
        entity_id="arcadian-exchange",
        display_name="Arcadian Exchange",
        lead_ai="Clarence Porter",
        pillar=Pillar.COMMERCIAL_FINANCIAL,
        src_path="cloudflare/arcadia-exchange/",
        foundation_keys=[],
        status="live",
        port=8012,
        lead_ais=[
            "Clarence Porter",
            "Ann Porter",
            "George Porter",
            "Edward Porter",
            "James Porter",
        ],
    ),
    "chronossphere": EntityManifestEntry(
        entity_id="chronossphere",
        display_name="ChronosSphere / ArcStream",
        lead_ai="Chronos",
        pillar=Pillar.COMMERCIAL_FINANCIAL,
        src_path="src/chronos/",
        foundation_keys=["cal_com"],
        status="planned",
        port=8021,
    ),
    "devocity": EntityManifestEntry(
        entity_id="devocity",
        display_name="DevOcity",
        lead_ai="Kitty",
        pillar=Pillar.DEVELOPMENT_CODE,
        src_path="src/devocity/",
        foundation_keys=["grafana"],
        status="planned",
    ),
    # ── Creativity ────────────────────────────────────────────────────────
    "sashas-photo-studio": EntityManifestEntry(
        entity_id="sashas-photo-studio",
        display_name="Sashas Photo Studio",
        lead_ai="Madam Krystal",
        pillar=Pillar.CREATIVITY,
        src_path="src/entities/locations/sashas_photo_studio/",
        foundation_keys=["comfyui"],
        status="planned",
    ),
    "tranceflow": EntityManifestEntry(
        entity_id="tranceflow",
        display_name="TranceFlow",
        lead_ai="Junior Cesar",
        pillar=Pillar.CREATIVITY,
        src_path="src/entities/locations/tranceflow/",
        foundation_keys=["godot", "three_js"],
        status="planned",
    ),
    "tateking": EntityManifestEntry(
        entity_id="tateking",
        display_name="TateKing",
        lead_ai="Benji Tate",
        pillar=Pillar.CREATIVITY,
        src_path="src/entities/locations/tateking/",
        foundation_keys=["ffmpeg"],
        status="planned",
        lead_ais=["Benji Tate", "Sam King"],
    ),
    "fabulousa": EntityManifestEntry(
        entity_id="fabulousa",
        display_name="Fabulousa",
        lead_ai="Baron Von Hilton",
        pillar=Pillar.CREATIVITY,
        src_path="src/entities/locations/fabulousa/",
        foundation_keys=["penpot"],
        status="planned",
    ),
    "imaginarium": EntityManifestEntry(
        entity_id="imaginarium",
        display_name="Imaginarium",
        lead_ai="Voxx",
        pillar=Pillar.CREATIVITY,
        src_path="src/entities/locations/imaginarium/",
        foundation_keys=["comfyui", "ffmpeg", "godot"],
        status="planned",
    ),
    "the-studio": EntityManifestEntry(
        entity_id="the-studio",
        display_name="The Studio",
        lead_ai="Voxx",
        pillar=Pillar.CREATIVITY,
        src_path="src/studio/",
        foundation_keys=["comfyui", "ffmpeg"],
        status="planned",
    ),
    "warp-radio": EntityManifestEntry(
        entity_id="warp-radio",
        display_name="Warp Radio",
        lead_ai="Rocking Ricki",
        pillar=Pillar.CREATIVITY,
        src_path="src/entities/locations/warp_radio/",
        foundation_keys=["liquidsoap"],
        status="planned",
    ),
    "vrar3d": EntityManifestEntry(
        entity_id="vrar3d",
        display_name="VRAR3D",
        lead_ai="Entari",
        pillar=Pillar.CREATIVITY,
        src_path="src/vrar3d/",
        foundation_keys=["aframe", "three_js"],
        status="planned",
    ),
    # ── Development & Code ────────────────────────────────────────────────
    "the-lab": EntityManifestEntry(
        entity_id="the-lab",
        display_name="The Lab",
        lead_ai="The Dr. (Nikolai O'denhime)",
        pillar=Pillar.DEVELOPMENT_CODE,
        src_path="src/lab/",
        foundation_keys=[],
        status="planned",
        lead_ais=["The Dr. (Nikolai O'denhime)", "Slime"],
    ),
    "think-tank": EntityManifestEntry(
        entity_id="think-tank",
        display_name="Think Tank",
        lead_ai="Trancendos",
        pillar=Pillar.DEVELOPMENT_CODE,
        src_path="src/quantum/",
        foundation_keys=[],
        status="planned",
    ),
    "the-artifactory": EntityManifestEntry(
        entity_id="the-artifactory",
        display_name="The Artifactory",
        lead_ai="Lunascene",
        pillar=Pillar.DEVELOPMENT_CODE,
        src_path="src/artifactory/",
        foundation_keys=["zot"],
        status="planned",
    ),
    "api-marketplace": EntityManifestEntry(
        entity_id="api-marketplace",
        display_name="API Marketplace",
        lead_ai="Solarscene",
        pillar=Pillar.DEVELOPMENT_CODE,
        src_path="src/apimarket/",
        foundation_keys=["gravitee"],
        status="planned",
    ),
    # ── Knowledge ─────────────────────────────────────────────────────────
    "the-library": EntityManifestEntry(
        entity_id="the-library",
        display_name="The Library",
        lead_ai="Zimik",
        pillar=Pillar.KNOWLEDGE,
        src_path="src/library/",
        foundation_keys=["outline"],
        status="planned",
    ),
    "the-academy": EntityManifestEntry(
        entity_id="the-academy",
        display_name="The Academy",
        lead_ai="Shimshi",
        pillar=Pillar.KNOWLEDGE,
        src_path="src/entities/locations/the_academy/",
        foundation_keys=["openedx"],
        status="planned",
    ),
    "docutari": EntityManifestEntry(
        entity_id="docutari",
        display_name="DocUtari",
        lead_ai="Fiddsy",
        pillar=Pillar.KNOWLEDGE,
        src_path="src/entities/locations/docutari/",
        foundation_keys=["paperless_ngx"],
        status="planned",
        port=8014,
    ),
    "the-basement": EntityManifestEntry(
        entity_id="the-basement",
        display_name="The Basement",
        lead_ai="Gary Glowman",
        pillar=Pillar.KNOWLEDGE,
        src_path="src/basement/",
        foundation_keys=[],
        status="planned",
    ),
    "turings-hub": EntityManifestEntry(
        entity_id="turings-hub",
        display_name="Turing's Hub",
        lead_ai="Samantha Turing",
        pillar=Pillar.KNOWLEDGE,
        src_path="src/personality/",
        foundation_keys=["ollama", "three_js", "aframe"],
        status="partial",
        port=8035,
    ),
    # ── Security ──────────────────────────────────────────────────────────
    "cryptex": EntityManifestEntry(
        entity_id="cryptex",
        display_name="Cryptex",
        lead_ai="Renik",
        pillar=Pillar.SECURITY,
        src_path="src/cryptex/",
        foundation_keys=["wazuh", "misp"],
        status="planned",
    ),
    "the-ice-box": EntityManifestEntry(
        entity_id="the-ice-box",
        display_name="The Ice Box",
        lead_ai="Neonach",
        pillar=Pillar.SECURITY,
        src_path="src/entities/locations/the_ice_box/",
        foundation_keys=[],
        status="planned",
    ),
    "the-warp-tunnel": EntityManifestEntry(
        entity_id="the-warp-tunnel",
        display_name="The Warp Tunnel",
        lead_ai="Rocking Ricki",
        pillar=Pillar.SECURITY,
        src_path="src/entities/locations/the_warp_tunnel/",
        foundation_keys=[],
        status="planned",
    ),
    # ── Governance ────────────────────────────────────────────────────────
    "the-town-hall": EntityManifestEntry(
        entity_id="the-town-hall",
        display_name="The Town Hall",
        lead_ai="Tristuran",
        pillar=Pillar.GOVERNANCE,
        src_path="src/townhall/",
        foundation_keys=[],
        status="partial",
    ),
    "arcadia": EntityManifestEntry(
        entity_id="arcadia",
        display_name="Arcadia",
        lead_ai="Lilli SC",
        pillar=Pillar.GOVERNANCE,
        src_path="web/",
        foundation_keys=[],
        status="partial",
    ),
    # ── Wellbeing ─────────────────────────────────────────────────────────
    "tranquility": EntityManifestEntry(
        entity_id="tranquility",
        display_name="Tranquility",
        lead_ai="Savania",
        pillar=Pillar.WELLBEING,
        src_path="src/tranquility/",
        foundation_keys=[],
        status="planned",
    ),
    "imind": EntityManifestEntry(
        entity_id="imind",
        display_name="I-Mind",
        lead_ai="Elouise",
        pillar=Pillar.WELLBEING,
        src_path="src/imind/",
        foundation_keys=["ollama"],
        status="planned",
    ),
    "resonate": EntityManifestEntry(
        entity_id="resonate",
        display_name="Resonate",
        lead_ai="Magdalena",
        pillar=Pillar.WELLBEING,
        src_path="src/resonate/",
        foundation_keys=["ollama"],
        status="planned",
    ),
    "taimra": EntityManifestEntry(
        entity_id="taimra",
        display_name="tAimra",
        lead_ai="tAImra",
        pillar=Pillar.WELLBEING,
        src_path="src/taimra/",
        foundation_keys=["ollama", "qdrant"],
        status="planned",
    ),
    "section-7": EntityManifestEntry(
        entity_id="section-7",
        display_name="Section 7",
        lead_ai="The Dutchy",
        pillar=Pillar.KNOWLEDGE,
        src_path="src/research/",
        foundation_keys=["qdrant"],
        status="planned",
    ),
    "the-chaos-party": EntityManifestEntry(
        entity_id="the-chaos-party",
        display_name="The Chaos Party",
        lead_ai="The Mad Hatter",
        pillar=Pillar.DEVELOPMENT_CODE,
        src_path="tests/",
        foundation_keys=[],
        status="partial",
    ),
}


# ---------------------------------------------------------------------------
# PlatformManifest — singleton accessor
# ---------------------------------------------------------------------------


class PlatformManifest:
    """Read-only view of the canonical 43-entity platform manifest."""

    def entity(self, entity_id: str) -> EntityManifestEntry:
        e = ENTITY_MANIFEST.get(entity_id)
        if not e:
            raise KeyError(f"Unknown entity: {entity_id}")
        return e

    def by_pillar(self, pillar: Pillar) -> List[EntityManifestEntry]:
        return [e for e in ENTITY_MANIFEST.values() if e.pillar == pillar]

    def by_status(self, status: str) -> List[EntityManifestEntry]:
        return [e for e in ENTITY_MANIFEST.values() if e.status == status]

    def by_lead_ai(self, lead_ai: str) -> List[EntityManifestEntry]:
        return [e for e in ENTITY_MANIFEST.values() if e.lead_ai == lead_ai]

    def all_entities(self) -> List[EntityManifestEntry]:
        return list(ENTITY_MANIFEST.values())

    def summary(self) -> dict:
        statuses: Dict[str, int] = {}
        pillars: Dict[str, int] = {}
        for e in ENTITY_MANIFEST.values():
            statuses[e.status] = statuses.get(e.status, 0) + 1
            pillars[e.pillar.value] = pillars.get(e.pillar.value, 0) + 1
        return {
            "total_entities": len(ENTITY_MANIFEST),
            "by_status": statuses,
            "by_pillar": pillars,
        }


_manifest: Optional[PlatformManifest] = None


def get_manifest() -> PlatformManifest:
    global _manifest
    if _manifest is None:
        _manifest = PlatformManifest()
    return _manifest
