FROM python:3.11-slim@sha256:e031123e3d85762b141ad1cbc56452ba69c6e722ebf2f042cc0dc86c47c0d8b3
RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/infinity-one-service/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker workers/infinity-one-service/worker.py .
# worker.py imports Dimensional.dimensionals and Dimensional.infinity.* -
# vendored from the repo-root build context (context: . per
# docker-compose.production.yml), not duplicated locally.
COPY --chown=worker:worker Dimensional/ ./Dimensional/

RUN mkdir -p data && chown -R worker:worker data

USER worker
EXPOSE 8043
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8043/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8043"]
