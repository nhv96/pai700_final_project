# forecast_service: the AI model as an HTTP service

Forecasts the heat use of a whole building (`HtTot`, Wh per hour) 1, 6 and 24 hours ahead with the saved models from `../models/ai_v1/`. The dashboard forwards to it at `/api/forecast/series` and draws the forecast over the measured heat use.

It holds no data. It asks the replay feed (`FEED_URL`) for the hourly readings **up to the forecast hour** (`/readings`, never later) and for the weather of the next hours (`/weather-forecast`, measured weather replayed as a **perfect forecast**). A forecast therefore never sees heat use from after its origin. The models are loaded once from `MODEL_DIR` and checked against the SHA-256 list in `manifest.json`; a changed or missing file stops the service from starting.

## The models (`../models/ai_v1/`)

| Horizon | Model |
|---|---|
| 1 h | LightGBM, direct target |
| 6 h, 24 h | plain average of LightGBM and a GRU, both on the residual target (HtTot minus the seasonal naive value) |

Trained on all windows of buildings 8105, 8107 and 8116 whose target hour is **before 2022-03-01**, with the same settings and seeds as the final test run (`modeling/final.py`). Error on the held-out test block (2022-03-01 to 2023-10-22), in `GET /model`: WAPE 0.093 / 0.127 / 0.128 for 1 / 6 / 24 h. The frozen replay window (2022-09-24 to 2023-03-31) lies inside that block, so the models have never seen it. The models know only the three buildings they were trained on (`GET /model` lists them); another building is refused.

Re-create the files (about 40 minutes, CPU): `uv run python -m modeling.export` from the repository root.

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status": "ok", "model": "ai_v1"}` |
| `GET /model` | version, rule, training end, test scores, buildings, a `note` |
| `GET /forecast?now=2022-12-19T10:00&building=8105&horizons=1,6,24` | the forecasts made at hour `now` (the last known hour): per horizon `target_time`, `wh` (final value), `trees_wh`, `gru_wh` |
| `GET /forecast/series?from=&until=&building=&horizons=` | forecasts made at every origin from `from` to `until` (at most 31 days), grouped by horizon. `covered` tells which origins each horizon could use. |

Timestamps are ISO 8601; one without an offset is the data's own time (UTC+1, no daylight saving). An origin needs 168 hours of history and the weather of the next `horizon` hours inside the data window, otherwise it is left out (`/forecast` answers 422).

The response carries a `note`: the forecasts are for the whole building, and because the weather is a perfect forecast the accuracy is an upper bound.

## Run

The service imports `etl/` and `modeling/` from the repository root.

```bash
# the feed must be running (see ../feed/README.md)
cd forecast_service
uv sync
FEED_URL=http://localhost:8001 MODEL_DIR=../models/ai_v1 PYTHONPATH=.. uv run uvicorn --factory forecast_service.app:create_app --port 8003
```

Docker (the build context is the repository root):

```bash
docker build -f forecast_service/Dockerfile -t pai700-forecast-service .
```

or `docker compose up --build` from the root, which starts the feed, the twin service, the forecast service and the dashboard together. The service uses the CPU-only build of torch.

## Tests

```bash
cd forecast_service && uv run pytest
```

The tests use a tiny model folder and a fake feed. They check, among other things, that a forecast does not change when the heat use after its origin changes.
