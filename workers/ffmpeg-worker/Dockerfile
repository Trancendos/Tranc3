# FFmpeg worker — non-root hardened (Forgejo #2127)
FROM python:3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN chown -R tranc3:tranc3 /app
USER tranc3

RUN mkdir -p /app/workdir && chown -R worker:worker /app/workdir

ENV FFMPEG_WORKDIR=/app/workdir

USER worker

EXPOSE 8052

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8052/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8052"]
