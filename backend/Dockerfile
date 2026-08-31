# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.12-python3.13-bookworm-slim AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first (cached until the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# App source + migrations (so `yoyo` can run from inside the container).
COPY app ./app
COPY migrations ./migrations
COPY yoyo.ini ./yoyo.ini

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
