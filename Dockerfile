# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci 2>/dev/null || npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_PORT=8080 \
    STATIC_DIR=/app/static

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY --from=frontend-build /build/dist /app/static
COPY docker/entrypoint.sh /app/docker/entrypoint.sh

RUN chmod +x /app/docker/entrypoint.sh

WORKDIR /app/backend
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health')" || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
