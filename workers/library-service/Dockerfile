FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r library && useradd -r -g library library

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY . .

RUN mkdir -p /data && chown library:library /data

USER library

EXPOSE 8067

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8067/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8067"]
