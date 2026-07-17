FROM python:3.11-slim
# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/infinity-admin-service/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
# worker.py is a thin shim importing app from main.py, which in turn imports
# config/database/models/service/router from this same directory - copying
# only worker.py left every one of those imports unresolvable.
COPY --chown=worker:worker workers/infinity-admin-service/config.py workers/infinity-admin-service/database.py workers/infinity-admin-service/models.py workers/infinity-admin-service/service.py workers/infinity-admin-service/router.py workers/infinity-admin-service/main.py workers/infinity-admin-service/worker.py .
# Include platform entity registry so the admin service can resolve names
COPY --chown=worker:worker src/entities/ ./src/entities/
# service.py/router.py import Dimensional.dimensionals and Dimensional.infinity.*
# - vendored from the repo-root build context (context: . per
# docker-compose.production.yml), not duplicated locally.
COPY --chown=worker:worker Dimensional/ ./Dimensional/
RUN mkdir -p /app/data \
    && chown -R worker:worker /app/data
# Security: drop to non-root user
USER worker

EXPOSE 8044
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8044/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8044"]
