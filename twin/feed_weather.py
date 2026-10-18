"""Weather from hourly readings of the replay feed (``feed/``).

Pure data in, no HTTP: the caller passes the hourly rows, so the class is easy to test
and the twin keeps no dependency on the feed service.

* Temperature is interpolated linearly between the hourly values.
* Sun is interpolated linearly too, then multiplied by ``south_facade_ratio``. The feed
  gives sun on a HORIZONTAL surface (``SolGlob``); the room model needs sun on the south
  facade. One fixed ratio is a crude, assumed conversion (see params.yaml ``solar:``).
* Times are the data's own clock: fixed UTC+1 all year, no daylight saving. The twin's
  naive datetimes are read on that same clock, so in a window that includes October
  the school day is one hour earlier than the wall clock before 30 October.
* Outside the data the first or last hour is held (no extrapolation).
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone

from .weather import WeatherSample

DATA_TZ = timezone(timedelta(hours=1))  # the feed's clock


def to_data_clock(timestamp: str) -> datetime:
    """Parse an ISO timestamp from the feed to a naive datetime on the data clock."""
    t = datetime.fromisoformat(timestamp)
    if t.tzinfo is not None:
        t = t.astimezone(DATA_TZ).replace(tzinfo=None)
    return t


class FeedWeather:
    def __init__(self, readings: Iterable[Mapping], south_facade_ratio: float) -> None:
        rows = sorted((to_data_clock(r["timestamp"]), float(r["Tout"]), float(r["SolGlob"])) for r in readings)
        if not rows:
            raise ValueError("FeedWeather needs at least one reading")
        if south_facade_ratio < 0:
            raise ValueError("south_facade_ratio must not be negative")
        self._times = [r[0] for r in rows]
        self._tout = [r[1] for r in rows]
        self._sun = [max(r[2], 0.0) * south_facade_ratio for r in rows]  # sensor noise can go below 0

    @property
    def first(self) -> datetime:
        return self._times[0]

    @property
    def last(self) -> datetime:
        return self._times[-1]

    def at(self, t: datetime) -> WeatherSample:
        i = bisect_right(self._times, t) - 1
        if i < 0:
            return WeatherSample(self._tout[0], self._sun[0])
        if i >= len(self._times) - 1:
            return WeatherSample(self._tout[-1], self._sun[-1])
        span = (self._times[i + 1] - self._times[i]).total_seconds()
        f = (t - self._times[i]).total_seconds() / span
        return WeatherSample(
            self._tout[i] + f * (self._tout[i + 1] - self._tout[i]),
            self._sun[i] + f * (self._sun[i + 1] - self._sun[i]),
        )
