FROM python:3.12-slim@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217

WORKDIR /app

RUN addgroup --system vrar3d && adduser --system --ingroup vrar3d vrar3d

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py models.py database.py service.py router.py main.py ./
COPY static/ ./static/

RUN mkdir -p /data/assets && chown vrar3d:vrar3d /data /data/assets

# --- Shared Functional Services Core (SFSC) — named build contexts ---
# Not copied into this directory — there is one copy of the core, at the
# repo root. Supplied by docker-compose.production.yml, or for a direct
#   docker build --build-context sharedcore=../../Dimensional .
# See scripts/apply_shared_core_contexts.py for why this is not a base image.
COPY --from=sharedcore --chown=vrar3d:vrar3d . /app/Dimensional/
ENV PYTHONPATH=/app
# --- end SFSC ---

USER vrar3d

EXPOSE 8060

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8060/health', timeout=4).read()"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8060"]
