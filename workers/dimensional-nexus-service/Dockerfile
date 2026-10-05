FROM python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b
# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
# Copy vendored Dimensionals.nexus + its transitive deps (Dimensionals.infinity.nomenclature/
# abac/rbac) — vendored locally under this build context because the compose build context
# is ./workers/dimensional-nexus-service, isolated from the repo-root Dimensionals/ package
# worker.py used to import unconditionally. Keep in sync with Dimensionals/nexus/,
# Dimensionals/infinity/{nomenclature,abac,rbac}.py.
COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY --chown=worker:worker worker.py .
COPY --chown=worker:worker Dimensionals/ ./Dimensionals/

# Security: drop to non-root user
USER worker

EXPOSE 8050
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8050/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8050"]
