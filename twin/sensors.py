"""Sensors. v0 is ideal: readings equal the true values (no noise, delay or dropouts).

Sensor specs for the realism phase are recorded in config/params.yaml (``sensors:``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .interface import ZoneState
from .weather import WeatherSample


@dataclass(frozen=True)
class Measurements:
    t_air_C: float
    t_outdoor_C: float
    occupants: int


class IdealSensors:
    def read(self, state: ZoneState, weather: WeatherSample, occupants: int) -> Measurements:
        return Measurements(
            t_air_C=state.t_air_C,
            t_outdoor_C=weather.t_outdoor_C,
            occupants=occupants,
        )
