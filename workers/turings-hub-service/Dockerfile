FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/turings-hub-service/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker workers/turings-hub-service/worker.py .

# VRM, animation, and portrait assets (populated at runtime or via volume mount)
RUN mkdir -p assets/vrm assets/animations assets/portraits \
  && chown -R worker:worker assets/

RUN mkdir -p src/personality src/entities 2>/dev/null; \
    touch src/__init__.py src/personality/__init__.py src/entities/__init__.py

USER worker
EXPOSE 8035
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8035/health || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8035"]
