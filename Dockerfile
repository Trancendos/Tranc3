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

# Create model directory (weights mounted at runtime or downloaded)
RUN mkdir -p models/tranc3-v1 models/tokenizer

# Expose main API + nanoservices
EXPOSE 8000 8001

# Default: run main FastAPI + nanoservices in parallel
# Override CMD for worker-only mode: CMD ["python", "-m", "src.workers.inference_worker"]
CMD ["sh", "-c", \
  "uvicorn api:app --host 0.0.0.0 --port 8000 & \
   uvicorn src.nanoservices.nano_server:nano_app --host 0.0.0.0 --port 8001 & \
   wait"]
