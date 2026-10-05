FROM python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b
# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
# Copy vendored Dimensionals.hive + its transitive deps (Dimensionals.infinity.nomenclature,
# src.errors.error_catalog) — vendored locally under this build context because the compose
# build context is ./workers/hive-service, isolated from the repo-root Dimensionals/ and src/
# packages worker.py used to import unconditionally. Keep in sync with the source modules
# under Dimensionals/hive/, Dimensionals/infinity/nomenclature.py, src/errors/error_catalog.py.
COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY --chown=worker:worker worker.py .
COPY --chown=worker:worker Dimensionals/ ./Dimensionals/
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
