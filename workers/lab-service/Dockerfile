FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system lab && adduser --system --ingroup lab lab

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY config.py models.py database.py service.py router.py main.py ./

RUN mkdir -p /data && chown lab:lab /data

USER lab

EXPOSE 8066

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8066/health', timeout=4).read()"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8066"]
