FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

WORKDIR /app

RUN addgroup --system vrar3d && adduser --system --ingroup vrar3d vrar3d

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py models.py database.py service.py router.py main.py ./
COPY static/ ./static/

RUN mkdir -p /data/assets && chown vrar3d:vrar3d /data /data/assets

USER vrar3d

EXPOSE 8060

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8060/health', timeout=4).read()"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8060"]
