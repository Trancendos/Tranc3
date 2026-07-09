# Build context is the repo root (see docker-compose.production.yml: context: ".",
# dockerfile: workers/backup-service/Dockerfile) because worker.py imports
# src.backup.* and src.entities.* — those packages must be present in the image
# alongside worker.py. worker.py itself does no sys.path manipulation, so it (and
# src/) are copied flat into /app: Python adds the script's own directory to
# sys.path[0] at startup, and src/ resolves as a subdirectory of that.
FROM python:3.11-slim

RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app

COPY workers/backup-service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/backup-service/worker.py worker.py
COPY src/__init__.py src/__init__.py
COPY src/backup/ src/backup/
COPY src/entities/ src/entities/
COPY src/database/ src/database/
COPY src/errors/ src/errors/
COPY src/observability/ src/observability/

RUN mkdir -p /app/data && chown -R worker:worker /app/data

USER worker

EXPOSE 8078
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8078\")}/health')"

CMD ["python", "worker.py"]
