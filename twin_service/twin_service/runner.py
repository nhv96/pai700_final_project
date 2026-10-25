"""Run the legacy and the combined controller on feed weather and package the result.

Pure functions (no HTTP): the app fetches the weather rows and calls ``compare``.
Everything returned is SIMULATED with assumed parameters, and the response says so.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta

from twin.controller_set import make_controllers
from twin.feed_weather import FeedWeather
from twin.metrics import totals
from twin.params import TwinParams
from twin.room_model import TwoNodeRoomModel
from twin.simulation import Record, build_default_twin

INITIAL_T_AIR_C = 17.0  # school at setback; the same start as scenarios/overshoot.py
SERIES_EVERY_MIN = 10  # the twin steps every minute; the chart does not need that
PREVIEW_MARGIN_H = 7  # weather needed after the run for the previews: 6 h max pre-heat + 60 min look-ahead
RUNS = {"legacy": "legacy", "combined": "combined"}  # response name -> controller_set name
NOTE = (
    "Simulation, not measurement: assumed room parameters, perfect weather forecast and "
    "perfect room model for the combined controller (best case), sun converted from "
    "horizontal to south facade with one fixed assumed ratio."
)


def _simulate(params: TwinParams, weather: FeedWeather, start: datetime, days: int, controller) -> list[Record]:
    twin = build_default_twin(
        start=start,
        params=params,
        model=TwoNodeRoomModel.from_params(params),
        weather=weather,
        controller=controller,
        initial_t_air_C=INITIAL_T_AIR_C,
    )
    if hasattr(controller, "bind"):
        controller.bind(twin)
    return twin.run(timedelta(days=days))


def _series(records: list[Record]) -> dict[str, list]:
    rows = records[SERIES_EVERY_MIN - 1 :: SERIES_EVERY_MIN]  # end-of-step values, one per bin
    return {
        "time": [f"{r.time + timedelta(seconds=60):%Y-%m-%dT%H:%M}" for r in rows],
        "t_air_C": [round(r.t_air_C, 2) for r in rows],
        "radiator_kW": [round(r.q_radiator_W / 1000.0, 3) for r in rows],
        "coil_kW": [round(r.q_coil_W / 1000.0, 3) for r in rows],
        "supply_air_C": [round(r.t_supply_air_C, 2) for r in rows],
        "occupants": [r.occupants for r in rows],
    }


def compare(weather: FeedWeather, params: TwinParams, start: datetime, days: int) -> dict:
    controllers = make_controllers(params)
    records = {name: _simulate(params, weather, start, days, controllers[key]) for name, key in RUNS.items()}
    base = totals(records["legacy"], params)
    legacy_heat = base.radiator_kWh + base.coil_kWh
    result: dict = {"runs": {}}
    for name, recs in records.items():
        t = totals(recs, params)
        heat = t.radiator_kWh + t.coil_kWh
        result["runs"][name] = {
            "summary": {
                **asdict(t),
                "heat_kWh": round(heat, 2),
                "heat_vs_legacy_pct": round(100 * (heat / legacy_heat - 1), 1) if legacy_heat > 0 else None,
            },
            "series": _series(recs),
        }
    ref = records["legacy"]
    rows = ref[SERIES_EVERY_MIN - 1 :: SERIES_EVERY_MIN]
    result["weather"] = {
        "t_outdoor_C": [round(r.t_outdoor_C, 2) for r in rows],
        "solar_south_W_m2": [round(r.solar_W_m2, 1) for r in rows],
    }
    result["setpoint_C"] = params.comfort.setpoint_C
    result["purge_trigger_C"] = params.ventilation.purge_trigger_C
    result["comfort_band_C"] = [params.comfort.lower_limit_C, params.comfort.discomfort_above_C]
    result["note"] = NOTE
    return result
