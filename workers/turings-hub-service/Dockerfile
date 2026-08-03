FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY --chown=worker:worker worker.py .

# VRM, animation, and portrait assets (populated at runtime or via volume mount)
RUN mkdir -p assets/vrm assets/animations assets/portraits \
  && chown -R worker:worker assets/

RUN mkdir -p src/personality src/entities 2>/dev/null; \
    touch src/__init__.py src/personality/__init__.py src/entities/__init__.py

USER worker
EXPOSE 8058
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8058/health', timeout=5).read()" || exit 1

CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8058"]
