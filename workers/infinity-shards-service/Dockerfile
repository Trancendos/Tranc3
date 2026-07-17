FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/infinity-shards-service/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker workers/infinity-shards-service/worker.py .
# worker.py imports src.database.encrypted_sqlite, which itself imports
# src.errors.error_catalog - both vendored from the repo-root build context
# (context: . per docker-compose.production.yml), not duplicated locally.
COPY --chown=worker:worker src/__init__.py src/__init__.py
COPY --chown=worker:worker src/database/ src/database/
COPY --chown=worker:worker src/errors/ src/errors/

RUN mkdir -p data && chown -R worker:worker data

USER worker
EXPOSE 8045
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8045/health || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8045"]
