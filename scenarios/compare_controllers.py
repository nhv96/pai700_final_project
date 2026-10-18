"""Compare the legacy controller with the forecast pre-heating controller. Run:

    uv run python -m scenarios.compare_controllers

Same weather, same start state, same ventilation timer; only the heating control differs.
Writes ``out/controller_comparison.csv`` and ``out/controller_comparison.png`` and prints
a table. The forecast controller sees a perfect weather forecast and a perfect copy of the
room model, so the result is a best case (see twin/predictive_controller.py).
"""

from __future__ import annotations

from pathlib import Path

from scenarios.overshoot import run, write_csv
from scenarios.plot import plot_comparison
from twin.metrics import Totals, totals  # noqa: F401  (re-exported for the scenarios)
from twin.params import load_params
from twin.predictive_controller import ForecastController

DAYS = 5  # Monday to Friday


def main() -> None:
    params = load_params()
    legacy = run(params, days=DAYS)
    forecast = run(params, days=DAYS, controller=ForecastController(params.heating, params.comfort, params.occupancy))
    write_csv(legacy, Path("out") / "controller_comparison_legacy.csv")
    write_csv(forecast, Path("out") / "controller_comparison_forecast.csv")
    plot_comparison(legacy, forecast, params, Path("out") / "controller_comparison.png")
    print(f"{DAYS} days, per-controller totals")
    for name, recs in (("legacy", legacy), ("forecast", forecast)):
        print(f"  {name:9s}{totals(recs, params)}")
    print("PNG: out/controller_comparison.png")


if __name__ == "__main__":
    main()
