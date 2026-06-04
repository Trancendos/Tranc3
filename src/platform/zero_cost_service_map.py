"""
Zero-Cost Service Map — Trancendos Platform
=============================================
Canonical mapping of every platform entity to its zero-cost open-source
foundation. Every entry is verified free-as-in-beer for self-hosted use.

Cost verification key:
  ✅ FREE  = Open source, self-hosted, zero runtime cost
  ⚠️  CHECK = Verify free tier limits before production use
  ❌ PAID  = NOT allowed — must be replaced

All 43 entities map ONLY to ✅ FREE foundations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ZeroCostFoundation:
    name: str
    license: str
    github_url: str
    docker_image: str
    self_hosted_free: bool
    notes: str
    has_api: bool = True
    adaptive_rotation_supported: bool = True


# ---------------------------------------------------------------------------
# Zero-cost foundation registry
# ---------------------------------------------------------------------------

FOUNDATIONS: Dict[str, ZeroCostFoundation] = {
    # AI / Inference
    "ollama": ZeroCostFoundation(
        name="Ollama",
        license="MIT",
        github_url="https://github.com/ollama/ollama",
        docker_image="ollama/ollama:latest",
        self_hosted_free=True,
        notes="Local LLM serving: Llama3, Mistral, Phi-3, Gemma2, CodeLlama. Zero inference cost.",
    ),
    "comfyui": ZeroCostFoundation(
        name="ComfyUI",
        license="GPL-3.0",
        github_url="https://github.com/comfyanonymous/ComfyUI",
        docker_image="ghcr.io/ai-dock/comfyui:latest",
        self_hosted_free=True,
        notes="Image generation pipeline. SD 1.5, SDXL, Flux — all free weights available.",
    ),
    "qdrant": ZeroCostFoundation(
        name="Qdrant",
        license="Apache-2.0",
        github_url="https://github.com/qdrant/qdrant",
        docker_image="qdrant/qdrant:latest",
        self_hosted_free=True,
        notes="Self-hosted vector DB. Replaces in-memory FAISS for production.",
    ),
    # Workflow
    "n8n": ZeroCostFoundation(
        name="n8n",
        license="Fair-code (self-host free)",
        github_url="https://github.com/n8n-io/n8n",
        docker_image="n8nio/n8n:latest",
        self_hosted_free=True,
        notes="Visual workflow automation. 400+ integrations. Enhances The Digital Grid.",
    ),
    # Knowledge / Docs
    "outline": ZeroCostFoundation(
        name="Outline",
        license="BSL 1.1 (self-host free)",
        github_url="https://github.com/outline/outline",
        docker_image="outlinewiki/outline:latest",
        self_hosted_free=True,
        notes="The Library — wiki and knowledge base.",
    ),
    "paperless_ngx": ZeroCostFoundation(
        name="Paperless-ngx",
        license="GPL-3.0",
        github_url="https://github.com/paperless-ngx/paperless-ngx",
        docker_image="ghcr.io/paperless-ngx/paperless-ngx:latest",
        self_hosted_free=True,
        notes="DocUtari — document management and OCR.",
    ),
    # Design
    "penpot": ZeroCostFoundation(
        name="Penpot",
        license="MPL-2.0",
        github_url="https://github.com/penpot/penpot",
        docker_image="penpotapp/frontend:latest",
        self_hosted_free=True,
        notes="Fabulousa — self-hosted Figma alternative. Full design system support.",
    ),
    # Scheduling
    "cal_com": ZeroCostFoundation(
        name="Cal.com",
        license="AGPL-3.0",
        github_url="https://github.com/calcom/cal.com",
        docker_image="calcom/cal.com:latest",
        self_hosted_free=True,
        notes="ChronosSphere/ArcStream — scheduling and time management.",
    ),
    # Security
    "wazuh": ZeroCostFoundation(
        name="Wazuh",
        license="GPL-2.0",
        github_url="https://github.com/wazuh/wazuh",
        docker_image="wazuh/wazuh-manager:latest",
        self_hosted_free=True,
        notes="Cryptex — SIEM, threat detection, vulnerability scanning.",
    ),
    "misp": ZeroCostFoundation(
        name="MISP",
        license="AGPL-3.0",
        github_url="https://github.com/MISP/MISP",
        docker_image="misp/misp:latest",
        self_hosted_free=True,
        notes="Cryptex — threat intelligence platform, CVE feeds.",
    ),
    # CI/CD
    "forgejo": ZeroCostFoundation(
        name="Forgejo",
        license="GPL-3.0",
        github_url="https://codeberg.org/forgejo/forgejo",
        docker_image="codeberg.org/forgejo/forgejo:latest",
        self_hosted_free=True,
        notes="The Workshop — self-hosted git forge and CI/CD.",
    ),
    # Artifacts
    "zot": ZeroCostFoundation(
        name="Zot",
        license="Apache-2.0",
        github_url="https://github.com/project-zot/zot",
        docker_image="ghcr.io/project-zot/zot-linux-amd64:latest",
        self_hosted_free=True,
        notes="The Artifactory — OCI-native container and artifact registry.",
    ),
    # API Gateway
    "gravitee": ZeroCostFoundation(
        name="Gravitee.io Community",
        license="Apache-2.0",
        github_url="https://github.com/gravitee-io/gravitee-api-management",
        docker_image="graviteeio/apim-gateway:latest",
        self_hosted_free=True,
        notes="API Marketplace — REST, webhook, OAuth governance hub.",
    ),
    # 3D / Games
    "godot": ZeroCostFoundation(
        name="Godot Engine",
        license="MIT",
        github_url="https://github.com/godotengine/godot",
        docker_image="barichello/godot-ci:4.2.2",
        self_hosted_free=True,
        notes="TranceFlow — 3D game development and export.",
        has_api=False,
    ),
    "three_js": ZeroCostFoundation(
        name="Three.js",
        license="MIT",
        github_url="https://github.com/mrdoob/three-js",
        docker_image="",  # npm package, no Docker image needed
        self_hosted_free=True,
        notes="VRAR3D — WebGL/WebXR 3D rendering in browser.",
        has_api=False,
    ),
    "aframe": ZeroCostFoundation(
        name="A-Frame",
        license="MIT",
        github_url="https://github.com/aframevr/aframe",
        docker_image="",  # npm package
        self_hosted_free=True,
        notes="VRAR3D — WebXR VR scenes in browser.",
        has_api=False,
    ),
    # Video
    "ffmpeg": ZeroCostFoundation(
        name="FFmpeg",
        license="LGPL-2.1 / GPL-2.0",
        github_url="https://github.com/FFmpeg/FFmpeg",
        docker_image="linuxserver/ffmpeg:latest",
        self_hosted_free=True,
        notes="TateKing — video transcoding and editing pipeline.",
    ),
    # Monitoring
    "grafana": ZeroCostFoundation(
        name="Grafana",
        license="AGPL-3.0",
        github_url="https://github.com/grafana/grafana",
        docker_image="grafana/grafana:latest",
        self_hosted_free=True,
        notes="The Observatory — dashboards and visualisation.",
    ),
    "prometheus": ZeroCostFoundation(
        name="Prometheus",
        license="Apache-2.0",
        github_url="https://github.com/prometheus/prometheus",
        docker_image="prom/prometheus:latest",
        self_hosted_free=True,
        notes="The Observatory — metrics collection.",
    ),
    "loki": ZeroCostFoundation(
        name="Grafana Loki",
        license="AGPL-3.0",
        github_url="https://github.com/grafana/loki",
        docker_image="grafana/loki:latest",
        self_hosted_free=True,
        notes="The Observatory — log aggregation.",
    ),
    "tempo": ZeroCostFoundation(
        name="Grafana Tempo",
        license="AGPL-3.0",
        github_url="https://github.com/grafana/tempo",
        docker_image="grafana/tempo:latest",
        self_hosted_free=True,
        notes="The Observatory — distributed tracing backend for OTel.",
    ),
    # Messaging
    "nats": ZeroCostFoundation(
        name="NATS JetStream",
        license="Apache-2.0",
        github_url="https://github.com/nats-io/nats-server",
        docker_image="nats:latest",
        self_hosted_free=True,
        notes="The HIVE — high-throughput message broker replacing SQLite queues.",
    ),
    # Streaming / Audio
    "liquidsoap": ZeroCostFoundation(
        name="Liquidsoap + Icecast2",
        license="GPL-2.0",
        github_url="https://github.com/savonet/liquidsoap",
        docker_image="savonet/liquidsoap:latest",
        self_hosted_free=True,
        notes="Warp Radio — audio/music streaming platform.",
    ),
    # AI Orchestration
    "langgraph": ZeroCostFoundation(
        name="LangGraph",
        license="MIT",
        github_url="https://github.com/langchain-ai/langgraph",
        docker_image="",  # pip package
        self_hosted_free=True,
        notes="Luminous — stateful AI agent orchestration graphs.",
        has_api=False,
    ),
    "deap": ZeroCostFoundation(
        name="DEAP",
        license="LGPL-3.0",
        github_url="https://github.com/DEAP/deap",
        docker_image="",  # pip package
        self_hosted_free=True,
        notes="Genetic optimizer — NSGA-II evolutionary algorithms.",
        has_api=False,
    ),
    # Secrets
    "vault_hashicorp": ZeroCostFoundation(
        name="HashiCorp Vault",
        license="BSL 1.1 (self-host free)",
        github_url="https://github.com/hashicorp/vault",
        docker_image="vault:latest",
        self_hosted_free=True,
        notes="The Void — self-hosted secrets management with Shamir unseal.",
    ),
    # LMS
    "openedx": ZeroCostFoundation(
        name="OpenedX (Tutor)",
        license="AGPL-3.0",
        github_url="https://github.com/openedx/edx-platform",
        docker_image="overhangio/openedx:latest",
        self_hosted_free=True,
        notes="The Academy — full LMS for Shimshi to power learning paths.",
    ),
}


# ---------------------------------------------------------------------------
# Entity → Foundation mapping
# ---------------------------------------------------------------------------

ENTITY_FOUNDATION_MAP: Dict[str, List[str]] = {
    "the-spark":            ["nats"],
    "the-digital-grid":     ["n8n"],
    "the-void":             ["vault_hashicorp"],
    "the-workshop":         ["forgejo"],
    "infinity":             [],  # custom FastAPI — already implemented
    "the-lighthouse":       [],  # custom Python — already implemented
    "the-hive":             ["nats"],
    "the-nexus":            [],  # custom FastAPI WebSocket — already implemented
    "the-citadel":          ["grafana", "prometheus"],
    "luminous":             ["ollama", "langgraph", "qdrant"],
    "the-observatory":      ["grafana", "prometheus", "loki", "tempo"],
    "royal-bank-of-arcadia": [],  # custom FastAPI — already implemented
    "arcadian-exchange":    [],  # custom FastAPI — already implemented
    "sashas-photo-studio":  ["comfyui"],
    "tranceflow":           ["godot", "three_js"],
    "tateking":             ["ffmpeg"],
    "fabulousa":            ["penpot"],
    "imaginarium":          ["comfyui", "ffmpeg", "godot"],
    "the-studio":           ["comfyui", "ffmpeg"],
    "warp-radio":           ["liquidsoap"],
    "vrar3d":               ["aframe", "three_js"],
    "the-lab":              [],  # custom Python — already implemented
    "think-tank":           [],  # custom Python (qiskit) — already implemented
    "devocity":             ["grafana"],
    "the-library":          ["outline"],
    "the-academy":          ["openedx"],
    "docutari":             ["paperless_ngx"],
    "the-basement":         [],  # custom Python — already implemented
    "turings-hub":          ["ollama"],
    "cryptex":              ["wazuh", "misp"],
    "the-ice-box":          [],  # custom Python sandbox
    "the-warp-tunnel":      [],  # custom Python — already implemented
    "the-artifactory":      ["zot"],
    "api-marketplace":      ["gravitee"],
    "the-town-hall":        [],  # custom FastAPI — already implemented
    "arcadia":              [],  # React SPA — already implemented
    "chronossphere":        ["cal_com"],
    "tranquility":          [],  # custom Python — to implement
    "imind":                ["ollama"],
    "resonate":             ["ollama"],
    "taimra":               ["ollama", "qdrant"],
    "the-dutchy":           ["qdrant"],
}


def get_foundation(entity_id: str) -> List[ZeroCostFoundation]:
    """Return the zero-cost foundations for a given entity."""
    keys = ENTITY_FOUNDATION_MAP.get(entity_id, [])
    return [FOUNDATIONS[k] for k in keys if k in FOUNDATIONS]


def audit_zero_cost() -> dict:
    """Verify all foundations in the map are free."""
    violations = []
    for entity_id, foundation_keys in ENTITY_FOUNDATION_MAP.items():
        for key in foundation_keys:
            f = FOUNDATIONS.get(key)
            if f and not f.self_hosted_free:
                violations.append({"entity": entity_id, "foundation": key})
    return {
        "compliant": len(violations) == 0,
        "violations": violations,
        "total_foundations": len(FOUNDATIONS),
        "total_entity_mappings": len(ENTITY_FOUNDATION_MAP),
    }
