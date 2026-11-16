FROM node:20-alpine AS build-frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim

WORKDIR /app

# tzdata-legacy: старые имена зон (Europe/Kiev и т.п.), которые были в образе на Alpine
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg tzdata-legacy \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-dev --compile-bytecode
ENV PATH="/app/.venv/bin:$PATH"

COPY ./app /app/app
COPY logging.yaml alembic.ini /app/
COPY ./locales /app/locales

COPY --from=build-frontend /app/frontend/dist /app/frontend/dist

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
