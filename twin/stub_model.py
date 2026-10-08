"""Placeholder heat model, used until the teammate's room equation is plugged in."""

from __future__ import annotations

from dataclasses import replace

from .interface import StepInputs, ZoneState


class StubHeatModel:
    """Returns the state unchanged, or pins the air temperature to a fixed value.

    This does NOT reproduce any physics. It only lets the rest of the twin
    (schedule, weather, radiator, ventilation, controller, loop) run end to end.
    """

    def __init__(self, fixed_t_air_C: float | None = None) -> None:
        self.fixed_t_air_C = fixed_t_air_C

    def step(self, state: ZoneState, inputs: StepInputs, dt_s: float) -> ZoneState:
        if self.fixed_t_air_C is None:
            return state
        return replace(state, t_air_C=self.fixed_t_air_C)
