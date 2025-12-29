FROM ghcr.io/astral-sh/uv:python3.13-alpine

WORKDIR /app

RUN apk add --no-cache curl

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --no-dev
ENV PATH="/app/.venv/bin:$PATH"

COPY ./app /app/app
COPY logging.yaml alembic.ini /app/
COPY ./locales /app/locales

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
