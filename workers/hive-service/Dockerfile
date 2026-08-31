FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5
# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
# Copy vendored Dimensional.hive + its transitive deps (Dimensional.infinity.nomenclature,
# src.errors.error_catalog) — vendored locally under this build context because the compose
# build context is ./workers/hive-service, isolated from the repo-root Dimensional/ and src/
# packages worker.py used to import unconditionally. Keep in sync with the source modules
# under Dimensional/hive/, Dimensional/infinity/nomenclature.py, src/errors/error_catalog.py.
COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY --chown=worker:worker worker.py .
COPY --chown=worker:worker Dimensional/ ./Dimensional/
COPY --chown=worker:worker src/ ./src/

# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context observability=../../src/observability .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=observability --chown=worker:worker . /app/src/observability/
ENV PYTHONPATH=/app
# --- end SFSC ---

# Security: drop to non-root user
USER worker

EXPOSE 8051
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8051/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8051"]
