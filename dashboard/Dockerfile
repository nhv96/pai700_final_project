# syntax=docker/dockerfile:1

# Dashboard server + static page. Build context is dashboard/ only; the replay feed is reached over HTTP (FEED_URL).
FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    FEED_URL=http://feed:8001

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY pyproject.toml uv.lock ./
COPY dashboard/ ./dashboard/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 dashboard
USER dashboard

EXPOSE 8000
CMD ["uvicorn", "--factory", "dashboard.app:create_app", "--host", "0.0.0.0", "--port", "8000"]
