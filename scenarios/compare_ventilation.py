"""Compare the legacy ventilation (coil always heats supply air to the room setpoint) with
room-compensated supply air temperature. Run:

    uv run python -m scenarios.compare_ventilation

Same weather, same start state, same legacy radiator control and ventilation timer; only
the coil target changes (see twin/supply_controller.py). Writes
``out/ventilation_comparison.png`` and the two CSV files, and prints a table including a
check on the assumed minimum supply temperature.
"""

from __future__ import annotations

from pathlib import Path

from scenarios.compare_controllers import DAYS, totals
from scenarios.overshoot import run, write_csv
from scenarios.plot import plot_comparison
from twin.controller import LegacyController
from twin.params import load_params
from twin.supply_controller import SupplyTempController

MIN_SUPPLY_C = 16.0  # chosen by the user (draught and comfort limit)


def main() -> None:
    params = load_params()

    def controller(min_supply_C: float) -> SupplyTempController:
        return SupplyTempController(
            LegacyController(params.heating, params.comfort), params.comfort, min_supply_C=min_supply_C
        )

    legacy = run(params, days=DAYS)
    new = run(params, days=DAYS, controller=controller(MIN_SUPPLY_C))
    write_csv(legacy, Path("out") / "ventilation_comparison_legacy.csv")
    write_csv(new, Path("out") / "ventilation_comparison_supply_temp.csv")
    t_leg, t_new = totals(legacy, params), totals(new, params)
    saving = 100 * (1 - (t_new.radiator_kWh + t_new.coil_kWh) / (t_leg.radiator_kWh + t_leg.coil_kWh))
    plot_comparison(
        legacy, new, params, Path("out") / "ventilation_comparison.png",
        title=f"Heating the ventilation air only as needed cuts total heat by {saving:.0f}% and most of the purge",
        new_label="supply-temp", lower="ventilation",
        note=f"Coil target falls with room temperature, minimum {MIN_SUPPLY_C:.0f} °C (assumed). ",
    )
    print(f"{DAYS} days, per-controller totals")
    print(f"  legacy              {t_leg}")
    print(f"  supply-temp {MIN_SUPPLY_C:.0f} C     {t_new}")
    print(f"  total heat saving: {saving:.1f} %")
    for m in (18.0,):
        print(f"  supply-temp {m:.0f} C     {totals(run(params, days=DAYS, controller=controller(m)), params)}")
    print("PNG: out/ventilation_comparison.png")


if __name__ == "__main__":
    main()
