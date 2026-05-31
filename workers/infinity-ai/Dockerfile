FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/infinity-ai/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker workers/infinity-ai/worker.py .
COPY --chown=worker:worker src/entities/ ./src/entities/
COPY --chown=worker:worker src/observability/prometheus_mount.py ./src/observability/prometheus_mount.py

RUN mkdir -p src/observability Dimensional 2>/dev/null; touch src/__init__.py src/entities/__init__.py src/observability/__init__.py; [ -f Dimensional/sanitize.py ] && touch Dimensional/__init__.py || true
USER worker
EXPOSE 8009
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8009/health || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8009"]
