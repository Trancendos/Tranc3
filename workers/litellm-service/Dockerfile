FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r litellm && useradd -r -g litellm litellm

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

RUN mkdir -p /app/data && chown -R litellm:litellm /app/data

USER litellm

EXPOSE 8049

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8049\")}/health', timeout=4).read()"

CMD ["python", "worker.py"]
