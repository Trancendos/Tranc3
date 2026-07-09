FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3

# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

# Install system dependencies for image processing and mesh export
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --chown=worker:worker requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# TripoSR (tsr) is an optional heavy dependency; install if desired at build time.
# Uncomment the following line to bake TripoSR into the image:
#   RUN pip install --no-cache-dir git+https://github.com/VAST-AI-Research/TripoSR.git
# Leaving it commented keeps the image lightweight; the worker degrades gracefully
# when tsr is absent (returns 503 with an installation hint).

COPY --chown=worker:worker worker.py .

RUN mkdir -p /app/outputs /app/models && chown -R worker:worker /app

# Security: drop to non-root user
USER worker

EXPOSE 8051
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8051/health')" || exit 1

ENV OUTPUTS_DIR=/app/outputs
ENV MODELS_DIR=/app/models

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8051"]
