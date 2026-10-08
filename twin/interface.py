"""Interface contract between the digital twin and the heat-model blackbox.

Agreed in the 2026-10-08 handoff (still to be confirmed with the heat-model owner):

* The twin computes ``q_radiator_W`` (from valve position and supply temperature)
  and passes it to the model. The model does not compute radiator output.
* The model owns the room equation:
  C * dT_in/dt = Q_heating + Q_internal + Q_solar - (T_in - T_out)/R - Q_ventilation
* Open assumptions for the heat-model owner:
  - the model derives Q_solar from ``solar_irradiance_W_m2`` (window area and g-value
    are in params.yaml, but the twin does not pass a ready-made Q_solar);
  - the model derives Q_ventilation from ``ventilation_flow_L_s``,
    ``supply_air_temp_C`` and ``heat_recovery_eff``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StepInputs:
    """Everything the twin hands to the heat model for one step."""

    t_outdoor_C: float
    solar_irradiance_W_m2: float
    occupants: int
    q_internal_W: float  # people + lighting + equipment
    q_radiator_W: float
    ventilation_flow_L_s: float
    supply_air_temp_C: float  # air entering the ventilation heat recovery (= outdoor air in v0)
    heat_recovery_eff: float  # 0 = no heat recovery


@dataclass(frozen=True)
class ZoneState:
    """State returned by the heat model.

    Only ``t_air_C`` is required by the twin. A model may return a subclass carrying
    extra internal state (wall temperature, ...); the twin passes it back unchanged.
    """

    t_air_C: float


class HeatModel(Protocol):
    """Blackbox room model. One call advances the zone by ``dt_s`` seconds."""

    def step(self, state: ZoneState, inputs: StepInputs, dt_s: float) -> ZoneState: ...
