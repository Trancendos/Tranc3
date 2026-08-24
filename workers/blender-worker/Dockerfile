FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3

# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

# Attempt to install Blender (non-fatal if unavailable in this base image)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        blender \
        libgl1 \
        libglib2.0-0 \
        libxrender1 \
        libxi6 \
    && rm -rf /var/lib/apt/lists/* \
    || (echo "WARNING: blender not available in apt — worker will start in degraded mode" && \
        rm -rf /var/lib/apt/lists/*)

WORKDIR /app
COPY --chown=worker:worker requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=worker:worker worker.py .

RUN mkdir -p /app/renders && chown -R worker:worker /app

# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional --build-context observability=../../src/observability .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=worker:worker . /app/Dimensional/
COPY --from=observability --chown=worker:worker . /app/src/observability/
ENV PYTHONPATH=/app
# --- end SFSC ---

# Security: drop to non-root user
USER worker

EXPOSE 8050
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8050/health')" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8050"]
