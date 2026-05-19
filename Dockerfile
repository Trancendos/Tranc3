# TRANC3 Backend — Docker image
# Runs: FastAPI main app + Nanoservices server + Worker processes
#
# Build:  docker build -t tranc3 .
# Run:    docker run -p 8000:8000 -p 8001:8001 --env-file .env tranc3
# Fly.io: fly deploy  (uses this Dockerfile automatically)

FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install onnxruntime for ONNX inference (lighter than full torch on edge)
RUN pip install --no-cache-dir onnxruntime==1.18.0

# Copy application
COPY . .

# Create runtime directories (model weights mounted from Fly.io persistent volume)
RUN mkdir -p models/tranc3-v1 models/tokenizer data/vector_store cache

# Entrypoint handles migrations then starts servers
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose main API + nanoservices
EXPOSE 8000 8001

# Override CMD for worker-only mode: CMD ["python", "-m", "src.workers.inference_worker"]
ENTRYPOINT ["docker-entrypoint.sh"]
