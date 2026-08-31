FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/infinity-portal-service/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker workers/infinity-portal-service/ .
# service.py imports Dimensional.infinity.* (nomenclature, auth_gateway,
# owasp_hardening, rbac, sentinel_station, worker_integration) and
# Dimensional.dimensionals - vendored from the repo-root build context
# (context: . per docker-compose.production.yml), not duplicated locally.
COPY --chown=worker:worker Dimensional/ ./Dimensional/

RUN mkdir -p data && chown -R worker:worker data

USER worker
EXPOSE 8042
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8042/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8042"]
