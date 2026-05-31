FROM python:3.11-slim
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/swarm-coordinator-service/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker workers/swarm-coordinator-service/worker.py .
COPY --chown=worker:worker src/entities/ ./src/entities/
COPY --chown=worker:worker config/swarm/ ./config/swarm/
COPY --chown=worker:worker scripts/swarm_runner.py scripts/health_check.py scripts/entity_registry_audit.py ./scripts/
RUN mkdir -p /app/logs /app/data && chown -R worker:worker /app/logs /app/data

USER worker
EXPOSE 8053
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8053/health || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8053"]
