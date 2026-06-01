"""The Town Hall — policy, procedural, ADDD/blueprint templates (cookbooks, bibles, guides)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES_DIR = _ROOT / "config" / "townhall" / "templates"


@dataclass(frozen=True)
class DocumentTemplate:
    id: str
    title: str
    category: str
    framework_id: str
    filename: str

    def path(self) -> Path:
        return _TEMPLATES_DIR / self.filename


# Catalog — maps framework ids to on-disk templates
TEMPLATE_CATALOG: list[DocumentTemplate] = [
    DocumentTemplate("policy", "Policy Document", "policy-documentation", "policy-documentation", "policy.md"),
    DocumentTemplate("procedure", "Procedure / SOP", "procedural-documentation", "procedural-documentation", "procedure.md"),
    DocumentTemplate("add", "Architectural Design Document", "architecture", "add", "architectural_design.md"),
    DocumentTemplate("ddd", "Detailed Design Document", "architecture", "ddd", "detailed_design.md"),
    DocumentTemplate("blueprint", "Blueprint", "architecture", "blueprint", "blueprint.md"),
    DocumentTemplate("security", "Security Framework Assessment", "security", "security-framework", "security_framework.md"),
    DocumentTemplate("legal", "Legal Compliance Checklist", "legal_ip_finance", "legal-compliance", "legal_compliance.md"),
    DocumentTemplate("financial", "Financial Oversight Review", "legal_ip_finance", "financial-oversight", "financial_oversight.md"),
    DocumentTemplate("ip", "Intellectual Property Register Entry", "legal_ip_finance", "intellectual-property", "intellectual_property.md"),
    DocumentTemplate("cookbook", "Operational Cookbook", "documentation", "cookbooks", "cookbook.md"),
    DocumentTemplate("foundation", "Foundation Framework Charter", "architecture", "foundation-framework", "foundation_framework.md"),
    DocumentTemplate("universe", "Trancendos Universe Framework", "architecture", "universe-framework", "universe_framework.md"),
    DocumentTemplate("app-framework", "App per App Framework", "architecture", "app-per-app", "app_per_app.md"),
    DocumentTemplate("design-system", "Design System Template", "architecture", "design-system", "design_system.md"),
    DocumentTemplate("kanban-charter", "Kanban Board Charter", "agile", "kanban", "kanban_charter.md"),
    DocumentTemplate("itil-incident", "ITIL Incident Record", "itsm", "itil4", "itil_incident.md"),
    DocumentTemplate("prince2-stage", "PRINCE2 Stage Gate", "project_management", "prince2-7", "prince2_stage_gate.md"),
]


def list_templates(*, category: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in TEMPLATE_CATALOG:
        if category and t.category != category:
            continue
        out.append(
            {
                "id": t.id,
                "title": t.title,
                "category": t.category,
                "framework_id": t.framework_id,
                "available": t.path().is_file(),
            }
        )
    return out


def get_template(template_id: str) -> DocumentTemplate | None:
    for t in TEMPLATE_CATALOG:
        if t.id == template_id:
            return t
    return None


def render_template(template_id: str, variables: dict[str, str] | None = None) -> str:
    tpl = get_template(template_id)
    if not tpl:
        raise KeyError(f"Unknown template: {template_id}")
    path = tpl.path()
    if not path.is_file():
        raise FileNotFoundError(f"Template file missing: {path}")
    body = path.read_text(encoding="utf-8")
    vars_map = {**(variables or {})}
    for key, value in vars_map.items():
        body = body.replace("{{" + key + "}}", str(value))
    body = re.sub(r"\{\{[^}]+\}\}", "", body)
    return body
