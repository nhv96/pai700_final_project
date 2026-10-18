"""Room-compensated supply air temperature: heat the ventilation air only as much as the
room needs.

The legacy plant always heats supply air up to the room setpoint, even when the room is
already warm from sun and people. That heating is the largest energy cost in the twin and
it works against the room (the purge then blows more of that costly air in). This wrapper
keeps whatever the inner controller does for the radiator and the ventilation timer, and
only lowers the coil target when the room is above the setpoint:

    target = clamp(setpoint - gain * (T_room - setpoint), min_supply, setpoint)

So a room at or below setpoint gets the legacy 21 C; a warm room gets colder supply air,
never below ``min_supply_C`` (draught and comfort limit).

Assumed values (not in params.yaml): ``min_supply_C`` 16 C (chosen by the user),
``gain_per_K`` 2.0 (every K above setpoint lowers the target by 2 K).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .controller import ControlAction, Controller
from .params import ComfortParams
from .sensors import Measurements


class SupplyTempController:
    def __init__(
        self,
        inner: Controller,
        comfort: ComfortParams,
        min_supply_C: float = 16.0,  # assumed
        gain_per_K: float = 2.0,  # assumed
    ) -> None:
        if min_supply_C > comfort.setpoint_C:
            raise ValueError("min_supply_C must not exceed the room setpoint")
        self._inner = inner
        self._comfort = comfort
        self._setpoint = comfort.setpoint_C
        self._min = min_supply_C
        self._gain = gain_per_K

    def bind(self, twin) -> None:
        """Pass the twin on to the inner controller if it needs one (e.g. a predictive one)."""
        if hasattr(self._inner, "set_preview_wrapper"):
            self._inner.set_preview_wrapper(
                lambda c: SupplyTempController(c, self._comfort, self._min, self._gain)
            )
        if hasattr(self._inner, "bind"):
            self._inner.bind(twin)

    def act(self, t: datetime, m: Measurements) -> ControlAction:
        action = self._inner.act(t, m)
        target = self._setpoint - self._gain * (m.t_air_C - self._setpoint)
        return replace(action, air_supply_target_C=max(self._min, min(self._setpoint, target)))
