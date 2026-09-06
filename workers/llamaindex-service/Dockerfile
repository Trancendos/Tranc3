FROM python:3.11-slim@sha256:1042b61448fef4ba92d16a8c7eb4996d027568ce64792a7877fd88511e0af7c6
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=worker:worker worker.py .
RUN mkdir -p /app/data && chown -R worker:worker /app/data
# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=worker:worker . /app/Dimensional/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER worker

EXPOSE 8096
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8096/health')" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8096"]
