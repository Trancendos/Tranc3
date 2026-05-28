FROM python:3.11-slim

LABEL maintainer="Trancendos"
LABEL description="Trancendos API Gateway — self-hosted replacement for Cloudflare Worker"

# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app

COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir --upgrade "pip>=25.3" "setuptools>=78.1.1" "wheel>=0.46.2" \
    && pip install --no-cache-dir -r requirements-worker.txt

COPY --chown=worker:worker worker.py .

# Security: drop to non-root user
USER worker

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8003/health || exit 1

CMD ["python", "worker.py"]
