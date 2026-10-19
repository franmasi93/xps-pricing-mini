# XPS Pricing Mini — imagen de producción para Cloud Run (F5-B1).
# Python 3.13, dependencias fijas (requirements.txt), Chromium de Playwright con sus librerías del sistema para el
# PDF, fuentes embebidas en app/templates/fonts, usuario no root y sin .env dentro de la imagen (ver .dockerignore).
# Los secretos llegan como variables de entorno desde Secret Manager (docs/DESPLIEGUE.md).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    APP_ENV=prod \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY frontend ./frontend
COPY scripts ./scripts
# E1-B: la plantilla oficial de importación de clientes (la lee app/services/importacion_clientes.py).
COPY docs/extensiones/importacion ./docs/extensiones/importacion

RUN useradd --create-home --uid 10001 xps \
    && chown -R xps:xps /app \
    && chmod -R a+rX /ms-playwright
USER xps

EXPOSE 8080
# Cloud Run fija PORT; --proxy-headers porque el TLS termina en el balanceador de Google.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --log-config app/core/log_config.json"]
