FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system tranceflow && adduser --system --ingroup tranceflow tranceflow

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py models.py database.py service.py router.py main.py ./

RUN mkdir -p /data/tranceflow-assets && chown tranceflow:tranceflow /data /data/tranceflow-assets

USER tranceflow

EXPOSE 8059

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8059/health', timeout=4).read()"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8059"]
