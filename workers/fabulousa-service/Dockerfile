FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5

WORKDIR /app

RUN groupadd -r fabulousa && useradd -r -g fabulousa fabulousa

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=fabulousa:fabulousa . /app/Dimensional/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER fabulousa

EXPOSE 8048

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8048\")}/health', timeout=4).read()"

CMD ["python", "worker.py"]
