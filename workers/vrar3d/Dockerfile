FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system vrar3d && adduser --system --ingroup vrar3d vrar3d

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py models.py database.py service.py router.py main.py ./

RUN mkdir -p /data/assets && chown vrar3d:vrar3d /data /data/assets

USER vrar3d

EXPOSE 8063

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8063/health', timeout=4).read()"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8063"]
