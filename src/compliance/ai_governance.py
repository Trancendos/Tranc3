"""
AI Governance — EU AI Act & ISO 42001 Compliance Baseline
============================================================
Implements initial governance obligations under:
  - EU AI Act (2024/1689): Art. 9 Risk Management, Art. 13 Transparency,
    Art. 15 Accuracy/Robustness/Cybersecurity
  - ISO 42001:2023 — AI Management System (AIMS) requirements
  - NIST AI RMF 1.0 — Govern/Map/Measure/Manage functions
  - UK AI Safety Framework — voluntary compliance baseline

This module provides:
  1. Model registry — structured model cards per AI component
  2. Bias assessment framework — demographic parity, equalised odds stubs
  3. Fairness report generator — periodic/on-demand governance reports
  4. Risk classification — EU AI Act risk tier assignment
  5. Incident log — adverse AI behaviour tracking (SQLite-backed)

Zero-cost: standard library only, no sklearn/fairlearn/pytorch required.
Metric values default to "unmeasured" until a live measurement run populates them.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger("tranc3.compliance.ai_governance")

_DB_PATH = Path(os.environ.get("AI_GOVERNANCE_DB_PATH", "/data/ai_governance.db"))


# ── Enums ─────────────────────────────────────────────────────────────────────


class RiskTier(str, Enum):
    """EU AI Act risk classification (Annex III & Art. 6)."""

    UNACCEPTABLE = "unacceptable"  # Prohibited (Art. 5)
    HIGH = "high"  # Annex III high-risk systems
    LIMITED = "limited"  # Transparency obligations (Art. 50)
    MINIMAL = "minimal"  # General-purpose / no specific risk


class MetricStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNMEASURED = "unmeasured"


class IncidentSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Pydantic models ───────────────────────────────────────────────────────────


class FairnessMetric(BaseModel):
    """A single bias/fairness measurement."""

    value: Optional[float] = None
    threshold: float
    status: MetricStatus = MetricStatus.UNMEASURED
    last_measured: Optional[str] = None
    description: str = ""


class ModelCard(BaseModel):
    """Structured model card (EU AI Act Art. 13 + ISO 42001 §6.1)."""

    model_id: str
    name: str
    version: str
    description: str
    risk_tier: RiskTier
    intended_use: str
    prohibited_uses: List[str] = Field(default_factory=list)
    training_data_sources: List[str] = Field(default_factory=list)
    known_limitations: List[str] = Field(default_factory=list)
    fairness_metrics: Dict[str, FairnessMetric] = Field(default_factory=dict)
    last_audit_date: Optional[str] = None
    next_audit_due: Optional[str] = None
    maintainer: str = "Trancendos Engineering"
    eu_ai_act_articles: List[str] = Field(default_factory=list)
    nist_rmf_functions: List[str] = Field(default_factory=list)


class AIIncident(BaseModel):
    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    model_id: str
    description: str
    severity: IncidentSeverity
    affected_users: int = 0
    reported_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolution_notes: str = ""
    reporter: str = "system"


# ── Model registry ────────────────────────────────────────────────────────────

_NEXT_AUDIT = (datetime.now(timezone.utc) + timedelta(days=90)).date().isoformat()

MODEL_REGISTRY: Dict[str, ModelCard] = {
    "luminous": ModelCard(
        model_id="luminous",
        name="Luminous — Core AI Intelligence Engine",
        version="1.0.0",
        description=(
            "Core AI inference engine (Cornelius MacIntyre). Handles natural language "
            "understanding, consciousness scoring (IIT), and neuromorphic processing. "
            "Primary inference: Ollama (local) → OpenRouter (free) → offline stub."
        ),
        risk_tier=RiskTier.LIMITED,
        intended_use="General-purpose AI assistant for Trancendos platform users",
        prohibited_uses=[
            "Biometric identification of individuals without consent",
            "Real-time remote biometric surveillance in public spaces",
            "Manipulation of vulnerable groups",
        ],
        training_data_sources=[
            "Open-source transformer weights (no proprietary training data)",
            "Ollama local models (user-provided)",
            "OpenRouter free-tier models (third-party, see their model cards)",
        ],
        known_limitations=[
            "Inherits biases from base model training data",
            "No formal fairness evaluation completed — metrics are unmeasured",
            "Consciousness scoring (IIT) is experimental — not clinically validated",
            "Offline stub provides deterministic but non-intelligent responses",
        ],
        fairness_metrics={
            "demographic_parity_difference": FairnessMetric(
                threshold=0.1,
                description="P(positive output | group A) - P(positive output | group B). Target: |diff| < 0.1",
            ),
            "equalised_odds_difference": FairnessMetric(
                threshold=0.1,
                description="max(|TPR_A - TPR_B|, |FPR_A - FPR_B|). Target: < 0.1",
            ),
            "individual_fairness_score": FairnessMetric(
                threshold=0.8,
                description="Cosine similarity of outputs for semantically similar inputs. Target: > 0.8",
            ),
            "calibration_error": FairnessMetric(
                threshold=0.05,
                description="Expected calibration error across output confidence bins. Target: < 0.05",
            ),
        },
        last_audit_date=None,
        next_audit_due=_NEXT_AUDIT,
        eu_ai_act_articles=["Art. 13 (Transparency)", "Art. 50 (Transparency obligations)"],
        nist_rmf_functions=["GOVERN", "MAP", "MEASURE"],
    ),
    "turings_hub": ModelCard(
        model_id="turings_hub",
        name="Turing's Hub — 3D AI Entity Builder",
        version="1.0.0",
        description=(
            "AI entity assembly pipeline (Samantha Turing). Combines personality matrix, "
            "3D body, voice, and memory into fully embodied AI beings (e.g. Imfy, The Dr., George Porter). "
            "Uses LNN (liquid neural network) and SNN-QAT (spiking neural network with quantisation-aware training)."
        ),
        risk_tier=RiskTier.LIMITED,
        intended_use="Building personalised AI entities for Trancendos ecosystem interactions",
        prohibited_uses=[
            "Impersonating real living persons without consent",
            "Creating AI entities designed to deceive users about their AI nature",
            "Generating synthetic identity documents",
        ],
        training_data_sources=[
            "Synthetic personality profiles (procedurally generated)",
            "No real-person biometric data in training",
        ],
        known_limitations=[
            "Personality coherence degrades over long interaction histories",
            "Voice synthesis not yet implemented — placeholder only",
            "3D avatar quality depends on Blender/TripoSR availability",
        ],
        fairness_metrics={
            "personality_representation_balance": FairnessMetric(
                threshold=0.15,
                description="Distribution balance across personality archetypes. No single type > 50%.",
            ),
            "response_consistency_score": FairnessMetric(
                threshold=0.75,
                description="Intra-entity response consistency across equivalent prompts.",
            ),
        },
        last_audit_date=None,
        next_audit_due=_NEXT_AUDIT,
        eu_ai_act_articles=["Art. 13 (Transparency)", "Art. 50 (AI-generated content disclosure)"],
        nist_rmf_functions=["GOVERN", "MAP"],
    ),
    "mlflow_experiments": ModelCard(
        model_id="mlflow_experiments",
        name="MLflow Experiment Tracker (self-hosted)",
        version="1.0.0",
        description=(
            "Trancendos-native MLflow REST API v2 subset (port 8039). Tracks ML experiments "
            "for Turing's Hub and Luminous. Does not perform inference — metadata/metrics store only."
        ),
        risk_tier=RiskTier.MINIMAL,
        intended_use="Internal ML experiment tracking and model performance logging",
        prohibited_uses=["Storing personal data without appropriate access controls"],
        training_data_sources=["N/A — metadata tracker, not a model"],
        known_limitations=["Subset of MLflow REST API only — not all SDK features supported"],
        fairness_metrics={},
        last_audit_date=None,
        next_audit_due=_NEXT_AUDIT,
        eu_ai_act_articles=["Art. 9 (Risk management documentation)"],
        nist_rmf_functions=["GOVERN", "MEASURE"],
    ),
}


# ── SQLite incident log ───────────────────────────────────────────────────────


def _get_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ai_incidents (
            incident_id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            description TEXT NOT NULL,
            severity TEXT NOT NULL,
            affected_users INTEGER DEFAULT 0,
            reported_at TEXT NOT NULL,
            resolved_at TEXT,
            resolution_notes TEXT DEFAULT '',
            reporter TEXT DEFAULT 'system'
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_model ON ai_incidents(model_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_incidents_reported ON ai_incidents(reported_at)")
    conn.commit()
    return conn


def log_ai_incident(
    model_id: str,
    description: str,
    severity: IncidentSeverity,
    affected_users: int = 0,
    reporter: str = "system",
) -> AIIncident:
    """Log an adverse AI behaviour incident."""
    incident = AIIncident(
        model_id=model_id,
        description=description,
        severity=severity,
        affected_users=affected_users,
        reporter=reporter,
    )
    with _get_db() as conn:
        conn.execute(
            """INSERT INTO ai_incidents
               (incident_id, model_id, description, severity, affected_users, reported_at, reporter)
               VALUES (?,?,?,?,?,?,?)""",
            (
                incident.incident_id,
                model_id,
                description,
                severity.value,
                affected_users,
                incident.reported_at,
                reporter,
            ),
        )
    logger.warning(
        "AI incident logged: model=%s severity=%s description=%s",
        sanitize_for_log(model_id),
        sanitize_for_log(severity.value),
        sanitize_for_log(description[:120]),
    )
    return incident


def get_ai_incidents(model_id: Optional[str] = None, days: int = 30) -> List[Dict]:
    """Return incidents within the last N days, optionally filtered by model."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _get_db() as conn:
        if model_id:
            rows = conn.execute(
                "SELECT * FROM ai_incidents WHERE model_id = ? AND reported_at >= ? ORDER BY reported_at DESC",
                (model_id, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ai_incidents WHERE reported_at >= ? ORDER BY reported_at DESC",
                (cutoff,),
            ).fetchall()
    return [dict(r) for r in rows]


def resolve_incident(incident_id: str, resolution_notes: str) -> bool:
    resolved_at = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        cur = conn.execute(
            "UPDATE ai_incidents SET resolved_at = ?, resolution_notes = ? WHERE incident_id = ?",
            (resolved_at, resolution_notes, incident_id),
        )
    return cur.rowcount > 0


# ── Risk classification ───────────────────────────────────────────────────────


def classify_risk(model_id: str, use_case: str = "") -> Dict[str, Any]:
    """Return EU AI Act risk tier for a model + use_case combination."""
    card = MODEL_REGISTRY.get(model_id)
    base_tier = card.risk_tier if card else RiskTier.MINIMAL

    # Escalation rules (non-exhaustive — extend as use cases are confirmed)
    escalation_keywords = {
        RiskTier.HIGH: [
            "biometric",
            "credit scoring",
            "employment screening",
            "law enforcement",
            "critical infrastructure",
            "medical diagnosis",
            "education assessment",
        ],
        RiskTier.UNACCEPTABLE: [
            "subliminal manipulation",
            "social scoring",
            "real-time biometric surveillance",
            "exploit vulnerability",
            "mass surveillance",
        ],
    }
    use_lower = use_case.lower()
    for tier, keywords in escalation_keywords.items():
        if any(kw in use_lower for kw in keywords):
            base_tier = tier
            break

    return {
        "model_id": model_id,
        "use_case": use_case,
        "risk_tier": base_tier.value,
        "eu_ai_act_annex_iii": base_tier == RiskTier.HIGH,
        "requires_conformity_assessment": base_tier == RiskTier.HIGH,
        "transparency_obligation": base_tier in (RiskTier.HIGH, RiskTier.LIMITED),
        "justification": (
            f"Base tier for '{model_id}' is {base_tier.value}. "
            + ("Use-case escalation applied." if use_case else "No use-case provided.")
        ),
    }


# ── Fairness report ───────────────────────────────────────────────────────────


def generate_fairness_report(model_id: Optional[str] = None) -> Dict[str, Any]:
    """Generate a structured fairness and compliance report."""
    target_models = (
        {model_id: MODEL_REGISTRY[model_id]}
        if model_id and model_id in MODEL_REGISTRY
        else MODEL_REGISTRY
    )

    model_reports = {}
    overall_statuses = []

    for mid, card in target_models.items():
        metrics_summary = {}
        for metric_name, metric in card.fairness_metrics.items():
            metrics_summary[metric_name] = {
                "value": metric.value,
                "threshold": metric.threshold,
                "status": metric.status.value,
                "last_measured": metric.last_measured,
                "description": metric.description,
            }
            overall_statuses.append(metric.status)

        recent_incidents = get_ai_incidents(mid, days=30)
        model_reports[mid] = {
            "model_name": card.name,
            "risk_tier": card.risk_tier.value,
            "fairness_metrics": metrics_summary,
            "known_limitations": card.known_limitations,
            "recent_incidents_30d": len(recent_incidents),
            "last_audit_date": card.last_audit_date,
            "next_audit_due": card.next_audit_due,
        }

    unmeasured = sum(1 for s in overall_statuses if s == MetricStatus.UNMEASURED)
    failed = sum(1 for s in overall_statuses if s == MetricStatus.FAIL)
    overall = (
        "action_required" if failed > 0 else ("measurement_needed" if unmeasured > 0 else "pass")
    )

    return {
        "report_id": str(uuid.uuid4()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models_assessed": list(target_models.keys()),
        "overall_status": overall,
        "model_reports": model_reports,
        "compliance_statements": {
            "eu_ai_act": {
                "art_9_risk_management": "Model registry maintained; risk tiers assigned",
                "art_13_transparency": "Model cards published via /compliance/ai/model-cards",
                "art_15_accuracy": f"Fairness metrics defined; {unmeasured} unmeasured (requires live data)",
            },
            "iso_42001": {
                "clause_6_planning": "Risk classification and model cards in place",
                "clause_8_operation": "Incident logging active; audit schedule set quarterly",
                "clause_9_evaluation": "Fairness report endpoint operational",
            },
            "nist_ai_rmf": {
                "govern": "AI governance module active; incident log operational",
                "map": "Model cards identify intended use, limitations, and risk tier",
                "measure": f"{len(overall_statuses) - unmeasured}/{len(overall_statuses)} metrics measured",
                "manage": "Incident resolution workflow available via API",
            },
        },
        "recommendations": [
            f"Run bias measurement suite to populate {unmeasured} unmeasured metrics"
            if unmeasured > 0
            else None,
            "Schedule first formal AI audit within next_audit_due dates",
            "Review prohibited_uses list against actual deployment use cases",
            "Consider high-risk classification review if deploying in regulated sectors",
        ],
        "next_review_due": _NEXT_AUDIT,
    }
