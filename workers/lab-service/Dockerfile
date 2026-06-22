FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system lab && adduser --system --ingroup lab lab

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY config.py models.py database.py service.py router.py main.py ./

RUN mkdir -p /data && chown lab:lab /data

USER lab

EXPOSE 8039

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8039"]
