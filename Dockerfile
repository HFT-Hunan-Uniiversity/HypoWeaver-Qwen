# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build -- --outDir /build/dist

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend/src \
    MPLCONFIGDIR=/app/backend/var/matplotlib-cache

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-lock.txt /tmp/requirements-lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements-lock.txt

COPY backend/src/ ./backend/src/
COPY backend/config/ ./backend/config/
COPY backend/scripts/ ./backend/scripts/
COPY --from=frontend-build /build/dist/ ./dist/

RUN useradd --create-home --uid 10001 hypoweaver \
    && mkdir -p /app/backend/var \
    && chown -R hypoweaver:hypoweaver /app

USER hypoweaver
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "hypoweaver.api:app", "--host", "0.0.0.0", "--port", "8000"]
