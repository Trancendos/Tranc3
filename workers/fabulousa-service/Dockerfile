FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r fabulousa && useradd -r -g fabulousa fabulousa

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

USER fabulousa

EXPOSE 8048

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8048\")}/health', timeout=4).read()"

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8048"]
