FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4
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
EXPOSE 8061
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8061\")}/health')"
CMD ["python", "main.py"]
