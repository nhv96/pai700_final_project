"""Weather sources for the twin.

v0 ships only offline sources. The SMHI loader (hourly observations, station id and
solar radiation source still to be resolved, see config/params.yaml) comes later and
only has to implement ``Weather.at``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class WeatherSample:
    t_outdoor_C: float
    solar_irradiance_W_m2: float


class Weather(Protocol):
    def at(self, t: datetime) -> WeatherSample: ...


class ConstantWeather:
    def __init__(self, t_outdoor_C: float, solar_irradiance_W_m2: float = 0.0) -> None:
        self._sample = WeatherSample(t_outdoor_C, solar_irradiance_W_m2)

    def at(self, t: datetime) -> WeatherSample:
        return self._sample


class SyntheticWeather:
    """Smooth daily cycle, deterministic. A placeholder, not a climate model.

    Temperature is a sine around ``mean_C`` peaking at ``temp_peak_hour``. Solar is a
    half-sine between sunrise and sunset scaled by ``solar_peak_W_m2``. Defaults are
    arbitrary autumn-like values, not fitted to Trollhattan.
    """

    def __init__(
        self,
        mean_C: float = 5.0,
        daily_amplitude_K: float = 3.0,
        temp_peak_hour: float = 15.0,
        sunrise_hour: float = 7.0,
        sunset_hour: float = 17.0,
        solar_peak_W_m2: float = 300.0,
    ) -> None:
        if sunset_hour <= sunrise_hour:
            raise ValueError("sunset_hour must be after sunrise_hour")
        self.mean_C = mean_C
        self.daily_amplitude_K = daily_amplitude_K
        self.temp_peak_hour = temp_peak_hour
        self.sunrise_hour = sunrise_hour
        self.sunset_hour = sunset_hour
        self.solar_peak_W_m2 = solar_peak_W_m2

    def at(self, t: datetime) -> WeatherSample:
        hour = t.hour + t.minute / 60.0 + t.second / 3600.0
        temp = self.mean_C + self.daily_amplitude_K * math.cos(
            2.0 * math.pi * (hour - self.temp_peak_hour) / 24.0
        )
        if self.sunrise_hour < hour < self.sunset_hour:
            frac = (hour - self.sunrise_hour) / (self.sunset_hour - self.sunrise_hour)
            solar = self.solar_peak_W_m2 * math.sin(math.pi * frac)
        else:
            solar = 0.0
        return WeatherSample(temp, solar)
