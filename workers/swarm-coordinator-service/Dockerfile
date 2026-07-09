# Build context is the repo root (see docker-compose.production.yml: context: ".",
# dockerfile: workers/swarm-coordinator-service/Dockerfile) because worker.py imports
# src.entities.health_metadata / src.errors.error_catalog and reads config/swarm/ and
# scripts/*.py relative to ROOT = Path(__file__).resolve().parents[2] — that computation
# requires worker.py to sit two directories below the image's repo-root equivalent, so
# the source tree's relative depth is preserved inside the image.
FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/swarm-coordinator-service/requirements-worker.txt workers/swarm-coordinator-service/requirements-worker.txt
RUN pip install --no-cache-dir -r workers/swarm-coordinator-service/requirements-worker.txt
COPY --chown=worker:worker workers/swarm-coordinator-service/worker.py workers/swarm-coordinator-service/worker.py
COPY --chown=worker:worker src/__init__.py src/__init__.py
COPY --chown=worker:worker src/entities/ src/entities/
COPY --chown=worker:worker src/errors/ src/errors/
COPY --chown=worker:worker src/database/ src/database/
COPY --chown=worker:worker config/swarm/ config/swarm/
COPY --chown=worker:worker scripts/swarm_runner.py scripts/health_check.py scripts/entity_registry_audit.py scripts/
RUN mkdir -p /app/logs /app/data && chown -R worker:worker /app/logs /app/data

USER worker
WORKDIR /app/workers/swarm-coordinator-service
# worker.py imports src.entities.* / src.errors.* but never adds ROOT to sys.path
# itself (unlike ice-box-service's worker.py, which does) — with WORKDIR set to
# the worker's own subdirectory for CMD, /app must be added via PYTHONPATH or
# those imports fail with ModuleNotFoundError at startup.
ENV PYTHONPATH=/app

EXPOSE 8109
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8109\")}/health')"

CMD ["python", "worker.py"]
