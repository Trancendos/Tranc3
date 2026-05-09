# TRANC3 Backend — Docker image for production
# Runs: FastAPI production API with LLM Router, DB persistence, auth
#
# Build:  docker build -t tranc3 .
# Run:    docker run -p 8000:8000 --env-file .env tranc3
#
# For full stack (DB, Redis, observability): docker compose up

FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime

WORKDIR /app

# Non-root user
RUN addgroup --system tranc3 && adduser --system --ingroup tranc3 tranc3

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .

RUN mkdir -p /app/data models/tranc3-v1 models/tokenizer \
    && chown -R tranc3:tranc3 /app

USER tranc3

EXPOSE 8000

# Structured JSON logging by default in container
ENV LOG_LEVEL=INFO
ENV LOG_FORMAT=json
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready')" || exit 1

# Production API entrypoint
CMD ["uvicorn", "api_production:app", "--host", "0.0.0.0", "--port", "8000"]
