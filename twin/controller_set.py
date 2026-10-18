"""The standard set of controllers that the scenarios and the twin service compare.

Controllers hold state, so build a fresh set for every run.
"""

from __future__ import annotations

from .controller import LegacyController
from .params import TwinParams
from .predictive_controller import ForecastController
from .supply_controller import SupplyTempController

MIN_SUPPLY_C = 16.0  # assumed, see docs/controllers-and-scenario.md


def make_controllers(
    params: TwinParams, min_supply_C: float = MIN_SUPPLY_C, supply_gain: float = 2.0, **forecast_kw
):
    """Fresh controllers for the four cases: legacy, forecast heating, supply temp, combined."""
    h, c, o = params.heating, params.comfort, params.occupancy
    return {
        "legacy": LegacyController(h, c),
        "forecast heating": ForecastController(h, c, o, **forecast_kw),
        "supply temp": SupplyTempController(LegacyController(h, c), c, min_supply_C=min_supply_C, gain_per_K=supply_gain),
        "combined": SupplyTempController(
            ForecastController(h, c, o, **forecast_kw), c, min_supply_C=min_supply_C, gain_per_K=supply_gain
        ),
    }
