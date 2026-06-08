FROM python:3.11-slim

# Install ffmpeg (zero-cost, available in Debian repos)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Security: non-root user
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app

COPY --chown=worker:worker requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=worker:worker worker.py .

# Working directory for processed video files (mounted as a volume in production)
RUN mkdir -p /app/workdir \
    && chown -R worker:worker /app/workdir

ENV FFMPEG_WORKDIR=/app/workdir

# Security: drop to non-root user
USER worker

EXPOSE 8052

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8052"]
