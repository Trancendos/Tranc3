FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3
# Install curl (healthcheck) and create non-root user in a single layer
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker path_validation.py worker.py .
RUN mkdir -p /data/mlflow-service \
    && chown -R worker:worker /data/mlflow-service
# Security: drop to non-root user
USER worker

EXPOSE 8039
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8039/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8039"]
