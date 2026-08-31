FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5
# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker workers/infinity-auth/requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker workers/infinity-auth/*.py ./
COPY --chown=worker:worker shared_core/ shared_core/
COPY --chown=worker:worker Dimensional/ Dimensional/
COPY --chown=worker:worker src/__init__.py src/__init__.py
COPY --chown=worker:worker src/entities/ src/entities/
COPY --chown=worker:worker src/database/ src/database/
COPY --chown=worker:worker src/errors/ src/errors/
RUN mkdir -p /app/data && chown -R worker:worker /app/data
# Security: drop to non-root user
USER worker

EXPOSE 8005
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8005/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8005"]
