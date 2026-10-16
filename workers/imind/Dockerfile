FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    adduser --disabled-password --gecos "" appuser
COPY worker.py .
RUN mkdir -p /app/data && chown appuser:appuser /app/data
# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensionals --build-context observability=../../src/observability .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=appuser:appuser . /app/Dimensionals/
COPY --from=observability --chown=appuser:appuser . /app/src/observability/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER appuser
EXPOSE 8075
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8075/health')"
CMD ["python", "worker.py"]
