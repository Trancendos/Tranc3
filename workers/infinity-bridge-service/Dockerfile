FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5

WORKDIR /app

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY . .

RUN useradd -m -r -s /bin/false worker
USER worker

EXPOSE 8070

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8070/health')" || exit 1

CMD ["python", "worker.py"]
