"""Occupancy schedule and plant operating windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from .params import OccupancyParams, ScheduleBlock


@dataclass(frozen=True)
class OperatingWindow:
    """Fixed daily on/off window, as run by a legacy timer (heating or ventilation)."""

    start: time
    end: time
    weekdays_only: bool = True

    def active(self, t: datetime) -> bool:
        if self.weekdays_only and t.weekday() >= 5:
            return False
        return self.start <= t.time() < self.end


class OccupancySchedule:
    """Weekday blocks from params.yaml; weekends use a flat occupancy fraction.

    Public holidays and school breaks are not modelled in v0.
    """

    def __init__(self, params: OccupancyParams) -> None:
        self._p = params

    def fraction(self, t: datetime) -> float:
        """Share of pupils present at time ``t`` (0..1)."""
        if t.weekday() >= 5:
            return self._p.weekend_occupancy
        now = t.time()
        for block in self._p.blocks:
            if _in_block(block, now):
                return block.occupancy_fraction
        return 0.0

    def occupants(self, t: datetime) -> int:
        """Pupils plus teachers present. The teacher is present whenever pupils are."""
        frac = self.fraction(t)
        if frac <= 0.0:
            return 0
        return round(self._p.pupils * frac) + self._p.teachers


def _in_block(block: ScheduleBlock, now: time) -> bool:
    return block.start <= now < block.end
