FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3
# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
# Copy vendored Dimensional.nexus + its transitive deps (Dimensional.infinity.nomenclature/
# abac/rbac) — vendored locally under this build context because the compose build context
# is ./workers/dimensional-nexus-service, isolated from the repo-root Dimensional/ package
# worker.py used to import unconditionally. Keep in sync with Dimensional/nexus/,
# Dimensional/infinity/{nomenclature,abac,rbac}.py.
COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY --chown=worker:worker worker.py .
COPY --chown=worker:worker Dimensional/ ./Dimensional/

# Security: drop to non-root user
USER worker

EXPOSE 8050
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8050/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8050"]
