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
from dataclasses import asdict, dataclass, fields
from datetime import timedelta
from pathlib import Path

from twin.controller import Controller
from twin.params import TwinParams, load_params
from twin.room_model import TwoNodeRoomModel
from twin.simulation import Record, build_default_twin
from twin.weather import SyntheticWeather

DAYS = 3  # Monday to Wednesday
INITIAL_T_AIR_C = 17.0  # school has been at setback over the weekend
# Cold early morning, clear sky. Assumed, not fitted to Trollhattan.
WEATHER = dict(mean_C=2.0, daily_amplitude_K=5.0, sunrise_hour=6.0, sunset_hour=18.0, solar_peak_W_m2=500.0)


@dataclass(frozen=True)
class DaySummary:
    day: str
    peak_t_air_C: float
    peak_time: str
    min_occupied_t_air_C: float
    occupied_minutes_below_lower_limit: int
    minutes_above_setpoint: int
    minutes_above_purge: int
    minutes_above_discomfort: int
    radiator_kWh: float
    coil_kWh: float
    energy_while_above_setpoint_kWh: float  # radiator + coil spent while room >= setpoint
    purge_extra_air_kWh: float  # coil energy for the extra air flow of the purge


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


def summarise(records: list[Record], params: TwinParams) -> list[DaySummary]:
    c, v = params.comfort, params.ventilation
    per_day = int(timedelta(days=1).total_seconds() // params.step_seconds)
    h = params.step_seconds / 3600.0 / 1000.0  # W per step -> kWh
    out = []
    for i in range(0, len(records), per_day):
        day = records[i : i + per_day]
        peak = max(day, key=lambda r: r.t_air_C)
        occupied = [r.t_air_C for r in day if r.occupants > 0]
        above = [r for r in day if r.t_air_C >= c.setpoint_C]
        purging = [r for r in day if r.t_air_C >= v.purge_trigger_C and r.ventilation_flow_L_s > 0]
        # coil power would be flow/multiplier of the actual during purge
        purge_extra = sum(r.q_coil_W * (1 - 1 / v.purge_flow_multiplier) for r in purging) * h
        out.append(
            DaySummary(
                day=f"{day[0].time:%a %d %b}",
                peak_t_air_C=round(peak.t_air_C, 2),
                peak_time=f"{peak.time:%H:%M}",
                min_occupied_t_air_C=round(min(occupied), 2) if occupied else float("nan"),
                occupied_minutes_below_lower_limit=sum(t < c.lower_limit_C for t in occupied),
                minutes_above_setpoint=len(above),
                minutes_above_purge=sum(r.t_air_C >= v.purge_trigger_C for r in day),
                minutes_above_discomfort=sum(r.t_air_C >= c.discomfort_above_C for r in day),
                radiator_kWh=round(sum(r.q_radiator_W for r in day) * h, 2),
                coil_kWh=round(sum(r.q_coil_W for r in day) * h, 2),
                energy_while_above_setpoint_kWh=round(sum(r.q_radiator_W + r.q_coil_W for r in above) * h, 2),
                purge_extra_air_kWh=round(purge_extra, 2),
            )
        )
    return out


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
