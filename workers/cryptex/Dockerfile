FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf
WORKDIR /app
COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY . .
RUN mkdir -p /data && addgroup --system appgroup && adduser --system --ingroup appgroup appuser && chown -R appuser:appgroup /app /data
# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=appuser:appuser . /app/Dimensional/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER appuser
EXPOSE 8053
# Shell form so ${CRYPTEX_PORT} is expanded at runtime. The exec form cannot
# read the environment, so the previous `--port 8039` was fixed at build time
# while compose published 8053:8053 and set CRYPTEX_PORT=8053 — the app listened
# on 8039 and every request to cryptex:8053 reached nothing. Compose is the
# source of truth for the port; the default here only applies if it sets none.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; p=os.getenv('CRYPTEX_PORT','8053'); urllib.request.urlopen(f'http://localhost:{p}/health', timeout=4).read()"
CMD uvicorn worker:app --host 0.0.0.0 --port ${CRYPTEX_PORT:-8053}
