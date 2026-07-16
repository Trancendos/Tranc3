FROM python:3.12-slim
WORKDIR /app
COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY . .
RUN mkdir -p /data && addgroup --system appgroup && adduser --system --ingroup appgroup appuser && chown -R appuser:appgroup /app /data
USER appuser
EXPOSE 8040
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"OBSERVATORY_PORT\", \"8040\")}/health', timeout=4).read()"
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${OBSERVATORY_PORT:-8040}"]
