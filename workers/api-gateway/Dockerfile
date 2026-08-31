FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5

LABEL maintainer="Trancendos"
LABEL description="Trancendos API Gateway — self-hosted replacement for Cloudflare Worker"

# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app

COPY --chown=worker:worker workers/api-gateway/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY --chown=worker:worker workers/api-gateway/sanitize.py workers/api-gateway/worker.py ./

# Security: drop to non-root user
USER worker

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health', timeout=5).read()" || exit 1

CMD ["python", "worker.py"]
