FROM python:3.11-slim

LABEL maintainer="Trancendos"
LABEL description="The Void — self-hosted encrypted secrets vault (replaces Cloudflare Worker)"

# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app

COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY --chown=worker:worker worker.py .

VOLUME ["/data"]

ENV VOID_DATA_DIR=/data

# Security: drop to non-root user
USER worker

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8002/health || exit 1

CMD ["python", "worker.py"]
