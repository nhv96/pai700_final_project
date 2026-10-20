# PAI700 final project: AI-assisted heating optimization in old buildings

Course PAI700, University West. Client: Trollhättan Stad / Kraftstaden.
Research question: **is it feasible to use AI to optimize heating in old municipal buildings?**
The client's core problems are "system fighting" and overshoot, thermal inertia, and finding the best start and stop time for heating.

## The three parts

The research solution has three parts that work together. This repository now covers all three.

| Part | What it is | Status |
|---|---|---|
| **Digital twin (DT)** | A simulation of one school classroom (heating and ventilation) with a 60 s step. It gives us a safe place to test control ideas without touching a real building. | Simulation loop, radiator, ventilation with air-handling unit, sensors, schedule, our own two-node heat model (assumed parameters), the legacy controller and two better controllers exist (`twin/`). It runs on feed weather as a service (`twin_service/`). |
| **AI model** | Predicts near-future heat load (`HtTot`, hourly, whole building) from past heat, weather and calendar. | Working: ETL, baselines, LightGBM, GRU, final test, saved models and a forecast service (`etl/`, `modeling/`, `models/`, `forecast_service/`). The twin's controllers do not use it (decision: benchmark only); the dashboard shows it, also scaled to 60 m² next to the twin run. |
| **Building-management dashboard** | One central place to see the buildings, their state, the AI forecasts and the DT results. | First version works (`dashboard/`): replay controls, buildings table, heat and outdoor-temperature charts, and a digital-twin panel (legacy vs combined controller, simulated). The AI forecast overlay works (dashed line, from the forecast service). Status colours are not built yet. |

How they fit together: the dataset is the common ground. The AI model learns from it, the DT replays the same weather, and the dashboard shows what both produce.

All three parts use the same **frozen data window** (`frozen/`, Oslo buildings 8105, 8107, 8116, 2022-09-24 to 2023-03-31: a 7-day warm-up plus a replay from 2022-10-01, a held-out part of the AI model's test block) and read it through the **replay feed** (`feed/`), which plays it like IoT sensors, hourly. Each part keeps its own clock. See `feed/README.md`.

## Data

- **COFACTOR-SBHUB Oslo**: 48 Oslo schools, hourly, CC BY 4.0, SINTEF. DOI 10.60609/2hvr-wc82. Cite Lien et al. 2025, Data in Brief 63, 112288.
- Raw files live in `datasets/` (git-ignored, large; do not open whole files). Drammen buildings were dropped.
- Used buildings: Oslo **8105, 8107, 8116** (long history, few gaps). Columns: `HtTot` (target, Wh per hour), `Tout`, `SolGlob`, `WindSpd`, `WindDir`.
- Timestamps are fixed UTC+1 all year (no daylight saving).
- The dataset has **no indoor temperature**, occupancy or valve data. Indoor temperature has to come from the DT.
- Weather in replays is measured weather used as a "perfect forecast". Real forecast errors are not included, so scores are an upper bound.
- Every data decision is logged in `notebooks/quality_inspect_decision.md`.

## Run

Python 3.13, managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest                      # tests
```

### Digital twin

```bash
uv run python -m twin              # 2 simulated school days -> out/run.csv
uv run python -m scenarios.overshoot   # cold-morning overshoot scenario -> out/overshoot.png + .csv
uv run python -m scenarios.compare_controllers   # legacy vs forecast pre-heating -> out/controller_comparison.png
uv run python -m scenarios.compare_ventilation      # legacy vs room-compensated supply air -> out/ventilation_comparison.png
uv run python -m scenarios.compare_combined         # legacy vs forecast + supply-temp combined -> out/combined_comparison.png
uv run python -m scenarios.sensitivity              # 26 one-at-a-time cases, about 100 s -> out/sensitivity.png + .csv
```

How the scenario and the controllers work: `docs/controllers-and-scenario.md`.

The heat model is our own two-node room model (`twin/room_model.py`: fast air node, slow wall node). The air-handling unit (`ventilation.ahu_step`) applies heat recovery and a heating coil up to the room setpoint, so `supply_air_temp_C` is the air entering the room and the coil energy is logged as `q_coil_W`. All room parameters are assumed, not calibrated. If `uv run` picks system packages, see `docs/pythonpath-note.md`.

Parameters live in `config/params.yaml` (confidence level per value, see `docs/parameters.md`).

Docker:

```bash
docker build -t pai700-twin .
mkdir -p out && docker run --rm -v "$PWD/out:/app/out" --user "$(id -u):$(id -g)" pai700-twin
head out/run.csv
```

### Twin service

Runs the twin on the replay feed's weather (own `pyproject.toml` and Dockerfile; details in `twin_service/README.md`).

```bash
docker compose up --build            # feed :8001, twin :8002, forecast :8003, dashboard http://localhost:8000
```

Limits of the Oslo data for the heat model: `docs/oslo-data-limits.md`. Results on real Oslo weather: `docs/controllers-and-scenario.md`.

### Data pipeline (ETL)

```bash
uv run python -m etl.preprocess_htot   # raw -> data/silver/*.parquet -> data/gold/htot_oslo.parquet
```

### Frozen window and replay feed

Own `pyproject.toml` and Dockerfile; details in `feed/README.md`.

```bash
cd feed && uv sync
uv run python -m feed.freeze                 # silver -> frozen/oslo_window_v1.parquet + .sha256 (already done; immutable)
uv run python -m feed.freeze verify
FEED_DATA=../frozen/oslo_window_v1.parquet uv run uvicorn --factory feed.api:create_app --port 8001
# or: docker build -t pai700-feed feed && docker run --rm -p 8001:8001 -v "$PWD/frozen:/data:ro" pai700-feed
```

### Dashboard

Own `pyproject.toml` and Dockerfile; details in `dashboard/README.md`. It only talks to the replay feed over HTTP.

```bash
docker compose up --build            # feed on :8001, twin service on :8002, dashboard on http://localhost:8000
```

### Forecast service

Serves the saved AI models over HTTP (own `pyproject.toml` and Dockerfile; details in `forecast_service/README.md`). The dashboard draws its forecasts over the measured heat use.

```bash
cd forecast_service && uv sync
FEED_URL=http://localhost:8001 MODEL_DIR=../models/ai_v1 PYTHONPATH=.. uv run uvicorn --factory forecast_service.app:create_app --port 8003
```

### AI model

Final choice (see the decision log): LightGBM with day-type and trend features at 1 h, the average of LightGBM and a GRU at 6 h and 24 h. Test block (2022-03-01 to 2023-10-22) WAPE 0.093 / 0.127 / 0.128 for 1 / 6 / 24 h, against 0.252 for the seasonal naive baseline.

```bash
uv run python -m modeling.final                      # the final test run, use once -> results/final/
uv run python -m modeling.export                     # train on data before the test block and save -> models/ai_v1/ (about 40 min)
uv run python -m modeling.run_gru --schemes pooled   # GRU on all folds (about 2.5 h on CPU) -> results/gru/
uv run python -m modeling.plot_final                 # winter and holiday week plots -> results/final/figures/
uv run python -m modeling.run_gbm --daytypes --trends   # LightGBM with day-type and trend features on all folds
uv run python -m modeling.run_gbm [--daytypes]       # LightGBM on all folds -> results/gbm/
uv run python -m modeling.persistence_report         # compare with persistence at horizon 1
uv run python -m modeling.tuning search              # random search for LightGBM settings -> results/tuning/
uv run python -m modeling.tuning confirm             # rerun best setting on all folds
```

`--daytypes` adds Norwegian public holidays and school breaks as features (`modeling/daytypes.py`).
A full `run_gbm` takes about 40 minutes. If `uv run` picks up the wrong packages, see `docs/pythonpath-note.md`.

## Layout

| Path | Role |
|---|---|
| `twin/interface.py` | `StepInputs`, `ZoneState`, `HeatModel` protocol (contract with the heat-model owner) |
| `twin/stub_model.py`, `twin/placeholder_model.py` | placeholder heat models (kept for tests) |
| `twin/room_model.py` | our two-node heat model |
| `twin/feed_weather.py` | weather from replay-feed rows (sun converted to the south facade) |
| `twin/controller_set.py`, `twin/metrics.py` | the standard controllers and the result metrics |
| `twin_service/` | HTTP service that runs the twin on feed weather (own project and Dockerfile) |
| `twin/params.py` | typed loader for `config/params.yaml` |
| `twin/schedule.py` | occupancy schedule, plant timer windows |
| `twin/weather.py` | `Weather` protocol, constant and synthetic sources (SMHI loader later) |
| `twin/radiator.py` | valve + radiator output (twin side) |
| `twin/ventilation.py` | airflow including overheat purge |
| `twin/sensors.py` | ideal sensors |
| `twin/controller.py` | `Controller` protocol, legacy timer + thermostat baseline |
| `twin/simulation.py` | `DigitalTwin` 60 s loop, `build_default_twin()` |
| `feed/` | frozen-window freeze command and HTTP replay service (own project, own Dockerfile) |
| `frozen/` | the frozen dataset window + SHA-256 checksum |
| `dashboard/` | building-heat dashboard: small FastAPI server + plain HTML/JS page (own project, own Dockerfile) |
| `docker-compose.yml` | runs the feed and the dashboard together |
| `etl/preprocess_htot.py` | silver and gold layers from the raw files |
| `etl/windows.py` | time splits and forecasting windows |
| `modeling/` | baselines, metrics, LightGBM (`gbm.py`), GRU (`gru.py`), tuning, day types, features, final test (`final.py`), model export and loading (`export.py`, `predictor.py`) |
| `models/ai_v1/` | the saved models (LightGBM boosters, GRU weights) with a manifest of SHA-256 checksums |
| `forecast_service/` | HTTP service that forecasts building heat use with the saved models (own project and Dockerfile) |
| `config/params.yaml` | twin parameters |
| `docs/` | explanations: parameters, energy balance, metrics, how LightGBM training works |
| `notebooks/` | data quality scan and the decision log |
| `tests/` | pytest suite for ETL, windows, metrics, GBM, tuning, day types |
| `AGENTS.md` | context handoff for AI coding agents |

## Plugging in the real heat model

The twin already runs our own `TwoNodeRoomModel`. Another model only has to implement `step(state, inputs, dt_s) -> ZoneState` (see `twin/interface.py`) and be passed as `model=` to `build_default_twin()`.

## Next steps

1. Calibrate the heat model with indoor temperature and plant data from the client (see `docs/oslo-data-limits.md`).
2. (Decided 2026-10-20) The AI forecast is a benchmark only; the twin's controllers do not use it. Not planned: connecting it to optimal start/stop.
3. Grow the dashboard: status colours, and the forecast for the next hours beyond the replay clock.
4. Optional: check what `HtTot` contains for each building (hot water share) to judge the benchmark better.

## Results so far (AI model)

Pooled WAPE over 10 rolling folds, residual target. Lower is better.

| Horizon | Seasonal naive | LightGBM |
|---|---|---|
| 1 h | 0.236 (persistence: 0.118) | 0.101 |
| 6 h | 0.235 | 0.139 |
| 24 h | 0.235 | 0.139 |

On an unseen building the gain over persistence at 1 h is close to zero. Tuning gave no real gain. Details in `notebooks/quality_inspect_decision.md`.
