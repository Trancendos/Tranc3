FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5

WORKDIR /app

RUN addgroup --system lab && adduser --system --ingroup lab lab

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY config.py models.py database.py service.py router.py main.py ./

RUN mkdir -p /data && chown lab:lab /data

# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=lab:lab . /app/Dimensional/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER lab

EXPOSE 8066

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8066/health', timeout=4).read()"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8066"]
