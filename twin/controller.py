"""Controllers: what the plant does given the measurements.

``LegacyController`` is the baseline the project wants to beat: fixed timers for
heating and ventilation, an outdoor-temperature heating curve for supply temperature,
and a proportional thermostat on the valve. It knows nothing about occupancy, solar
gain or the forecast, which is what lets the overshoot happen.

Timer windows and the thermostat gain are assumed placeholders (not in params.yaml).
A PID or AI controller later only has to implement ``Controller.act``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Protocol

from .params import ComfortParams, HeatingParams
from .schedule import OperatingWindow
from .sensors import Measurements


@dataclass(frozen=True)
class ControlAction:
    valve_cmd: float  # 0..1, TRV opening
    t_supply_C: float  # radiator supply temperature from the substation
    ventilation_on: bool


class Controller(Protocol):
    def act(self, t: datetime, m: Measurements) -> ControlAction: ...


def heating_curve_C(heating: HeatingParams, t_outdoor_C: float) -> float:
    """Supply temperature: linear between (5 C, mild cap) and (design outdoor, design supply)."""
    warm = 5.0
    if t_outdoor_C >= warm:
        return heating.mild_supply_C
    if t_outdoor_C <= heating.design_outdoor_C:
        return heating.design_supply_C
    frac = (warm - t_outdoor_C) / (warm - heating.design_outdoor_C)
    return heating.mild_supply_C + frac * (heating.design_supply_C - heating.mild_supply_C)


class LegacyController:
    def __init__(
        self,
        heating: HeatingParams,
        comfort: ComfortParams,
        heating_window: OperatingWindow = OperatingWindow(time(5, 30), time(16, 0)),  # assumed
        ventilation_window: OperatingWindow = OperatingWindow(time(7, 0), time(16, 0)),  # assumed
        thermostat_gain_per_K: float = 0.5,  # assumed: valve fully open 2 K below setpoint
    ) -> None:
        self._heating = heating
        self._comfort = comfort
        self._heating_window = heating_window
        self._ventilation_window = ventilation_window
        self._gain = thermostat_gain_per_K

    def act(self, t: datetime, m: Measurements) -> ControlAction:
        if self._heating_window.active(t):
            setpoint = self._comfort.setpoint_C
        else:
            setpoint = self._comfort.setback_unoccupied_C
        valve = max(0.0, min(1.0, self._gain * (setpoint - m.t_air_C)))
        return ControlAction(
            valve_cmd=valve,
            t_supply_C=heating_curve_C(self._heating, m.t_outdoor_C),
            ventilation_on=self._ventilation_window.active(t),
        )
