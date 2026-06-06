FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/gateway-service/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker workers/gateway-service/worker.py .

RUN mkdir -p data && chown -R worker:worker data

USER worker
EXPOSE 8040
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8040/health || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8040"]
