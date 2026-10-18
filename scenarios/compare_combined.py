"""Legacy vs forecast pre-heating vs supply-temperature control vs both combined. Run:

    uv run python -m scenarios.compare_combined

Same weather and start state for all four. Prints a table and writes
``out/combined_comparison.png``. Forecast controllers see perfect weather and a perfect
room model (best case).
"""

from __future__ import annotations

from pathlib import Path

from scenarios.compare_controllers import DAYS, totals
from scenarios.overshoot import run
from scenarios.plot import plot_comparison
from twin.controller import LegacyController
from twin.params import TwinParams, load_params
from twin.predictive_controller import ForecastController
from twin.supply_controller import SupplyTempController

MIN_SUPPLY_C = 16.0


def make_controllers(
    params: TwinParams, min_supply_C: float = MIN_SUPPLY_C, supply_gain: float = 2.0, **forecast_kw
):
    """Fresh controllers (they hold state) for the four cases."""
    h, c, o = params.heating, params.comfort, params.occupancy
    return {
        "legacy": LegacyController(h, c),
        "forecast heating": ForecastController(h, c, o, **forecast_kw),
        "supply temp": SupplyTempController(LegacyController(h, c), c, min_supply_C=min_supply_C, gain_per_K=supply_gain),
        "combined": SupplyTempController(
            ForecastController(h, c, o, **forecast_kw), c, min_supply_C=min_supply_C, gain_per_K=supply_gain
        ),
    }


def main() -> None:
    params = load_params()
    runs = {name: run(params, days=DAYS, controller=ctrl) for name, ctrl in make_controllers(params).items()}
    base = totals(runs["legacy"], params)
    base_heat = base.radiator_kWh + base.coil_kWh
    print(f"{DAYS} days")
    for name, recs in runs.items():
        t = totals(recs, params)
        heat = t.radiator_kWh + t.coil_kWh
        print(f"  {name:17s} heat {heat:6.1f} kWh ({100 * (heat / base_heat - 1):+5.1f} %)  radiator {t.radiator_kWh:5.1f}  "
              f"coil {t.coil_kWh:6.1f}  peak {t.peak_t_air_C:.2f} C  purge min {t.minutes_above_purge:4d}  "
              f"cold lesson min {t.occupied_minutes_below_lower_limit:3d}")
    t = totals(runs["combined"], params)
    saving = 100 * (1 - (t.radiator_kWh + t.coil_kWh) / base_heat)
    plot_comparison(
        runs["legacy"], runs["combined"], params, Path("out") / "combined_comparison.png",
        title=f"Forecast heating plus supply-temperature control: total heat {saving:+.0f}% vs legacy".replace("+-", "-"),
        new_label="combined", lower="ventilation",
        note="Both controllers combined; forecast part sees perfect weather and room model (best case). ",
    )
    print("PNG: out/combined_comparison.png")


if __name__ == "__main__":
    main()
