# syntax=docker/dockerfile:1

# Forecast service. Build context is the REPOSITORY ROOT (it needs etl/, modeling/ and the saved models), so build with:
#   docker build -f forecast_service/Dockerfile -t pai700-forecast-service .
# The replay feed is reached over HTTP (FEED_URL). The models are read-only files in /app/models.
FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    FEED_URL=http://feed:8001 \
    MODEL_DIR=/app/models/ai_v1

WORKDIR /app

# lightgbm needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=forecast_service/uv.lock,target=uv.lock \
    --mount=type=bind,source=forecast_service/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY forecast_service/pyproject.toml forecast_service/uv.lock ./
COPY etl/windows.py ./etl/windows.py
COPY modeling/ ./modeling/
COPY models/ ./models/
COPY forecast_service/forecast_service/ ./forecast_service/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 forecast
USER forecast

EXPOSE 8003
CMD ["uvicorn", "--factory", "forecast_service.app:create_app", "--host", "0.0.0.0", "--port", "8003"]
