FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4

WORKDIR /app

RUN groupadd -r library && useradd -r -g library library

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY . .

RUN mkdir -p /data && chown library:library /data

# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=library:library . /app/Dimensional/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER library

EXPOSE 8067

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8067/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8067"]
