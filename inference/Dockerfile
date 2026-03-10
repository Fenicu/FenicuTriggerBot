FROM ghcr.io/astral-sh/uv:python3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN uv sync --frozen --no-cache --no-dev
ENV PATH="/app/.venv/bin:$PATH"

COPY ./inference /app/inference

EXPOSE 8000

CMD [".venv/bin/uvicorn", "inference.main:app", "--host", "0.0.0.0", "--port", "8000"]
