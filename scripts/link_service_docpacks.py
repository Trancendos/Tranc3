#!/usr/bin/env python3
"""One-time (re-runnable, idempotent) script: insert a CMDB ServiceID
cross-reference into each docs/services/<slug>/README.md that
src/cmdb/service_docpack_map.py confidently maps to a real ServiceID.

Handles the two header formats actually used across the 43 doc-packs:
  1. A "| Field | Value |" metadata table -> inserts a new row.
  2. An inline "**Service:** ... · **Slug:** ..." metadata line -> appends
     to that line.
  3. Neither -> inserts a standalone line right after the H1 title.

Idempotent: does nothing to a file that already contains "ServiceID (CMDB)".
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cmdb.service_docpack_map import DOCPACK_TO_SERVICE_ID  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICES_DOC_DIR = os.path.join(REPO_ROOT, "docs", "services")

_TABLE_HEADER_RE = re.compile(r"^\| Field \| Value \|\n\|---\|---\|\n", re.MULTILINE)
_INLINE_META_RE = re.compile(r"^(\*\*Service:\*\*.*)$", re.MULTILINE)
_H1_RE = re.compile(r"^# .+$", re.MULTILINE)


def _insert_service_id(text: str, service_id: str) -> str | None:
    if "ServiceID (CMDB)" in text:
        return None  # already linked — idempotent no-op

    m = _TABLE_HEADER_RE.search(text)
    if m:
        insert_at = m.end()
        new_row = f"| **ServiceID (CMDB)** | `{service_id}` |\n"
        return text[:insert_at] + new_row + text[insert_at:]

    m = _INLINE_META_RE.search(text)
    if m:
        old_line = m.group(1)
        new_line = old_line + f" · **ServiceID (CMDB):** `{service_id}`"
        return text[: m.start()] + new_line + text[m.end() :]

    m = _H1_RE.search(text)
    if m:
        insert_at = m.end()
        new_line = f"\n\n**ServiceID (CMDB):** `{service_id}`"
        return text[:insert_at] + new_line + text[insert_at:]

    return None  # no recognisable insertion point — leave untouched, report it


def main() -> int:
    updated, skipped_already_linked, skipped_no_insertion_point, missing_file = [], [], [], []

    for slug, service_id in sorted(DOCPACK_TO_SERVICE_ID.items()):
        readme_path = os.path.join(SERVICES_DOC_DIR, slug, "README.md")
        if not os.path.exists(readme_path):
            missing_file.append(slug)
            continue
        with open(readme_path, encoding="utf-8") as f:
            text = f.read()
        if "ServiceID (CMDB)" in text:
            skipped_already_linked.append(slug)
            continue
        new_text = _insert_service_id(text, service_id)
        if new_text is None:
            skipped_no_insertion_point.append(slug)
            continue
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(new_text)
        updated.append(slug)

    print(f"Updated: {len(updated)} -> {updated}")
    print(f"Already linked (no-op): {len(skipped_already_linked)} -> {skipped_already_linked}")
    print(
        f"No recognisable insertion point (needs manual fix): {len(skipped_no_insertion_point)} -> {skipped_no_insertion_point}"
    )
    print(f"README.md missing: {len(missing_file)} -> {missing_file}")
    return 1 if skipped_no_insertion_point or missing_file else 0


if __name__ == "__main__":
    sys.exit(main())
