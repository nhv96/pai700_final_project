"""Sensitivity of the controller comparison to the assumed parameters. Run:

    uv run python -m scenarios.sensitivity

Changes ONE assumed value at a time (weather, building, controller settings), reruns legacy,
forecast heating, supply-temperature control and both combined, and records how much heat
each saves versus legacy and how the peak room temperature changes. Writes
``out/sensitivity.csv`` and ``out/sensitivity.png``.

The point is robustness: does the ranking and the size of the saving survive reasonable
changes of the numbers that params.yaml marks as assumed?
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path

from twin.controller_set import make_controllers
from scenarios.compare_controllers import DAYS, totals
from scenarios.overshoot import run
from twin.params import TwinParams, load_params


@dataclass(frozen=True)
class Case:
    group: str
    label: str
    weather: dict = field(default_factory=dict)
    room: dict = field(default_factory=dict)
    params_edit: tuple = ()  # ("window_area_m2", 6.0) style pairs, see apply_params
    controller: dict = field(default_factory=dict)


CASES = [
    Case("base case", "base case"),
    Case("outdoor temperature", "mean -5 °C", weather={"mean_C": -5.0}),
    Case("outdoor temperature", "mean 8 °C", weather={"mean_C": 8.0}),
    Case("sun strength", "peak 300 W/m²", weather={"solar_peak_W_m2": 300.0}),
    Case("sun strength", "peak 700 W/m²", weather={"solar_peak_W_m2": 700.0}),
    Case("wall U-value", "0.4 W/m²K", room={"u_wall_W_m2K": 0.4}),
    Case("wall U-value", "1.2 W/m²K", room={"u_wall_W_m2K": 1.2}),
    Case("external wall area", "7 m²", room={"opaque_wall_area_m2": 7.0}),
    Case("external wall area", "28 m² (corner room)", room={"opaque_wall_area_m2": 28.0}),
    Case("window area", "6 m²", params_edit=(("window_area_m2", 6.0),)),
    Case("window area", "14 m²", params_edit=(("window_area_m2", 14.0),)),
    Case("glass g-value", "0.4", params_edit=(("window_g_value", 0.4),)),
    Case("glass g-value", "0.7", params_edit=(("window_g_value", 0.7),)),
    Case("shading", "factor 0.3 (external blinds)", room={"shading_factor": 0.3}),
    Case("wall heat capacity", "medium (165 kJ/m²K)", room={"mass_capacity_J_m2K": 165_000.0}),
    Case("infiltration", "0.05 1/h", room={"infiltration_ach": 0.05}),
    Case("infiltration", "0.4 1/h", room={"infiltration_ach": 0.4}),
    Case("heat recovery", "70 % (FTX unit)", params_edit=(("heat_recovery_eff", 0.7),)),
    Case("pupils", "20", params_edit=(("pupils", 20),)),
    Case("pupils", "30", params_edit=(("pupils", 30),)),
    Case("min supply temp", "18 °C", controller={"min_supply_C": 18.0}),
    Case("supply gain", "1 K/K", controller={"supply_gain": 1.0}),
    Case("supply gain", "4 K/K", controller={"supply_gain": 4.0}),
    Case("forecast look-ahead", "30 min", controller={"lookahead": timedelta(minutes=30)}),
    Case("forecast look-ahead", "120 min", controller={"lookahead": timedelta(minutes=120)}),
    Case("max pre-heat", "3 h", controller={"max_preheat": timedelta(hours=3)}),
]


def apply_params(params: TwinParams, edits: tuple) -> TwinParams:
    for key, value in edits:
        if key in ("window_area_m2", "window_g_value"):
            params = replace(params, zone=replace(params.zone, **{key: value}))
        elif key == "heat_recovery_eff":
            params = replace(params, ventilation=replace(params.ventilation, heat_recovery_eff=value))
        elif key == "pupils":
            params = replace(params, occupancy=replace(params.occupancy, pupils=value))
        else:
            raise KeyError(key)
    return params


def evaluate(case: Case, base_params: TwinParams) -> dict:
    params = apply_params(base_params, case.params_edit)
    out = {"group": case.group, "case": case.label}
    runs = {
        name: totals(run(params, days=DAYS, controller=ctrl, weather=case.weather, room=case.room), params)
        for name, ctrl in make_controllers(params, **case.controller).items()
    }
    legacy = runs["legacy"]
    heat = lambda t: t.radiator_kWh + t.coil_kWh
    out["legacy_heat_kWh"] = round(heat(legacy), 1)
    out["legacy_peak_C"] = legacy.peak_t_air_C
    out["legacy_purge_min"] = legacy.minutes_above_purge
    for name, t in runs.items():
        if name == "legacy":
            continue
        key = name.replace(" ", "_")
        out[f"{key}_saving_pct"] = round(100 * (1 - heat(t) / heat(legacy)), 1)
        out[f"{key}_peak_change_K"] = round(t.peak_t_air_C - legacy.peak_t_air_C, 2)
        out[f"{key}_purge_min"] = t.minutes_above_purge
        out[f"{key}_cold_lesson_min"] = t.occupied_minutes_below_lower_limit
    out["legacy_cold_lesson_min"] = legacy.occupied_minutes_below_lower_limit
    return out


def main() -> None:
    base = load_params()
    rows = []
    for case in CASES:
        row = evaluate(case, base)
        rows.append(row)
        print(f"{case.group:22s} {case.label:30s} legacy {row['legacy_heat_kWh']:6.1f} kWh | saving %: "
              f"forecast {row['forecast_heating_saving_pct']:6.1f}  supply {row['supply_temp_saving_pct']:6.1f}  "
              f"combined {row['combined_saving_pct']:6.1f} | peak K combined {row['combined_peak_change_K']:+.2f}")
    out = Path("out") / "sensitivity.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    from scenarios.plot import plot_sensitivity

    plot_sensitivity(rows, Path("out") / "sensitivity.png")
    print("CSV: out/sensitivity.csv   PNG: out/sensitivity.png")


if __name__ == "__main__":
    main()
