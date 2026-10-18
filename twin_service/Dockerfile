# syntax=docker/dockerfile:1

# Twin service. Build context is the REPOSITORY ROOT (it needs twin/ and config/), so build with:
#   docker build -f twin_service/Dockerfile -t pai700-twin-service .
# The replay feed is reached over HTTP (FEED_URL).
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
    --mount=type=bind,source=twin_service/uv.lock,target=uv.lock \
    --mount=type=bind,source=twin_service/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY twin_service/pyproject.toml twin_service/uv.lock ./
COPY config/ ./config/
COPY twin/ ./twin/
COPY twin_service/twin_service/ ./twin_service/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 twin
USER twin

EXPOSE 8002
CMD ["uvicorn", "--factory", "twin_service.app:create_app", "--host", "0.0.0.0", "--port", "8002"]
