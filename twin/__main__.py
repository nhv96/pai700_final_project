"""Smoke run: ``uv run python -m twin`` simulates 2 school days with the placeholder
1R1C model, writes out/run.csv and prints a short summary."""

from __future__ import annotations

import csv
from dataclasses import asdict, fields
from datetime import timedelta
from pathlib import Path

from .params import load_params
from .placeholder_model import OneR1CPlaceholder
from .simulation import Record, build_default_twin

SETPOINT_C = 21.0
DISCOMFORT_ABOVE_C = 26.0


def main() -> None:
    params = load_params()
    twin = build_default_twin(
        model=OneR1CPlaceholder.from_params(params),
        initial_t_air_C=19.0,  # below setpoint so the radiator path runs
    )
    records = twin.run(timedelta(days=2))

    out = Path("out") / "run.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[x.name for x in fields(Record)])
        w.writeheader()
        for r in records:
            w.writerow(asdict(r))

    hours = twin.dt_s / 3600.0
    heat_kWh = sum(r.q_radiator_W for r in records) * hours / 1000.0
    peak = max(records, key=lambda r: r.t_air_C)
    above_setpoint = sum(1 for r in records if r.t_air_C > SETPOINT_C)
    above_discomfort = sum(1 for r in records if r.t_air_C > DISCOMFORT_ABOVE_C)

    print(f"model: {type(twin.model).__name__} (THROWAWAY placeholder)")
    print(f"steps: {len(records)} (dt={twin.dt_s:.0f} s)")
    print(f"radiator heat delivered: {heat_kWh:.1f} kWh")
    print(f"peak t_air: {peak.t_air_C:.2f} C at {peak.time:%a %H:%M}")
    print(f"minutes above setpoint {SETPOINT_C:.0f} C: {above_setpoint}")
    print(f"minutes above discomfort {DISCOMFORT_ABOVE_C:.0f} C: {above_discomfort}")
    print(f"CSV: {out}")


if __name__ == "__main__":
    main()
