# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm AS base

# uv: copy the static binary from its official image (pinned).
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first (cached until the lockfile changes).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# App source + migrations (so `yoyo` and the graph-migration runner can run
# from inside the container).
COPY app ./app
COPY migrations ./migrations
COPY graph_migrations ./graph_migrations
COPY scripts ./scripts
COPY yoyo.ini ./yoyo.ini

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# PYTHONPATH so `python scripts/*.py` can import `app` (the project isn't
# installed as a package — see [tool.uv] package = false).
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
