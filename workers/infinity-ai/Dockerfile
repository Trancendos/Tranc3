FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3
# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
# worker.py is a backwards-compat shim that imports config/database/models/
# service/router/main from this same directory (see worker.py's own
# docstring) — copying only worker.py left every one of those imports
# unresolvable at runtime (ModuleNotFoundError), so the image never
# actually ran despite building successfully.
COPY --chown=worker:worker config.py database.py models.py service.py router.py main.py sanitize.py zero_cost_registry.py worker.py .
# Vendored copy of config/zero_cost/providers.yaml — zero_cost_registry.py reads
# it from a path relative to this file, not the repo-root config/ directory,
# which isn't visible inside this worker's isolated build context.
COPY --chown=worker:worker config/zero_cost/ ./config/zero_cost/
RUN mkdir -p /app/data \
    && chown -R worker:worker /app/data
# Security: drop to non-root user
USER worker

EXPOSE 8009
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8009/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8009"]
