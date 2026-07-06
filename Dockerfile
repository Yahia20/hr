# syntax=docker/dockerfile:1

# ---- Stage 1: build the React/Vite frontend ----
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: FastAPI backend serving the built SPA ----
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /fe/dist ./static
ENV FRONTEND_DIST=/app/static \
    PYTHONUNBUFFERED=1

# Railway injects $PORT; default to 8000 for local `docker run`.
EXPOSE 8000
# --proxy-headers + --forwarded-allow-ips=* make uvicorn trust the platform's
# X-Forwarded-For / -Proto, so request.client.host is the real client IP (not
# the Railway edge). Required for correct per-IP login lockout, the attendance
# IP audit, and HTTPS detection (HSTS). Only the platform edge can reach the
# container, so trusting all forwarded IPs is safe here.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
