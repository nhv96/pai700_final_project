"""Smoke run: ``uv run python -m twin`` simulates 2 school days and writes a CSV."""

from __future__ import annotations

import csv
from dataclasses import asdict, fields
from datetime import timedelta
from pathlib import Path

from .simulation import Record, build_default_twin


def main() -> None:
    twin = build_default_twin(initial_t_air_C=19.0)  # below setpoint so the radiator path runs
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
    print(f"steps: {len(records)} (dt={twin.dt_s:.0f} s), heat model: {type(twin.model).__name__}")
    print(f"radiator heat delivered: {heat_kWh:.1f} kWh, CSV: {out}")
    print("note: the stub model has no physics; plug in the real HeatModel for meaningful temperatures")


if __name__ == "__main__":
    main()
