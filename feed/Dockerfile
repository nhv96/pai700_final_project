# syntax=docker/dockerfile:1

# Replay feed. Build context is feed/ only; the frozen file is mounted at runtime, never baked in.
FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    FEED_DATA=/data/oslo_window_v1.parquet

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY pyproject.toml uv.lock ./
COPY feed/ ./feed/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 feed
USER feed

EXPOSE 8001
CMD ["uvicorn", "--factory", "feed.api:create_app", "--host", "0.0.0.0", "--port", "8001"]
