# Build the existing frontend; no user data is included in either stage.
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
RUN npm install --global pnpm@11.25.0
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
RUN pnpm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATALENS_DB=/app/storage/platform.sqlite \
    PORT=7860
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 1000 datalens \
    && mkdir -p /app/storage \
    && chown datalens:datalens /app/storage
COPY backend ./backend
COPY data/orders.csv ./data/orders.csv
COPY --from=frontend /build/dist ./frontend/dist
USER datalens
EXPOSE 7860
CMD ["sh", "-c", "exec uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
