# FFmpeg worker — non-root hardened (Forgejo #2127)
FROM python:3.12-slim-bookworm

RUN groupadd -r tranc3 && useradd -r -g tranc3 -d /app -s /sbin/nologin tranc3 \
    && apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN chown -R tranc3:tranc3 /app
USER tranc3

ENV PORT=8039
EXPOSE 8039
CMD ["python", "-m", "uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8039"]
