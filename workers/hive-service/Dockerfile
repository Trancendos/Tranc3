FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3
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

# Security: drop to non-root user
USER worker

EXPOSE 8051
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8051/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8051"]
