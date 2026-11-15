FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/infinity-one-service/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker workers/infinity-one-service/worker.py .
# worker.py imports Dimensionals.dimensionals and Dimensionals.infinity.* -
# vendored from the repo-root build context (context: . per
# docker-compose.production.yml), not duplicated locally.
COPY --chown=worker:worker Dimensionals/ ./Dimensionals/

RUN mkdir -p data && chown -R worker:worker data

USER worker
EXPOSE 8043
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8043/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8043"]
