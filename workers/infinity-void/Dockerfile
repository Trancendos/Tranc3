FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4

LABEL maintainer="Trancendos"
LABEL description="The Void — self-hosted encrypted secrets vault (replaces Cloudflare Worker)"

# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app

COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY --chown=worker:worker worker.py .

VOLUME ["/data"]

ENV VOID_DATA_DIR=/data

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

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health', timeout=5).read()" || exit 1

CMD ["python", "worker.py"]
