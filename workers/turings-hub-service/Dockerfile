FROM python:3.11-slim@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker worker.py .

# VRM, animation, and portrait assets (populated at runtime or via volume mount)
RUN mkdir -p assets/vrm assets/animations assets/portraits \
  && chown -R worker:worker assets/

RUN mkdir -p src/personality src/entities 2>/dev/null; \
    touch src/__init__.py src/personality/__init__.py src/entities/__init__.py

# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional --build-context observability=../../src/observability .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=worker:worker . /app/Dimensional/
COPY --from=observability --chown=worker:worker . /app/src/observability/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER worker
EXPOSE 8058
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8058/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8058"]
