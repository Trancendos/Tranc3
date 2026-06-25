FROM python:3.11-slim
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=worker:worker worker.py .
RUN mkdir -p /app/data && chown -R worker:worker /app/data
USER worker

EXPOSE 8096
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8096/health')" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8096"]
