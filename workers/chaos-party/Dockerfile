FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    adduser --disabled-password --gecos "" appuser
COPY worker.py .
RUN mkdir -p /app/data && chown appuser:appuser /app/data
USER appuser
EXPOSE 8079
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8079/health')"
CMD ["python", "worker.py"]
