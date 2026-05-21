FROM python:3.11-slim

LABEL maintainer="Trancendos"
LABEL description="The Void — self-hosted encrypted secrets vault (replaces Cloudflare Worker)"

WORKDIR /app

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY worker.py .

VOLUME ["/data"]

ENV VOID_DATA_DIR=/data

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8002/health || exit 1

CMD ["python", "worker.py"]
