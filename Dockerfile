FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SYMPHONIA_HOST=0.0.0.0 \
    SYMPHONIA_PORT=8099 \
    SYMPHONIA_DATABASE=/data/symphonia.sqlite3

WORKDIR /app
COPY src /app/src

RUN addgroup --system symphonia \
    && adduser --system --ingroup symphonia symphonia \
    && mkdir -p /data \
    && chown -R symphonia:symphonia /app /data

USER symphonia
VOLUME ["/data"]
EXPOSE 8099

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request; port=os.getenv('SYMPHONIA_PORT','8099'); base=os.getenv('SYMPHONIA_INGRESS_PATH','/').rstrip('/'); urllib.request.urlopen(f'http://127.0.0.1:{port}{base}/ready', timeout=2)"]

ENTRYPOINT ["python", "-m", "symphonia"]
