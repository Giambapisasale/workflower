# Immagine unica: builda il frontend (Vite) e lo fa servire dal backend FastAPI.
# Un solo container = API + interfaccia. I dati (repo git SoT) stanno su un
# volume esterno montato in /data (vedi entrypoint e i file di deploy).

# --- 1) build del frontend --------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # → /web/dist

# --- 2) runtime backend -----------------------------------------------------
FROM python:3.12-slim
# git: GitPython invoca il binario per i commit del repo dati (ogni mutazione).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir -e ./backend
COPY --from=frontend /web/dist ./frontend_dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data/repo \
    FRONTEND_DIST=/app/frontend_dist \
    LOG_LEVEL=INFO \
    DIAGNOSTICA_AUTO=0

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
