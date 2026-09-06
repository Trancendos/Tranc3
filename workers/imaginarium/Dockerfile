FROM python:3.11-slim@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    adduser --disabled-password --gecos "" appuser
COPY main.py .
# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=appuser:appuser . /app/Dimensional/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER appuser
EXPOSE 8064
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8064\")}/health')"
CMD ["python", "main.py"]
