"""Radiator plus valve actuator, on the twin side (decision 2026-10-08).

Output model (all values from params.yaml unless noted):

    q_steady = rated * valve * ((t_mean_water - t_air) / dT_ref) ** n
    t_mean_water = t_supply - (design_supply - design_return) / 2
    dT_ref       = (design_supply + design_return) / 2 - design_room

so the radiator delivers exactly ``rated`` at design supply/return with the valve fully
open and the room at ``design_room_C``. Two simplifications, both placeholders:

* exponent n = 1.3 is a typical radiator exponent (EN 442 style). Assumed, not sourced.
* output is linear in valve position (no valve authority / flow characteristic).

The valve moves at a limited speed (full stroke in ``valve_full_stroke_s``) and the
emitter output follows the steady value as a first-order lag (``response_time_s`` is
used as the time constant).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .params import ActuatorParams, ComfortParams, HeatingParams

RADIATOR_EXPONENT = 1.3  # assumed


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class Radiator:
    rated_output_W: float
    design_supply_C: float
    design_return_C: float
    design_room_C: float
    response_time_s: float
    valve_full_stroke_s: float
    exponent: float = RADIATOR_EXPONENT
    valve_position: float = 0.0  # actual valve opening, 0..1
    q_W: float = 0.0  # current emitter output

    def __post_init__(self) -> None:
        if self.valve_full_stroke_s <= 0 or self.response_time_s <= 0:
            raise ValueError("valve_full_stroke_s and response_time_s must be > 0")
        if self.design_supply_C <= self.design_return_C:
            raise ValueError("design supply temperature must exceed return temperature")

    @classmethod
    def from_params(
        cls, heating: HeatingParams, actuator: ActuatorParams, comfort: ComfortParams
    ) -> "Radiator":
        return cls(
            rated_output_W=heating.radiator_rated_W,
            design_supply_C=heating.design_supply_C,
            design_return_C=heating.design_return_C,
            design_room_C=comfort.setpoint_C,
            response_time_s=heating.radiator_response_s,
            valve_full_stroke_s=actuator.valve_full_stroke_s,
        )

    def steady_output_W(self, valve: float, t_supply_C: float, t_air_C: float) -> float:
        t_mean = t_supply_C - 0.5 * (self.design_supply_C - self.design_return_C)
        d_t = t_mean - t_air_C
        if d_t <= 0.0:
            return 0.0
        d_t_ref = 0.5 * (self.design_supply_C + self.design_return_C) - self.design_room_C
        return self.rated_output_W * valve * (d_t / d_t_ref) ** self.exponent

    def step(self, valve_cmd: float, t_supply_C: float, t_air_C: float, dt_s: float) -> float:
        """Advance valve and emitter by ``dt_s`` and return the emitter output in W."""
        cmd = _clamp(valve_cmd, 0.0, 1.0)
        max_move = dt_s / self.valve_full_stroke_s
        self.valve_position += _clamp(cmd - self.valve_position, -max_move, max_move)
        target = self.steady_output_W(self.valve_position, t_supply_C, t_air_C)
        alpha = 1.0 - math.exp(-dt_s / self.response_time_s)
        self.q_W += alpha * (target - self.q_W)
        return self.q_W
