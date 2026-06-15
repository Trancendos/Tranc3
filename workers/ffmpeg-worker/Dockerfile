FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

RUN mkdir -p /app/workdir && chown -R worker:worker /app/workdir

ENV FFMPEG_WORKDIR=/app/workdir

USER worker

EXPOSE 8052

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8052/health || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8052"]
