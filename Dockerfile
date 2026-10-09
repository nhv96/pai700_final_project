# syntax=docker/dockerfile:1

# Digital twin image. Same image runs locally and as an Azure Container Apps Job.
FROM python:3.13-slim-bookworm

# uv binary (pin the minor version; bump deliberately)
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 1) Dependencies only (cached until pyproject.toml / uv.lock change).
#    --frozen: fail if uv.lock is out of date instead of silently re-resolving.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

# 2) Project code and config.
COPY pyproject.toml uv.lock ./
COPY config/ ./config/
COPY twin/ ./twin/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Run as non-root; /app/out is where the simulation writes run.csv.
RUN useradd --create-home --uid 1000 twin \
    && mkdir -p /app/out \
    && chown -R twin:twin /app/out
USER twin

CMD ["python", "-m", "twin"]