#!/usr/bin/env python3
"""Generate docs/DOC_INDEX.md and inject category frontmatter into all docs.

This script is idempotent: it only adds frontmatter to files that do not
already have a YAML frontmatter block, and DOC_INDEX.md is fully regenerated
each run from the current docs/ tree.

Categories follow the canonical documentation hierarchy:
  Getting Started, Architecture, Development, Deployment,
  Security, Operations, Reference
"""
from __future__ import annotations

import os
import re
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_ROOT = os.path.join(REPO_ROOT, "docs")
INDEX_PATH = os.path.join(DOCS_ROOT, "DOC_INDEX.md")

CATEGORIES = [
    "Getting Started",
    "Architecture",
    "Development",
    "Deployment",
    "Security",
    "Operations",
    "Reference",
]

# Directory fragment -> category (first match wins, checked in order).
DIR_RULES = [
    ("architecture", "Architecture"),
    ("runbooks", "Operations"),
    ("services", "Reference"),
    ("compliance", "Security"),
    ("policies", "Security"),
    ("privacy", "Security"),
    ("defstan", "Security"),
    ("engineering", "Development"),
    ("procedures", "Operations"),
    ("governance", "Reference"),
    ("framework", "Reference"),
    ("reference", "Reference"),
    ("cab", "Reference"),
    ("templates", "Reference"),
    ("evidence", "Reference"),
    ("solution-packs", "Reference"),
]

# Top-level docs/<file>.md overrides (by basename).
TOPLEVEL_RULES = {
    "API_REFERENCE.md": "Reference",
    "DEPLOYMENT_GUIDE.md": "Deployment",
    "DEPLOYMENT_INDEX.md": "Deployment",
    "DEPLOYMENT_RUNBOOK.md": "Operations",
    "DESIGN_SYSTEM.md": "Development",
    "GO_LIVE_GAP_ANALYSIS.md": "Deployment",
    "HOSTIPC_RISK_ACCEPTANCE.md": "Security",
    "PRODUCTION_ROADMAP.md": "Deployment",
    "RESEARCH_FINDINGS.md": "Architecture",
    "SECURITY-ASSESSMENT.md": "Security",
    "SECURITY_RESEARCH_FINDINGS.md": "Security",
    "THE_TOWN_HALL.md": "Reference",
    "WIKI_INDEX.md": "Reference",
    "01-MAGNACARTA-FOUNDATION.md": "Reference",
    "change-request-process.md": "Development",
    "credential-rotation-advisory.md": "Security",
    "vault_security.md": "Security",
}

# Repo-root markdown files that belong in the index.
ROOT_FILES = {
    "README.md": "Getting Started",
    "CLAUDE.md": "Reference",
    "PLATFORM_ENTITIES.md": "Reference",
    "ARCHITECTURE_THREAT_MODEL.md": "Security",
    "SECURITY.md": "Security",
    "SECURITY_ALERT_REGISTER.md": "Security",
    "CODE_OF_CONDUCT.md": "Development",
}

# Docs explicitly known to be accurate/authoritative → status "complete".
COMPLETE_ALLOWLIST = {
    "docs/API_REFERENCE.md",
    "docs/DEPLOYMENT_GUIDE.md",
    "docs/WIKI_INDEX.md",
    "README.md",
    "CLAUDE.md",
    "PLATFORM_ENTITIES.md",
    "ARCHITECTURE_THREAT_MODEL.md",
    "SECURITY.md",
    "SECURITY_ALERT_REGISTER.md",
}


def git_last_reviewed(rel_path: str) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", rel_path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return out or "2026-08-21"
    except Exception:
        return "2026-08-21"


def categorize(rel_path: str) -> str:
    norm = rel_path.replace(os.sep, "/")
    if norm.startswith("docs/"):
        body = norm[len("docs/"):]
        if "/" not in body:  # top-level docs/<file>.md
            return TOPLEVEL_RULES.get(body, "Reference")
        for frag, cat in DIR_RULES:
            if frag in norm:
                return cat
        return "Reference"
    return "Reference"


def extract_title(path: str, fallback: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^#\s+(.+?)\s*$", line)
                if m:
                    return m.group(1).strip()
    except Exception:
        pass
    return fallback


def has_frontmatter(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        stripped = content.lstrip()
        return stripped.startswith("---")
    except Exception:
        return False


def inject_frontmatter(path: str, rel_path: str) -> bool:
    """Add frontmatter if missing. Returns True if a change was made."""
    if has_frontmatter(path):
        return False
    title = extract_title(path, rel_path)
    category = categorize(rel_path)
    last_reviewed = git_last_reviewed(rel_path)
    status = "complete" if rel_path in COMPLETE_ALLOWLIST else "needs-update"
    block = (
        "---\n"
        f'title: "{title}"\n'
        f"category: {category}\n"
        f"last-reviewed: {last_reviewed}\n"
        f"status: {status}\n"
        "---\n\n"
    )
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(block + content)
    return True


def collect_docs() -> list[tuple[str, str, str, str]]:
    """Return list of (rel_path, title, category, status) sorted by category then path."""
    entries = []
    # docs/ tree
    for dirpath, _dirs, files in os.walk(DOCS_ROOT):
        for name in files:
            if not name.endswith(".md"):
                continue
            if name == "DOC_INDEX.md":
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
            entries.append((rel, full))
    # root markdown files
    for name, cat in ROOT_FILES.items():
        full = os.path.join(REPO_ROOT, name)
        if os.path.exists(full):
            rel = name
            entries.append((rel, full))
    result = []
    for rel, full in entries:
        title = extract_title(full, rel)
        # re-extract title ignoring any newly added frontmatter
        category = categorize(rel)
        status = "complete" if rel in COMPLETE_ALLOWLIST else "needs-update"
        result.append((category, rel, title, status))
    result.sort(key=lambda e: (CATEGORIES.index(e[0]), e[1].lower()))
    return result


def write_index(entries: list[tuple[str, str, str, str]]) -> None:
    lines = []
    lines.append("# Trancendos Documentation Index\n")
    lines.append(
        "Canonical navigation hub for all Trancendos documentation. "
        "Documents are organized into the logical hierarchy below.\n"
    )
    lines.append(
        "> **Status legend:** `complete` = reviewed and accurate · "
        "`wip` = work in progress · `needs-update` = accuracy not yet verified "
        "(see the documentation audit / alignment tasks).\n"
    )
    # Quick links
    lines.append("## Quick Links\n")
    lines.append("| Task | Start here |")
    lines.append("|------|-----------|")
    quick = [
        ("Deploy", "Deployment", "docs/DEPLOYMENT_GUIDE.md"),
        ("Develop", "Development", "docs/DESIGN_SYSTEM.md"),
        ("Debug", "Operations", "docs/runbooks/"),
        ("Secure", "Security", "SECURITY-ASSESSMENT.md"),
    ]
    for label, _cat, target in quick:
        lines.append(f"| {label} | [{target}]({target}) |")
    lines.append("")

    # Category sections
    for cat in CATEGORIES:
        cat_entries = [e for e in entries if e[0] == cat]
        if not cat_entries:
            continue
        lines.append(f"## {cat}\n")
        lines.append("| Document | Category | Status |")
        lines.append("|----------|-----------|--------|")
        for _category, rel, title, status in cat_entries:
            disp = title if title else rel
            lines.append(f"| [{disp}]({rel}) | {cat} | {status} |")
        lines.append("")

    lines.append("---\n")
    lines.append(
        "_This index is generated by `scripts/generate_doc_index.py`. "
        "Run it after adding or moving docs to refresh the navigation hub and "
        "frontmatter metadata._\n"
    )
    with open(INDEX_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> None:
    changed = 0
    for dirpath, _dirs, files in os.walk(DOCS_ROOT):
        for name in files:
            if not name.endswith(".md") or name == "DOC_INDEX.md":
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")
            if inject_frontmatter(full, rel):
                changed += 1
    # root files frontmatter (optional, skip README to avoid altering entry point)
    for name in ROOT_FILES:
        if name == "README.md":
            continue
        full = os.path.join(REPO_ROOT, name)
        if os.path.exists(full) and inject_frontmatter(full, name):
            changed += 1
    entries = collect_docs()
    write_index(entries)
    print(f"Injected frontmatter into {changed} file(s).")
    print(f"Indexed {len(entries)} documents into DOC_INDEX.md.")


if __name__ == "__main__":
    main()
