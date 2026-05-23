# src/registry/file_registry.py
# FID: TRANC3-REG-001 | Version: 1.0.0 | Module: Registry
# TRANC3 File Identity & Registry System
# Every file in the platform is registered here with FID, version, hash, and metadata.

import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

# Registry signing key — used to detect tampering
_REGISTRY_KEY = os.getenv(
    "REGISTRY_SIGNING_KEY", os.getenv("SECRET_KEY", "tranc3-registry-key")
)


@dataclass
class FileRecord:
    """Complete identity record for a TRANC3 file."""

    fid: str  # e.g. TRANC3-CORE-001
    path: str  # relative path from project root
    module: str  # e.g. "core", "security", "billing"
    description: str
    version: str  # semver e.g. "1.0.0"
    revision: int  # increments on every change
    created_at: str
    updated_at: str
    author: str = "TRANC3-System"
    status: str = "active"  # active | deprecated | experimental | research
    dependencies: List[str] = field(default_factory=list)  # FIDs this file depends on
    tags: List[str] = field(default_factory=list)
    sha256: Optional[str] = None  # computed at runtime
    signature: Optional[str] = None  # HMAC of sha256+fid+version
    tampered: bool = False


# ── Master Registry ───────────────────────────────────────────────────────────
# Every file in the project is listed here.
# Format: FID -> FileRecord

REGISTRY: Dict[str, FileRecord] = {
    # ── Entry Points ──────────────────────────────────────────────────────────
    "TRANC3-ENTRY-001": FileRecord(
        fid="TRANC3-ENTRY-001",
        path="api.py",
        module="entry",
        description="Production FastAPI application — main entry point. Wires all subsystems.",
        version="2.0.0",
        revision=12,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        dependencies=[
            "TRANC3-AUTH-001",
            "TRANC3-CORE-001",
            "TRANC3-BILL-001",
            "TRANC3-OBS-001",
        ],
        tags=["api", "fastapi", "production", "entry"],
    ),
    "TRANC3-ENTRY-002": FileRecord(
        fid="TRANC3-ENTRY-002",
        path="auth.py",
        module="entry",
        description="JWT authentication, token management, FastAPI dependency injection.",
        version="1.2.0",
        revision=5,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        dependencies=["TRANC3-AUTH-001"],
        tags=["auth", "jwt", "security"],
    ),
    "TRANC3-ENTRY-003": FileRecord(
        fid="TRANC3-ENTRY-003",
        path="train.py",
        module="entry",
        description="Fine-tuning pipeline for TRANC3 model on personality profiles.",
        version="1.0.0",
        revision=2,
        created_at="2026-04-22",
        updated_at="2026-04-22",
        dependencies=["TRANC3-CORE-003"],
        tags=["training", "ml", "fine-tuning"],
    ),
    "TRANC3-ENTRY-004": FileRecord(
        fid="TRANC3-ENTRY-004",
        path="main_2060.py",
        module="entry",
        description="TRANC3 2060 master orchestrator — integrates all 2060 subsystems.",
        version="5.0.0",
        revision=3,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        status="experimental",
        dependencies=[
            "TRANC3-QUANT-001",
            "TRANC3-BIO-001",
            "TRANC3-EVOL-001",
            "TRANC3-DIST-001",
            "TRANC3-HOLO-001",
        ],
        tags=["2060", "orchestrator", "experimental"],
    ),
    # ── Core AI ───────────────────────────────────────────────────────────────
    "TRANC3-CORE-001": FileRecord(
        fid="TRANC3-CORE-001",
        path="src/core/advanced_model.py",
        module="core",
        description="Advanced transformer with rotary embeddings, gated FFN, consciousness-weighted attention.",
        version="2.0.0",
        revision=4,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        tags=["transformer", "model", "rotary", "attention"],
    ),
    "TRANC3-CORE-002": FileRecord(
        fid="TRANC3-CORE-002",
        path="src/core/multilingual_tokenizer.py",
        module="core",
        description="Multilingual tokenizer supporting 50+ languages via mBERT backbone.",
        version="1.1.0",
        revision=3,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        tags=["tokenizer", "multilingual", "nlp"],
    ),
    "TRANC3-CORE-003": FileRecord(
        fid="TRANC3-CORE-003",
        path="src/core/dataset.py",
        module="core",
        description="MultilingualDataset for fine-tuning on personality profiles.",
        version="1.0.0",
        revision=1,
        created_at="2026-04-22",
        updated_at="2026-04-22",
        tags=["dataset", "training", "multilingual"],
    ),
    "TRANC3-CORE-004": FileRecord(
        fid="TRANC3-CORE-004",
        path="src/core/feature_flags.py",
        module="core",
        description="Redis-backed feature flag system with per-user rollout support.",
        version="1.0.0",
        revision=2,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["feature-flags", "redis", "rollout"],
    ),
    "TRANC3-CORE-005": FileRecord(
        fid="TRANC3-CORE-005",
        path="src/core/context_compressor.py",
        module="core",
        description="Conversation context compressor — extends effective context window.",
        version="1.0.0",
        revision=1,
        created_at="2026-04-22",
        updated_at="2026-04-22",
        tags=["context", "compression", "nlp"],
    ),
    # ── Bio-Neural ────────────────────────────────────────────────────────────
    "TRANC3-BIO-001": FileRecord(
        fid="TRANC3-BIO-001",
        path="src/bio_neural/consciousness_engine.py",
        module="bio_neural",
        description="IIT 4.0 consciousness engine — Φ score, Global Workspace Theory, self-awareness.",
        version="2.0.0",
        revision=5,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        tags=["consciousness", "iit", "phi", "gwt"],
    ),
    "TRANC3-BIO-002": FileRecord(
        fid="TRANC3-BIO-002",
        path="src/bio_neural/neuromorphic.py",
        module="bio_neural",
        description="Spiking Neural Network with LIF neurons and STDP learning.",
        version="1.0.0",
        revision=3,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["snn", "neuromorphic", "lif", "stdp"],
    ),
    # ── Quantum ───────────────────────────────────────────────────────────────
    "TRANC3-QUANT-001": FileRecord(
        fid="TRANC3-QUANT-001",
        path="src/quantum/quantum_core.py",
        module="quantum",
        description="Quantum-classical hybrid core — QFT attention, Grover search, classical fallback.",
        version="1.1.0",
        revision=4,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["quantum", "qiskit", "attention", "grover"],
    ),
    "TRANC3-QUANT-002": FileRecord(
        fid="TRANC3-QUANT-002",
        path="src/quantum/quantum_engine.py",
        module="quantum",
        description="Full quantum engine — circuit builder, memory system, VQE optimisation.",
        version="1.0.0",
        revision=2,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        tags=["quantum", "vqe", "memory", "circuits"],
    ),
    # ── Evolution ─────────────────────────────────────────────────────────────
    "TRANC3-EVOL-001": FileRecord(
        fid="TRANC3-EVOL-001",
        path="src/evolution/self_improving_core.py",
        module="evolution",
        description="Genetic algorithm self-evolution engine with Redis genome persistence.",
        version="1.1.0",
        revision=4,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["evolution", "genetic", "fitness", "redis"],
    ),
    # ── Distributed ───────────────────────────────────────────────────────────
    "TRANC3-DIST-001": FileRecord(
        fid="TRANC3-DIST-001",
        path="src/distributed/swarm_intelligence.py",
        module="distributed",
        description="Distributed swarm intelligence with neural consensus and blockchain recording.",
        version="1.1.0",
        revision=5,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["swarm", "distributed", "consensus"],
    ),
    "TRANC3-DIST-002": FileRecord(
        fid="TRANC3-DIST-002",
        path="src/distributed/intelligence_blockchain.py",
        module="distributed",
        description="Simplified blockchain for AI computation auditability + HomomorphicCrypto.",
        version="1.0.0",
        revision=2,
        created_at="2026-04-22",
        updated_at="2026-04-22",
        tags=["blockchain", "crypto", "audit", "privacy"],
    ),
    "TRANC3-DIST-003": FileRecord(
        fid="TRANC3-DIST-003",
        path="src/distributed/swarm_coordinator.py",
        module="distributed",
        description="HTTP-based swarm coordinator for multi-node distributed inference.",
        version="1.0.0",
        revision=1,
        created_at="2026-04-22",
        updated_at="2026-04-22",
        tags=["swarm", "http", "coordinator"],
    ),
    # ── Holographic ───────────────────────────────────────────────────────────
    "TRANC3-HOLO-001": FileRecord(
        fid="TRANC3-HOLO-001",
        path="src/holographic/memory_crystal.py",
        module="holographic",
        description="6D holographic memory crystal — FFT-based associative recall.",
        version="1.1.0",
        revision=4,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        tags=["holographic", "memory", "fft", "6d"],
    ),
    # ── Security ──────────────────────────────────────────────────────────────
    "TRANC3-SEC-001": FileRecord(
        fid="TRANC3-SEC-001",
        path="src/security/security_framework.py",
        module="security",
        description="Full security framework — JWT, bcrypt, rate limiting, audit logging, input sanitisation.",
        version="1.0.0",
        revision=3,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        tags=["security", "jwt", "bcrypt", "audit", "sanitisation"],
    ),
    "TRANC3-SEC-002": FileRecord(
        fid="TRANC3-SEC-002",
        path="src/security/middleware.py",
        module="security",
        description="FastAPI security headers middleware and governance middleware.",
        version="1.0.0",
        revision=2,
        created_at="2026-04-22",
        updated_at="2026-04-22",
        tags=["middleware", "headers", "csp", "hsts"],
    ),
    # ── Auth ──────────────────────────────────────────────────────────────────
    "TRANC3-AUTH-001": FileRecord(
        fid="TRANC3-AUTH-001",
        path="src/auth/db_user_manager.py",
        module="auth",
        description="DB-backed user manager with password strength validation and SQLAlchemy persistence.",
        version="1.0.0",
        revision=3,
        created_at="2026-04-22",
        updated_at="2026-04-22",
        dependencies=["TRANC3-DB-001"],
        tags=["auth", "database", "users", "bcrypt"],
    ),
    # ── Database ──────────────────────────────────────────────────────────────
    "TRANC3-DB-001": FileRecord(
        fid="TRANC3-DB-001",
        path="src/database/schema.py",
        module="database",
        description="SQLAlchemy schema — users, conversations, messages, feedback, evolution events.",
        version="1.0.0",
        revision=3,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        tags=["database", "sqlalchemy", "schema", "postgresql"],
    ),
    "TRANC3-DB-002": FileRecord(
        fid="TRANC3-DB-002",
        path="src/database/vector_store.py",
        module="database",
        description="Vector store abstraction — Pinecone or in-memory fallback for embeddings.",
        version="1.0.0",
        revision=1,
        created_at="2026-04-22",
        updated_at="2026-04-22",
        tags=["vector", "pinecone", "embeddings", "gdpr"],
    ),
    # ── Monetisation ──────────────────────────────────────────────────────────
    "TRANC3-BILL-001": FileRecord(
        fid="TRANC3-BILL-001",
        path="src/monetisation/billing.py",
        module="monetisation",
        description="Tier enforcement, Stripe integration, passive revenue tracker.",
        version="1.0.0",
        revision=3,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["billing", "stripe", "tiers", "revenue"],
    ),
    # ── Analytics ─────────────────────────────────────────────────────────────
    "TRANC3-ANAL-001": FileRecord(
        fid="TRANC3-ANAL-001",
        path="src/analytics/predictive.py",
        module="analytics",
        description="Predictive analytics — intent, churn, quality scoring, load forecasting.",
        version="1.0.0",
        revision=2,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["analytics", "churn", "intent", "quality"],
    ),
    # ── Adaptive ──────────────────────────────────────────────────────────────
    "TRANC3-ADAP-001": FileRecord(
        fid="TRANC3-ADAP-001",
        path="src/adaptive/foresight.py",
        module="adaptive",
        description="Foresight engine — trajectory prediction, adaptive generation parameters.",
        version="1.0.0",
        revision=2,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["foresight", "trajectory", "adaptive", "prediction"],
    ),
    # ── Observability ─────────────────────────────────────────────────────────
    "TRANC3-OBS-001": FileRecord(
        fid="TRANC3-OBS-001",
        path="src/observability/metrics.py",
        module="observability",
        description="Prometheus metrics, structlog logging, OTEL integration.",
        version="1.0.0",
        revision=2,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["prometheus", "grafana", "otel", "logging"],
    ),
    # ── Personality ───────────────────────────────────────────────────────────
    "TRANC3-PERS-001": FileRecord(
        fid="TRANC3-PERS-001",
        path="src/personality/matrix.py",
        module="personality",
        description="Personality matrix — 5 profiles, 12D trait vectors, emotion modulation.",
        version="1.0.0",
        revision=3,
        created_at="2026-04-20",
        updated_at="2026-04-22",
        tags=["personality", "emotion", "traits", "profiles"],
    ),
    # ── Compliance ────────────────────────────────────────────────────────────
    "TRANC3-COMP-001": FileRecord(
        fid="TRANC3-COMP-001",
        path="src/compliance/magna_carta.py",
        module="compliance",
        description="Magna Carta compliance framework hooks — activates when config provided.",
        version="1.0.0",
        revision=1,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["compliance", "magna-carta", "gdpr"],
    ),
    # ── Nanoservices ──────────────────────────────────────────────────────────
    "TRANC3-NANO-001": FileRecord(
        fid="TRANC3-NANO-001",
        path="src/nanoservices/nano_registry.py",
        module="nanoservices",
        description="Nanoservice registry — 13 capabilities with health tracking and routing.",
        version="1.0.0",
        revision=1,
        created_at="2026-04-21",
        updated_at="2026-04-22",
        tags=["nanoservices", "registry", "routing"],
    ),
    # ── Research ──────────────────────────────────────────────────────────────
    "TRANC3-RES-001": FileRecord(
        fid="TRANC3-RES-001",
        path="src/research/bci_interface.py",
        module="research",
        description="Brain-Computer Interface abstraction stub — 2035+ target.",
        version="0.1.0",
        revision=1,
        created_at="2026-04-22",
        updated_at="2026-04-22",
        status="research",
        tags=["bci", "research", "2060", "experimental"],
    ),
}


# ── Registry Engine ───────────────────────────────────────────────────────────


class FileRegistry:
    """
    Runtime file registry with integrity verification.
    Computes SHA-256 of each file and signs with HMAC to detect tampering.
    """

    def __init__(self, project_root: str = "."):
        self.root = Path(project_root)
        self.records = REGISTRY
        self._verified: Dict[str, bool] = {}

    def compute_sha256(self, path: str) -> Optional[str]:
        full = self.root / path
        if not full.exists():
            return None
        h = hashlib.sha256()
        with open(full, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def sign(self, sha256: str, fid: str, version: str) -> str:
        msg = f"{sha256}:{fid}:{version}".encode()
        return hmac.new(_REGISTRY_KEY.encode(), msg, hashlib.sha256).hexdigest()

    def verify(self, fid: str) -> Dict:
        record = self.records.get(fid)
        if not record:
            return {"fid": fid, "status": "unknown", "error": "FID not in registry"}

        current_sha = self.compute_sha256(record.path)
        if current_sha is None:
            return {"fid": fid, "status": "missing", "path": record.path}

        record.sha256 = current_sha
        expected_sig = self.sign(current_sha, fid, record.version)
        record.signature = expected_sig

        # If a stored signature exists, compare
        stored_sig = os.getenv(f"TRANC3_SIG_{fid.replace('-','_')}")
        if stored_sig and stored_sig != expected_sig:
            record.tampered = True
            logger.warning(  # codeql[py/cleartext-logging]
                "INTEGRITY ALERT: %s (%s) signature mismatch — possible tampering",
                sanitize_for_log(fid), sanitize_for_log(record.path),
            )
            return {
                "fid": fid,
                "status": "tampered",
                "path": record.path,
                "version": record.version,
            }

        self._verified[fid] = True
        return {
            "fid": fid,
            "status": "verified",
            "path": record.path,
            "version": record.version,
            "revision": record.revision,
            "sha256": current_sha[:16] + "...",
            "signature": expected_sig[:16] + "...",
        }

    def verify_all(self) -> Dict:
        results = {fid: self.verify(fid) for fid in self.records}
        tampered = [fid for fid, r in results.items() if r.get("status") == "tampered"]
        missing = [fid for fid, r in results.items() if r.get("status") == "missing"]
        verified = [fid for fid, r in results.items() if r.get("status") == "verified"]
        return {
            "total": len(self.records),
            "verified": len(verified),
            "missing": missing,
            "tampered": tampered,
            "results": results,
        }

    def get_by_module(self, module: str) -> List[FileRecord]:
        return [r for r in self.records.values() if r.module == module]

    def get_by_tag(self, tag: str) -> List[FileRecord]:
        return [r for r in self.records.values() if tag in r.tags]

    def get_dependency_tree(self, fid: str, depth: int = 0) -> Dict:
        record = self.records.get(fid)
        if not record or depth > 5:
            return {}
        return {
            "fid": fid,
            "path": record.path,
            "version": record.version,
            "deps": [
                self.get_dependency_tree(d, depth + 1) for d in record.dependencies
            ],
        }

    def export_manifest(self) -> str:
        manifest = {
            "generated_at": datetime.utcnow().isoformat(),
            "total_files": len(self.records),
            "files": {
                fid: {
                    "path": r.path,
                    "module": r.module,
                    "version": r.version,
                    "revision": r.revision,
                    "status": r.status,
                    "sha256": r.sha256,
                    "tags": r.tags,
                }
                for fid, r in self.records.items()
            },
        }
        return json.dumps(manifest, indent=2)

    def lookup(self, path: str) -> Optional[FileRecord]:
        """Find a record by file path."""
        for r in self.records.values():
            if r.path == path:
                return r
        return None


# Singleton
registry = FileRegistry()
