FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928
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
