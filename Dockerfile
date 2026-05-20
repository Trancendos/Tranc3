# TRANC3 Backend — Docker image
# Runs: FastAPI main app + Nanoservices server + Worker processes
#
# Build:  docker build -t tranc3 .
# Run:    docker run -p 8000:8000 -p 8001:8001 --env-file .env tranc3
# Fly.io: fly deploy  (uses this Dockerfile automatically)

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps — remove build tools after install to reduce attack surface
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl \
  && rm -rf /var/lib/apt/lists/*

# Security: non-root user
RUN groupadd -r tranc3 && useradd -r -g tranc3 -d /app -s /sbin/nologin tranc3

WORKDIR /app

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install onnxruntime for ONNX inference (lighter than full torch on edge)
RUN pip install --no-cache-dir onnxruntime==1.18.0

# Copy application with correct ownership
COPY --chown=tranc3:tranc3 . .

# Create runtime directories (model weights mounted from Fly.io persistent volume)
RUN mkdir -p models/tranc3-v1 models/tokenizer data/vector_store cache logs \
    && chown -R tranc3:tranc3 /app

# Entrypoint handles migrations then starts servers
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Drop to non-root
USER tranc3

# Expose main API + nanoservices
EXPOSE 8000 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Override CMD for worker-only mode: CMD ["python", "-m", "src.workers.inference_worker"]
ENTRYPOINT ["docker-entrypoint.sh"]
