FROM python:3.11-slim

# Install ffmpeg (zero-cost, available in Debian repos)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

# Working directory for processed video files (mounted as a volume in production)
RUN mkdir -p /app/workdir

ENV FFMPEG_WORKDIR=/app/workdir

EXPOSE 8052

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8052"]
