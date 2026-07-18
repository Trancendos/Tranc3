FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/gateway-service/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
# worker.py is a thin shim importing app from main.py, which in turn imports
# config/database/models/service/router from this same directory - copying
# only worker.py left every one of those imports unresolvable.
COPY --chown=worker:worker workers/gateway-service/config.py workers/gateway-service/database.py workers/gateway-service/models.py workers/gateway-service/service.py workers/gateway-service/router.py workers/gateway-service/main.py workers/gateway-service/worker.py .
# service.py/router.py/main.py import Dimensional.dimensionals and
# Dimensional.infinity.* - vendored from the repo-root build context
# (context: . — see docker-compose.production.yml note if/when this service
# is wired in), not duplicated locally.
COPY --chown=worker:worker Dimensional/ ./Dimensional/

RUN mkdir -p data && chown -R worker:worker data

USER worker
EXPOSE 8040
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8040/health || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8040"]
