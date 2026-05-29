FROM python:3.11-slim
# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
# Copy Dimensional package (monorepo path)
COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

# Copy the Dimensional hive package
COPY --chown=worker:worker Dimensional/ ./Dimensional/

# Security: drop to non-root user
USER worker

EXPOSE 8060
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8060/health || exit 1

CMD ["uvicorn", "Dimensional.hive.hive_core:app", "--host", "0.0.0.0", "--port", "8060"]
