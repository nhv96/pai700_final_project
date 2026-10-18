# PAI700 final project: AI-assisted heating optimization in old buildings

Course PAI700, University West. Client: Trollhättan Stad / Kraftstaden.
Research question: **is it feasible to use AI to optimize heating in old municipal buildings?**
The client's core problems are "system fighting" and overshoot, thermal inertia, and finding the best start and stop time for heating.

## The three parts

The research solution has three parts that work together. This repository now covers all three.

| Part | What it is | Status |
|---|---|---|
| **Digital twin (DT)** | A simulation of one school classroom (heating and ventilation) with a 60 s step. It gives us a safe place to test control ideas without touching a real building. | Simulation loop, radiator, ventilation, sensors, schedule and baseline controller exist (`twin/`). The heat model is still a **placeholder**; the real heat model is next. |
| **AI model** | Predicts near-future heat load (`HtTot`, hourly) from past heat, weather and calendar. Meant to plug into the DT and feed the controller. | Working: ETL, baselines, LightGBM, tuning (`etl/`, `modeling/`). |
| **Building-management dashboard** | One central place to see the buildings, their state, the AI forecasts and the DT results. | Not started. Design is the next discussion. |

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
```

Parameters live in `config/params.yaml` (confidence level per value, see `docs/parameters.md`).

Docker:

```bash
docker build -t pai700-twin .
mkdir -p out && docker run --rm -v "$PWD/out:/app/out" --user "$(id -u):$(id -g)" pai700-twin
head out/run.csv
```

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

### AI model

```bash
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
| `twin/stub_model.py`, `twin/placeholder_model.py` | placeholder heat models (no real physics yet) |
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
| `etl/preprocess_htot.py` | silver and gold layers from the raw files |
| `etl/windows.py` | time splits and forecasting windows |
| `modeling/` | baselines, metrics, LightGBM (`gbm.py`), tuning, day types, features |
| `config/params.yaml` | twin parameters |
| `docs/` | explanations: parameters, energy balance, metrics, how LightGBM training works |
| `notebooks/` | data quality scan and the decision log |
| `tests/` | pytest suite for ETL, windows, metrics, GBM, tuning, day types |
| `AGENTS.md` | context handoff for AI coding agents |

## Plugging in the real heat model

Implement `step(state, inputs, dt_s) -> ZoneState` (see `twin/interface.py`) and pass it as `model=` to `build_default_twin()`.

## Next steps

1. Build the real heat model for the classroom and plug it into the DT.
2. Connect the AI forecast to the DT controller (optimal start/stop).
3. Design and build the centralized building-management dashboard.

## Results so far (AI model)

Pooled WAPE over 10 rolling folds, residual target. Lower is better.

| Horizon | Seasonal naive | LightGBM |
|---|---|---|
| 1 h | 0.236 (persistence: 0.118) | 0.101 |
| 6 h | 0.235 | 0.139 |
| 24 h | 0.235 | 0.139 |

On an unseen building the gain over persistence at 1 h is close to zero. Tuning gave no real gain. Details in `notebooks/quality_inspect_decision.md`.
