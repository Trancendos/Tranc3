FROM python:3.12-slim@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217

WORKDIR /app

RUN groupadd -r litellm && useradd -r -g litellm litellm

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

RUN mkdir -p /app/data && chown -R litellm:litellm /app/data

# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=litellm:litellm . /app/Dimensional/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER litellm

EXPOSE 8049

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8049\")}/health', timeout=4).read()"

CMD ["python", "worker.py"]
