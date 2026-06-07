"""
Compliance API Routes — Tranc3 / Trancendos Platform

FastAPI router exposing /compliance/* endpoints.

Routes:
    GET /compliance/status          -- live compliance status JSON
    GET /compliance/report          -- full compliance report JSON
    GET /compliance/matrix          -- traceability matrix JSON
    GET /compliance/export/markdown -- download Markdown report
    GET /compliance/export/html     -- download HTML report
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from src.compliance.checker import REGISTER_PATH, load_and_check
from src.compliance.report_generator import generate_html, generate_markdown
from src.compliance.traceability import build_matrix

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["compliance"])


def _get_report():
    """Load and return the compliance report, raising 503 on failure."""
    try:
        return load_and_check(REGISTER_PATH)
    except FileNotFoundError as e:
        logger.error("Compliance register not found: %s", e)
        raise HTTPException(
            status_code=503, detail=f"Compliance register not available: {e}"
        ) from e
    except Exception as e:
        logger.error("Compliance checker error: %s", e)
        raise HTTPException(status_code=500, detail=f"Compliance check failed: {e}") from e


@router.get("/status", summary="Live compliance status")
async def get_compliance_status() -> dict[str, Any]:
    """
    Returns a compact compliance status summary.

    Suitable for health dashboards and monitoring tools.
    """
    report = _get_report()
    counts = report.status_counts
    return {
        "platform": report.platform,
        "classification": report.classification,
        "overall_score": report.overall_score,
        "generated_at": report.generated_at,
        "ci_pass": report.overall_score >= 70.0,
        "status_counts": counts,
        "areas": {
            area_code: {
                "standard": a.standard,
                "total": a.total,
                "compliant": a.compliant,
                "partial": a.partial,
                "planned": a.planned,
                "score_pct": a.score_pct,
            }
            for area_code, a in sorted(report.areas.items())
        },
    }


@router.get("/report", summary="Full compliance report")
async def get_compliance_report() -> dict[str, Any]:
    """Returns the full compliance report including all requirements and evidence."""
    report = _get_report()
    return JSONResponse(content=report.to_dict())


@router.get("/matrix", summary="Traceability matrix")
async def get_traceability_matrix() -> dict[str, Any]:
    """
    Returns the full requirements -> code -> test traceability matrix.

    Also reports orphaned requirements (no evidence) and orphaned tests
    (test files with no requirement mapping).
    """
    report = _get_report()
    return build_matrix(report)


@router.get(
    "/export/markdown",
    summary="Download Markdown compliance report",
    response_class=PlainTextResponse,
)
async def export_markdown() -> PlainTextResponse:
    """Downloads the compliance report as a Markdown document."""
    report = _get_report()
    md = generate_markdown(report)
    return PlainTextResponse(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=compliance_report.md"},
    )


@router.get("/export/html", summary="Download HTML compliance report", response_class=HTMLResponse)
async def export_html() -> HTMLResponse:
    """Downloads a self-contained HTML compliance report (no external deps)."""
    report = _get_report()
    html = generate_html(report)
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": "attachment; filename=compliance_report.html"},
    )


# ── AI Governance endpoints (EU AI Act / ISO 42001 / NIST AI RMF) ─────────────

from pydantic import BaseModel as _BaseModel  # noqa: E402

from src.compliance.ai_governance import (  # noqa: E402
    MODEL_REGISTRY,
    IncidentSeverity,
    classify_risk,
    generate_fairness_report,
    get_ai_incidents,
    log_ai_incident,
    resolve_incident,
)


class _IncidentCreate(_BaseModel):
    model_id: str
    description: str
    severity: IncidentSeverity
    affected_users: int = 0
    reporter: str = "system"


class _IncidentResolve(_BaseModel):
    resolution_notes: str


@router.get("/ai/model-cards", summary="List all AI model cards (EU AI Act Art. 13)")
async def list_model_cards():
    return {"model_cards": [card.model_dump() for card in MODEL_REGISTRY.values()]}


@router.get("/ai/model-cards/{model_id}", summary="Get a single AI model card")
async def get_model_card(model_id: str):
    card = MODEL_REGISTRY.get(model_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not in registry")
    return card.model_dump()


@router.get("/ai/fairness-report", summary="AI fairness & bias report (EU AI Act Art. 15)")
async def ai_fairness_report(model_id: str | None = None):
    return generate_fairness_report(model_id)


@router.post("/ai/fairness-report/run", summary="Trigger a fresh bias measurement run")
async def run_fairness_measurement(model_id: str | None = None):
    # Stub: in production, enqueue a measurement job (e.g. via queue-service)
    return {
        "status": "queued",
        "message": "Bias measurement run queued. Results will populate fairness_metrics on completion.",
        "model_id": model_id or "all",
        "note": "Implement live measurement by connecting to your inference pipeline and test dataset.",
    }


@router.get("/ai/risk-classification", summary="EU AI Act risk tier for all registered models")
async def risk_classification(use_case: str = ""):
    return {
        "classifications": [classify_risk(mid, use_case) for mid in MODEL_REGISTRY],
        "eu_ai_act_version": "2024/1689",
        "assessed_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }


@router.post("/ai/incidents", summary="Log an adverse AI behaviour incident")
async def create_incident(body: _IncidentCreate):
    if body.model_id not in MODEL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Model '{body.model_id}' not in registry")
    incident = log_ai_incident(
        body.model_id, body.description, body.severity, body.affected_users, body.reporter
    )
    return incident.model_dump()


@router.get("/ai/incidents", summary="List AI incidents")
async def list_incidents(model_id: str | None = None, days: int = 30):
    return {"incidents": get_ai_incidents(model_id, days), "days": days}


@router.patch("/ai/incidents/{incident_id}/resolve", summary="Resolve an AI incident")
async def resolve_ai_incident(incident_id: str, body: _IncidentResolve):
    ok = resolve_incident(incident_id, body.resolution_notes)
    if not ok:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"resolved": True, "incident_id": incident_id}


@router.get("/ai/compliance-statement", summary="Machine-readable AI compliance attestation")
async def ai_compliance_statement():
    """Returns a machine-readable compliance attestation for external auditors."""
    report = generate_fairness_report()
    return {
        "platform": "Trancendos",
        "attestation_version": "1.0",
        "generated_at": report["generated_at"],
        "frameworks": {
            "eu_ai_act_2024_1689": {
                "status": "partial",
                "articles_addressed": ["Art. 9", "Art. 13", "Art. 15", "Art. 50"],
                "articles_pending": ["Art. 16 (Registration)", "Art. 17 (Quality Management)"],
                "notes": "Initial governance baseline. Full conformity assessment pending high-risk classification review.",
            },
            "iso_42001_2023": {
                "status": "partial",
                "clauses_addressed": ["§6 Planning", "§8 Operation", "§9 Evaluation"],
                "clauses_pending": ["§10 Improvement", "Certification audit"],
            },
            "nist_ai_rmf_1_0": {
                "status": "partial",
                "functions_addressed": ["GOVERN", "MAP", "MEASURE"],
                "functions_partial": ["MANAGE"],
            },
            "uk_ai_safety_framework": {
                "status": "voluntary_compliance",
                "notes": "Transparency and accountability principles applied. No mandatory obligation.",
            },
        },
        "model_count": len(MODEL_REGISTRY),
        "overall_status": report["overall_status"],
        "compliance_statements": report["compliance_statements"],
    }
