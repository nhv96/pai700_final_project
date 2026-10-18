"""Scenario: cold morning pre-heat, then sun and people arrive, the room overshoots,
the ventilation purge works against the radiator. Run:

    uv run python -m scenarios.overshoot

Writes ``out/overshoot.csv`` and ``out/overshoot.png`` and prints a daily summary.

What this shows: with OUR model and OUR assumed parameters (all marked 'assumed' in
config/params.yaml and twin/room_model.py), the mechanism the client describes is
physically reproducible. It does not prove it happens in their building: that needs
measured indoor temperatures.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, fields
from datetime import timedelta
from pathlib import Path

from twin.controller import Controller
from twin.metrics import DaySummary, summarise  # noqa: F401  (re-exported for the scenarios)
from twin.params import TwinParams, load_params
from twin.room_model import TwoNodeRoomModel
from twin.simulation import Record, build_default_twin
from twin.weather import SyntheticWeather

DAYS = 3  # Monday to Wednesday
INITIAL_T_AIR_C = 17.0  # school has been at setback over the weekend
# Cold early morning, clear sky. Assumed, not fitted to Trollhattan.
WEATHER = dict(mean_C=2.0, daily_amplitude_K=5.0, sunrise_hour=6.0, sunset_hour=18.0, solar_peak_W_m2=500.0)


def run(
    params: TwinParams | None = None,
    days: int = DAYS,
    controller: Controller | None = None,
    weather: dict | None = None,
    room: dict | None = None,
) -> list[Record]:
    """Run the scenario. ``controller`` defaults to the legacy one; a controller with a
    ``bind(twin)`` method (a predictive one) is bound to the twin before the run.
    ``weather`` overrides entries of WEATHER, ``room`` overrides RoomModelParams fields."""
    params = params or load_params()
    twin = build_default_twin(
        params=params,
        model=TwoNodeRoomModel.from_params(params, **(room or {})),
        weather=SyntheticWeather(**{**WEATHER, **(weather or {})}),
        controller=controller,
        initial_t_air_C=INITIAL_T_AIR_C,
    )
    if hasattr(controller, "bind"):
        controller.bind(twin)
    return twin.run(timedelta(days=days))


def write_csv(records: list[Record], path: Path) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[x.name for x in fields(Record)])
        w.writeheader()
        for r in records:
            w.writerow(asdict(r))


def main() -> None:
    from scenarios.plot import plot_overshoot

    params = load_params()
    records = run(params)
    write_csv(records, Path("out") / "overshoot.csv")
    plot_overshoot(records, params, Path("out") / "overshoot.png")
    for s in summarise(records, params):
        print(s)
    print("CSV: out/overshoot.csv   PNG: out/overshoot.png")


if __name__ == "__main__":
    main()
