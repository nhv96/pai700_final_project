"""Forecast-based heating controller: pre-heats as late as possible and lets the sun help.

Compared with ``LegacyController`` it changes the HEATING only (ventilation timer and
heating curve for supply temperature stay as they are). It does two things:

1. Optimal start. Before the school day it heats only when it must: it asks the twin
   "if I heat at full valve from now, will the room reach the setpoint by the first
   lesson?" and starts at the first moment the answer is "only just". A sunny or mild
   morning therefore starts later, a cold one earlier.
2. Look-ahead thermostat during the day. Instead of reading the room temperature now,
   it asks "where will the room be in ``lookahead`` if the valve closes now?" and opens
   the valve in proportion to how far THAT is below the setpoint. Sun, people and the
   heat stored in the walls close the valve early, before the room overshoots.

The "asking" is ``DigitalTwin.preview``: a perfect forecast of the weather and a perfect
copy of the room model. This is the best case. A real controller has forecast errors and
an imperfect model, so its benefit would be smaller.

Assumed values (not in params.yaml): ``lookahead`` 60 min, ``max_preheat`` 6 h,
``decision_every`` 5 min, thermostat gain 0.5 per K (same as the legacy controller).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING

from .controller import ControlAction, heating_curve_C
from .params import ComfortParams, HeatingParams, OccupancyParams
from .schedule import OperatingWindow
from .sensors import Measurements

if TYPE_CHECKING:  # avoid a circular import at runtime
    from .simulation import DigitalTwin


@dataclass(frozen=True)
class _HoldValve:
    """Controller used inside a preview: hold one valve command, same timers as the plant."""

    valve: float
    heating: HeatingParams
    ventilation_window: OperatingWindow

    def act(self, t: datetime, m: Measurements) -> ControlAction:
        return ControlAction(
            valve_cmd=self.valve,
            t_supply_C=heating_curve_C(self.heating, m.t_outdoor_C),
            ventilation_on=self.ventilation_window.active(t),
        )


class ForecastController:
    def __init__(
        self,
        heating: HeatingParams,
        comfort: ComfortParams,
        occupancy: OccupancyParams,
        ventilation_window: OperatingWindow = OperatingWindow(time(7, 0), time(16, 0)),  # as legacy
        lookahead: timedelta = timedelta(minutes=60),  # assumed
        max_preheat: timedelta = timedelta(hours=6),  # assumed
        decision_every: timedelta = timedelta(minutes=5),  # assumed
        thermostat_gain_per_K: float = 0.5,  # same as legacy
    ) -> None:
        self._heating = heating
        self._comfort = comfort
        self._ventilation_window = ventilation_window
        self._lookahead = lookahead
        self._max_preheat = max_preheat
        self._every = decision_every
        self._gain = thermostat_gain_per_K
        self._day_start = min(b.start for b in occupancy.blocks if b.occupancy_fraction > 0)
        self._day_end = max(b.end for b in occupancy.blocks if b.occupancy_fraction > 0)
        self._twin: DigitalTwin | None = None
        self._preview_wrapper = None
        self._last_decision: datetime | None = None
        self._valve = 0.0

    def bind(self, twin: DigitalTwin) -> None:
        """Give the controller the twin it may preview. Call once after building the twin."""
        self._twin = twin

    def set_preview_wrapper(self, wrapper) -> None:
        """Wrap the controller used inside previews, so the forecast sees the same extra
        control (e.g. supply temperature) that the real plant applies."""
        self._preview_wrapper = wrapper

    # -- schedule helpers -------------------------------------------------------------
    def _in_school_day(self, t: datetime) -> bool:
        return t.weekday() < 5 and self._day_start <= t.time() < self._day_end

    def _next_day_start(self, t: datetime) -> datetime:
        for offset in range(8):
            d = (t + timedelta(days=offset)).date()
            candidate = datetime.combine(d, self._day_start)
            if candidate.weekday() < 5 and candidate > t:
                return candidate
        raise RuntimeError("no school day found within a week")  # unreachable

    # -- decision ---------------------------------------------------------------------
    def _temp_after(self, valve: float, horizon: timedelta) -> float:
        assert self._twin is not None
        plan = _HoldValve(valve, self._heating, self._ventilation_window)
        if self._preview_wrapper is not None:
            plan = self._preview_wrapper(plan)
        return self._twin.preview(plan, horizon)[-1].t_air_C

    def _decide_valve(self, t: datetime, m: Measurements) -> float:
        c = self._comfort
        if self._in_school_day(t):
            t_free = self._temp_after(0.0, self._lookahead)
            return _clamp(self._gain * (c.setpoint_C - t_free))

        start = self._next_day_start(t)
        until_start = start - t
        if until_start <= self._max_preheat:
            # Heat now only if starting later would miss the setpoint at the first lesson.
            t_full = self._temp_after(1.0, until_start)
            if t_full <= c.setpoint_C:
                return 1.0
        return _clamp(self._gain * (c.setback_unoccupied_C - m.t_air_C))

    def act(self, t: datetime, m: Measurements) -> ControlAction:
        if self._twin is None:
            raise RuntimeError("ForecastController needs bind(twin) before use")
        if self._last_decision is None or t - self._last_decision >= self._every:
            self._valve = self._decide_valve(t, m)
            self._last_decision = t
        return ControlAction(
            valve_cmd=self._valve,
            t_supply_C=heating_curve_C(self._heating, m.t_outdoor_C),
            ventilation_on=self._ventilation_window.active(t),
        )


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))
