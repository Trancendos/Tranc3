FROM python:3.12-slim
WORKDIR /app
COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY . .
RUN mkdir -p /data
EXPOSE 8039
CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8039"]
