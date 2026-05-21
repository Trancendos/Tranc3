FROM python:3.11-slim
WORKDIR /app
COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY worker.py .
RUN mkdir -p /app/data
EXPOSE 8029
CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8029"]
