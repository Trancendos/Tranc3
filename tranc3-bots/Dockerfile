FROM python:3.14-slim@sha256:ce40764625a4ff50df3548277632e7f96c4e77fe75fa848aae9885476e7df5a4

# Security: non-root user
RUN groupadd -r botuser && useradd -r -g botuser -d /app -s /sbin/nologin botuser

WORKDIR /app

COPY --chown=botuser:botuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=botuser:botuser bots/   bots/
COPY --chown=botuser:botuser server/ server/
COPY --chown=botuser:botuser client/ client/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Security: drop to non-root user
USER botuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
