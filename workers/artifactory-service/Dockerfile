FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

WORKDIR /app

RUN groupadd -r artifactory && useradd -r -g artifactory artifactory

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=artifactory:artifactory . /app/Dimensional/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER artifactory

EXPOSE 8047

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8047/health', timeout=4).read()"

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8047"]
