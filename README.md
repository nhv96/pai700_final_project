# pai700_final_project

Digital twin of one school classroom's heating and ventilation (PAI700, Kraftstaden / Trollhättan Stad).

## Run

```bash
uv sync
uv run python -m twin      # 2 simulated school days -> out/run.csv
```

Python 3.13, managed with uv. Parameters live in `config/params.yaml` (confidence levels per value, see `docs/parameters.md`).

## Layout

| File | Role |
|---|---|
| `twin/interface.py` | `StepInputs`, `ZoneState`, `HeatModel` protocol (contract with the heat-model owner) |
| `twin/stub_model.py` | placeholder `HeatModel` (no physics) |
| `twin/params.py` | typed loader for `config/params.yaml` |
| `twin/schedule.py` | occupancy schedule, plant timer windows |
| `twin/weather.py` | `Weather` protocol, constant and synthetic sources (SMHI loader later) |
| `twin/radiator.py` | valve + radiator output (twin side) |
| `twin/ventilation.py` | airflow incl. overheat purge |
| `twin/sensors.py` | ideal sensors |
| `twin/controller.py` | `Controller` protocol, legacy timer + thermostat baseline |
| `twin/simulation.py` | `DigitalTwin` 60 s loop, `build_default_twin()` |

## Plugging in the real heat model

Implement `step(state, inputs, dt_s) -> ZoneState` (see `twin/interface.py`) and pass it as `model=` to `build_default_twin()`.
