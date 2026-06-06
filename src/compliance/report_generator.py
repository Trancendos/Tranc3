"""
Compliance Report Generator — Tranc3 / Trancendos Platform

Generates JSON, Markdown, and self-contained HTML compliance reports
from a ComplianceReport object produced by checker.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.compliance.checker import ComplianceReport

STATUS_COLOURS = {
    "COMPLIANT": "#22c55e",
    "PARTIAL": "#f59e0b",
    "PLANNED": "#3b82f6",
    "WAIVED": "#a855f7",
    "NA": "#6b7280",
}

STATUS_EMOJI = {
    "COMPLIANT": "PASS",
    "PARTIAL": "PART",
    "PLANNED": "PLAN",
    "WAIVED": "WAIV",
    "NA": "N/A ",
}


def generate_json(report: "ComplianceReport") -> str:
    """Return full compliance report as JSON string."""
    return json.dumps(report.to_dict(), indent=2)


def generate_markdown(report: "ComplianceReport") -> str:
    """Return full compliance report as Markdown string."""
    lines: list[str] = []

    lines.append("# DEFSTAN Compliance Report")
    lines.append("")
    lines.append(f"**Platform:** {report.platform}")
    lines.append(f"**Classification:** {report.classification}")
    lines.append(f"**Generated:** {report.generated_at}")
    lines.append(f"**Register Version:** {report.register_version}")
    lines.append("")

    # Overall score
    score = report.overall_score
    lines.append("## Overall Compliance Score")
    lines.append("")
    lines.append(f"**{score:.1f}%**")
    lines.append("")

    # Status counts
    counts = report.status_counts
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    for s, n in counts.items():
        lines.append(f"| {s} | {n} |")
    lines.append("")

    # Per-area breakdown
    lines.append("## Compliance by Standard Area")
    lines.append("")
    lines.append("| Area | Standard | Total | Compliant | Partial | Planned | Score |")
    lines.append("|------|----------|-------|-----------|---------|---------|-------|")
    for area_code in sorted(report.areas.keys()):
        a = report.areas[area_code]
        lines.append(
            f"| {a.area} | {a.standard} | {a.total} | {a.compliant} | "
            f"{a.partial} | {a.planned} | {a.score_pct:.1f}% |"
        )
    lines.append("")

    # Requirements table
    lines.append("## Requirements Register")
    lines.append("")
    lines.append("| ID | Standard | Title | Status | Evidence |")
    lines.append("|----|----------|-------|--------|----------|")
    for r in sorted(report.requirements, key=lambda x: x.req_id):
        ev_count = len(r.evidence_checks)
        ev_ok = sum(1 for e in r.evidence_checks if e.exists)
        ev_str = f"{ev_ok}/{ev_count}" if ev_count > 0 else "none"
        lines.append(f"| {r.req_id} | {r.standard} | {r.title} | {r.status} | {ev_str} |")
    lines.append("")

    # Traceability matrix
    lines.append("## Traceability Matrix")
    lines.append("")
    for r in sorted(report.requirements, key=lambda x: x.req_id):
        lines.append(f"### {r.req_id} — {r.title}")
        lines.append("")
        lines.append(f"**Status:** {r.status}")
        lines.append(f"**Standard:** {r.standard}")
        if r.notes:
            lines.append(f"**Notes:** {r.notes}")
        lines.append("")
        if r.evidence_checks:
            lines.append("**Evidence:**")
            for e in r.evidence_checks:
                exists_mark = "OK" if e.exists else "MISSING"
                lines.append(f"- `{e.path}` [{exists_mark}] — {e.description}")
        else:
            lines.append("**Evidence:** None recorded")
        lines.append("")

    # Waivers
    if report.waivers:
        lines.append("## Active Waivers")
        lines.append("")
        for w in report.waivers:
            if w.get("status") == "ACTIVE":
                lines.append(f"### {w.get('waiver_id')} — {w.get('title')}")
                lines.append(f"**Requirement:** {w.get('requirement_id')}")
                lines.append(f"**Risk Level:** {w.get('risk_level')}")
                lines.append(f"**Expiry:** {w.get('expiry_date')}")
                lines.append(f"**Rationale:** {w.get('rationale', '')}")
                controls = w.get("compensating_controls", [])
                if controls:
                    lines.append("**Compensating Controls:**")
                    for c in controls:
                        lines.append(f"- {c}")
                lines.append("")

    return "\n".join(lines)


def generate_html(report: "ComplianceReport") -> str:
    """
    Generate a self-contained HTML compliance report.
    No external dependencies — all styles inline.
    """
    score = report.overall_score
    counts = report.status_counts

    # Build donut SVG
    donut_svg = _build_donut_svg(score)

    # Build per-area rows
    area_rows = ""
    for area_code in sorted(report.areas.keys()):
        a = report.areas[area_code]
        score_col = _score_badge(a.score_pct)
        area_rows += f"""
        <tr>
          <td><strong>{a.area}</strong></td>
          <td>{a.standard}</td>
          <td>{a.total}</td>
          <td>{a.compliant}</td>
          <td>{a.partial}</td>
          <td>{a.planned}</td>
          <td>{score_col}</td>
        </tr>"""

    # Build requirements rows
    req_rows = ""
    for r in sorted(report.requirements, key=lambda x: x.req_id):
        badge = _status_badge(r.status)
        ev_items = (
            "".join(
                f'<li class="ev-{"ok" if e.exists else "missing"}">'
                f"<code>{e.path}</code> — {e.description}</li>"
                for e in r.evidence_checks
            )
            or "<li>No evidence recorded</li>"
        )
        req_rows += f"""
        <tr>
          <td><code>{r.req_id}</code></td>
          <td>{r.standard}</td>
          <td>{r.title}</td>
          <td>{badge}</td>
          <td><ul class="ev-list">{ev_items}</ul></td>
        </tr>"""

    # Status summary cards
    status_cards = ""
    for s in ["COMPLIANT", "PARTIAL", "PLANNED", "WAIVED", "NA"]:
        n = counts.get(s, 0)
        colour = STATUS_COLOURS.get(s, "#6b7280")
        status_cards += f"""
        <div class="stat-card" style="border-left: 4px solid {colour}">
          <div class="stat-num" style="color:{colour}">{n}</div>
          <div class="stat-label">{s}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DEFSTAN Compliance Report — {report.platform}</title>
<style>
  :root {{
    --bg: #0a0a0f;
    --surface: #111118;
    --border: #1f1f2e;
    --text: #e2e8f0;
    --muted: #64748b;
    --green: #22c55e;
    --amber: #f59e0b;
    --blue: #3b82f6;
    --purple: #a855f7;
    --gray: #6b7280;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif;
         font-size: 14px; line-height: 1.6; padding: 2rem; }}
  h1 {{ font-size: 1.6rem; font-weight: 700; margin-bottom: 0.25rem; color: #f8fafc; }}
  h2 {{ font-size: 1.1rem; font-weight: 600; color: #cbd5e1; margin: 2rem 0 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
  h3 {{ font-size: 0.95rem; color: #94a3b8; margin: 0.25rem 0; }}
  .meta {{ color: var(--muted); font-size: 0.8rem; margin-bottom: 2rem; }}
  .top-grid {{ display: grid; grid-template-columns: auto 1fr; gap: 2rem; align-items: center; margin-bottom: 2rem; }}
  .stats-grid {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
  .stat-card {{ background: var(--surface); border-radius: 8px; padding: 1rem 1.5rem; min-width: 110px; }}
  .stat-num {{ font-size: 1.8rem; font-weight: 700; }}
  .stat-label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-top: 0.2rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; }}
  th {{ text-align: left; padding: 0.6rem 0.75rem; font-size: 0.75rem; text-transform: uppercase;
        letter-spacing: 0.05em; color: var(--muted); border-bottom: 1px solid var(--border); }}
  td {{ padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
  tr:hover td {{ background: rgba(255,255,255,0.02); }}
  code {{ background: rgba(255,255,255,0.06); padding: 0.1em 0.4em; border-radius: 4px; font-size: 0.8em; }}
  .badge {{ display: inline-block; padding: 0.2em 0.6em; border-radius: 4px; font-size: 0.7rem;
            font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }}
  .badge-COMPLIANT {{ background: rgba(34,197,94,0.15); color: #22c55e; }}
  .badge-PARTIAL {{ background: rgba(245,158,11,0.15); color: #f59e0b; }}
  .badge-PLANNED {{ background: rgba(59,130,246,0.15); color: #3b82f6; }}
  .badge-WAIVED {{ background: rgba(168,85,247,0.15); color: #a855f7; }}
  .badge-NA {{ background: rgba(107,114,128,0.15); color: #6b7280; }}
  .score-badge {{ font-weight: 700; }}
  .ev-list {{ list-style: none; font-size: 0.8rem; }}
  .ev-list li {{ padding: 0.15rem 0; }}
  .ev-ok::before {{ content: "OK "; color: var(--green); font-weight: 600; }}
  .ev-missing::before {{ content: "MISSING "; color: #ef4444; font-weight: 600; }}
  .score-gauge {{ font-size: 2rem; font-weight: 800; text-align: center; }}
  .score-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted); text-align: center; }}
  footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.75rem; }}
</style>
</head>
<body>
<h1>DEFSTAN Compliance Report</h1>
<p class="meta">
  Platform: {report.platform} &nbsp;&bull;&nbsp;
  Classification: {report.classification} &nbsp;&bull;&nbsp;
  Generated: {report.generated_at} &nbsp;&bull;&nbsp;
  Register v{report.register_version}
</p>

<div class="top-grid">
  <div>
    {donut_svg}
    <p class="score-label">Overall Score</p>
  </div>
  <div>
    <h2 style="margin-top:0">Status Summary</h2>
    <div class="stats-grid">{status_cards}</div>
  </div>
</div>

<h2>Compliance by Standard Area</h2>
<table>
  <thead>
    <tr>
      <th>Area</th><th>Standard</th><th>Total</th><th>Compliant</th>
      <th>Partial</th><th>Planned</th><th>Score</th>
    </tr>
  </thead>
  <tbody>{area_rows}</tbody>
</table>

<h2>Requirements Register</h2>
<table>
  <thead>
    <tr>
      <th>ID</th><th>Standard</th><th>Title</th><th>Status</th><th>Evidence</th>
    </tr>
  </thead>
  <tbody>{req_rows}</tbody>
</table>

<footer>
  Tranc3 / Trancendos Platform — DEFSTAN-inspired compliance framework v1.0.0 &nbsp;&bull;&nbsp;
  This is a public application modelled on DEF STAN discipline and rigour &nbsp;&bull;&nbsp;
  UNCLASSIFIED
</footer>
</body>
</html>"""
    return html


def _status_badge(status: str) -> str:
    cls = f"badge badge-{status.upper()}"
    return f'<span class="{cls}">{status}</span>'


def _score_badge(score: float) -> str:
    if score >= 80:
        colour = "#22c55e"
    elif score >= 50:
        colour = "#f59e0b"
    else:
        colour = "#ef4444"
    return f'<span class="score-badge" style="color:{colour}">{score:.1f}%</span>'


def _build_donut_svg(score: float) -> str:
    """Generate a simple SVG donut gauge for the overall score."""
    radius = 45
    circumference = 2 * 3.14159 * radius
    filled = circumference * (score / 100)
    gap = circumference - filled

    if score >= 80:
        colour = "#22c55e"
    elif score >= 50:
        colour = "#f59e0b"
    else:
        colour = "#ef4444"

    return f"""<svg width="120" height="120" viewBox="0 0 120 120" style="display:block;margin:auto">
  <circle cx="60" cy="60" r="{radius}" fill="none" stroke="#1f1f2e" stroke-width="12"/>
  <circle cx="60" cy="60" r="{radius}" fill="none" stroke="{colour}" stroke-width="12"
    stroke-dasharray="{filled:.1f} {gap:.1f}"
    stroke-dashoffset="{circumference * 0.25:.1f}"
    stroke-linecap="round"/>
  <text x="60" y="56" text-anchor="middle" fill="{colour}" font-size="18" font-weight="800"
        font-family="'Segoe UI',system-ui,sans-serif">{score:.0f}%</text>
  <text x="60" y="72" text-anchor="middle" fill="#64748b" font-size="8"
        font-family="'Segoe UI',system-ui,sans-serif">COMPLIANCE</text>
</svg>"""


def save_reports(report: "ComplianceReport", output_dir: Path) -> dict[str, Path]:
    """Save JSON, Markdown, and HTML reports to output_dir. Returns paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    json_path = output_dir / "compliance_report.json"
    json_path.write_text(generate_json(report))
    paths["json"] = json_path

    md_path = output_dir / "compliance_report.md"
    md_path.write_text(generate_markdown(report))
    paths["markdown"] = md_path

    html_path = output_dir / "compliance_report.html"
    html_path.write_text(generate_html(report))
    paths["html"] = html_path

    return paths
