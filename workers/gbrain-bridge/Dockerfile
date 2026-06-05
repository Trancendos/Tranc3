FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.136.3 uvicorn==0.34.3 pydantic==2.11.5 httpx==0.28.1
COPY --chown=worker:worker workers/gbrain-bridge/worker.py .

RUN mkdir -p data && chown -R worker:worker data

USER worker
EXPOSE 8030
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8030/health || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8030"]
