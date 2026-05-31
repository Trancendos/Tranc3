#!/usr/bin/env python3
"""One-shot: replace hardcoded health entity dicts with health_entity_block()."""

from __future__ import annotations

import re
from pathlib import Path

IMPORT_LINE = "from src.entities.health_metadata import health_entity_block\n"

WORKERS = [
    ("workers/infinity-ws/worker.py", 8004, '"infinity-ws"'),
    ("workers/infinity-auth/worker.py", 8005, '"infinity-auth"'),
    ("workers/monitoring/worker.py", 8007, '"monitoring"'),
    ("workers/search-service/worker.py", 8017, '"search-service"'),
    ("workers/queue-service/worker.py", 8022, "WORKER_NAME"),
    ("workers/rate-limit-service/worker.py", 8026, "WORKER_NAME"),
    ("workers/geo-service/worker.py", 8023, "WORKER_NAME"),
    ("workers/health-aggregator/worker.py", 8029, "WORKER_NAME"),
    ("workers/blender-worker/worker.py", 8050, "WORKER_NAME"),
    ("workers/triposr-worker/worker.py", 8051, "WORKER_NAME"),
    ("workers/audit-service/worker.py", 8025, "WORKER_NAME"),
    ("workers/analytics-service/worker.py", 8016, "WORKER_NAME"),
    ("workers/config-service/worker.py", 8020, "WORKER_NAME"),
    ("workers/cron-service/worker.py", 8021, "WORKER_NAME"),
    ("workers/sms-service/worker.py", 8019, "WORKER_NAME"),
    ("workers/notifications/worker.py", 8008, "WORKER_NAME"),
    ("workers/storage-service/worker.py", 8020, "WORKER_NAME"),
    ("workers/email-service/worker.py", 8018, "WORKER_NAME"),
    ("workers/cdn-service/worker.py", 8028, "WORKER_NAME"),
]

ENTITY_RE = re.compile(
    r'"entity":\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\}',
    re.DOTALL,
)


def patch_file(path: Path, port: int, service_expr: str) -> bool:
    text = path.read_text()
    if "health_entity_block" in text:
        return False
    new_block = f'"entity": health_entity_block({port}, {service_expr})'
    new_text, n = ENTITY_RE.subn(new_block, text, count=1)
    if n == 0:
        print(f"  skip (no entity block): {path}")
        return False
    if IMPORT_LINE.strip() not in new_text:
        # After last __future__ import or after module docstring
        if "from __future__ import" in new_text:
            new_text = re.sub(
                r"(from __future__ import[^\n]+\n)",
                r"\1" + IMPORT_LINE,
                new_text,
                count=1,
            )
        else:
            lines = new_text.split("\n", 1)
            insert_at = 0
            if lines[0].startswith('"""') or lines[0].startswith("'''"):
                for i, line in enumerate(lines):
                    if i > 0 and ('"""' in line or "'''" in line):
                        insert_at = i + 1
                        break
            new_text = "\n".join(lines[:insert_at]) + "\n" + IMPORT_LINE + "\n".join(
                lines[insert_at:]
            )
    path.write_text(new_text)
    print(f"  patched: {path}")
    return True


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    count = 0
    for rel, port, svc in WORKERS:
        if patch_file(root / rel, port, svc):
            count += 1
    print(f"Done. {count} files updated.")


if __name__ == "__main__":
    main()
