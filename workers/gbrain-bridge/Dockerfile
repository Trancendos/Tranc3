FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY worker.py .

RUN mkdir -p /app/data

EXPOSE 8030
CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8030", "--log-level", "info"]
