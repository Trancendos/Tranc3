#!/usr/bin/env python3
"""Ensure P0 worker Dockerfiles build from repo root with src/ + observability."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.production.yml"

# worker_dir, port, extra COPY lines (repo-root paths)
P0_WORKERS: list[tuple[str, int, list[str]]] = [
    ("tranc3-ai", 8001, []),
    ("infinity-void", 8002, []),
    (
        "api-gateway",
        8003,
        ["COPY --chown=worker:worker Dimensional/sanitize.py ./Dimensional/sanitize.py"],
    ),
    ("infinity-ws", 8004, []),
    ("infinity-auth", 8005, ["COPY --chown=worker:worker shared_core/ ./shared_core/"]),
    ("users-service", 8006, []),
    ("monitoring", 8007, []),
    ("notifications", 8008, []),
    ("infinity-ai", 8009, []),
    ("products-service", 8011, []),
    ("orders-service", 8012, []),
    ("payments-service", 8013, []),
]


def _dockerfile(worker: str, port: int, extras: list[str]) -> str:
    extra_block = "\n".join(extras)
    init_py = (
        "RUN mkdir -p src/observability Dimensional 2>/dev/null; "
        "touch src/__init__.py src/entities/__init__.py src/observability/__init__.py; "
        "[ -f Dimensional/sanitize.py ] && touch Dimensional/__init__.py || true"
    )
    return f"""FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl \\
  && rm -rf /var/lib/apt/lists/* \\
  && groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/{worker}/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker workers/{worker}/worker.py .
COPY --chown=worker:worker src/entities/ ./src/entities/
COPY --chown=worker:worker src/observability/prometheus_mount.py ./src/observability/prometheus_mount.py
{extra_block}
{init_py}
USER worker
EXPOSE {port}
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\
  CMD curl -f http://localhost:{port}/health || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "{port}"]
"""


def _patch_compose(text: str, worker: str) -> str:
    pattern = (
        rf"(  {re.escape(worker)}:\n"
        rf"    <<: \*worker-platform\n"
        rf"    build:\n)"
        rf"      context: \./workers/{re.escape(worker)}\n"
        rf"      dockerfile: Dockerfile"
    )
    repl = (
        rf"\1\n"
        rf"      context: .\n"
        rf"      dockerfile: workers/{worker}/Dockerfile"
    )
    return re.sub(pattern, repl, text, count=1)


def main() -> int:
    for worker, port, extras in P0_WORKERS:
        path = ROOT / "workers" / worker / "Dockerfile"
        path.write_text(_dockerfile(worker, port, extras))
        print(f"Wrote {path}")

    text = COMPOSE.read_text()
    for worker, _, _ in P0_WORKERS:
        text = _patch_compose(text, worker)
    COMPOSE.write_text(text)
    print(f"Patched {COMPOSE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
