FROM python:3.11-slim

LABEL maintainer="Trancendos"
LABEL description="Tranc3 AI Worker — self-hosted replacement for Cloudflare Worker"

WORKDIR /app

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY worker.py .

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "worker.py"]
