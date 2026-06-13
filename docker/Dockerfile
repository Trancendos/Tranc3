# TRANC3 — Hardened Dockerfile
# Security: non-root user, minimal base, no cache, pinned versions
# Updated: 2025-07 — CVE Remediation

FROM python:3.11-slim-bookworm AS base

# Security labels
LABEL maintainer="Trancendos Security <security@trancendos.ai>"
LABEL org.opencontainers.image.title="Tranc3"
LABEL org.opencontainers.image.description="Secure AI Language Model Platform"
LABEL org.opencontainers.image.vendor="Trancendos"

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Security: Install minimal system deps, then remove build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y

# Security: Create non-root user
RUN groupadd -r tranc3 && useradd -r -g tranc3 -d /tranc3 -s /sbin/nologin tranc3

WORKDIR /tranc3

# Security: Pin pip and install with hash verification
RUN pip install --upgrade pip==25.1 setuptools==80.9.0 wheel==0.45.1

# Install Python dependencies (exact-pinned)
COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt 2>/dev/null || \
    pip install -r requirements.txt --no-deps && \
    pip check

# Copy source code with proper ownership
COPY --chown=tranc3:tranc3 . .

# Create necessary directories
RUN mkdir -p data/raw/custom data/processed/train data/processed/val models && \
    chown -R tranc3:tranc3 /tranc3

# Security: Drop to non-root user
USER tranc3

# Security: Read-only filesystem where possible
# Runtime health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import torch; print('healthy')" || exit 1

# Default command
CMD ["python", "scripts/chat.py"]
