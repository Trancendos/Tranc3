# Build context is the repo root (see docker-compose.production.yml: context: ".",
# dockerfile: workers/ice-box-service/Dockerfile) because worker.py imports
# src.security.ice_box.* and src.security.warp_tunnel.* — those packages must be
# present in the image alongside worker.py.
FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3

RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app

COPY workers/ice-box-service/requirements.txt workers/ice-box-service/requirements.txt
RUN pip install --no-cache-dir -r workers/ice-box-service/requirements.txt

COPY workers/ice-box-service/worker.py workers/ice-box-service/worker.py
COPY src/__init__.py src/__init__.py
COPY src/security/__init__.py src/security/__init__.py
COPY src/security/ice_box/ src/security/ice_box/
COPY src/security/warp_tunnel/ src/security/warp_tunnel/
COPY src/observability/worker_setup.py src/observability/worker_setup.py

RUN mkdir -p /app/workers/ice-box-service/data && chown -R worker:worker /app/workers/ice-box-service/data

USER worker
WORKDIR /app/workers/ice-box-service

EXPOSE 8046
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8046\")}/health')"

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8046"]
