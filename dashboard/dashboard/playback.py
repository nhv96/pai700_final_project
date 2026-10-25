"""Server-side replay clock shared by every page (the playback console and the BMS display).

The feed has no "now": each client declares its own. Here one clock is kept for all of them, so a page can
pause or speed it up and another page follows. Time is counted in simulated hours since the first hour of the
window; `speed` is simulated hours per real second, the same unit as the feed's /stream.

The clock is lazy: while playing it is computed from the real time that has passed, nothing ticks in the
background. Pages learn about changes (and about each new hour) from `events()`.
"""
import asyncio
import json
import math
import time
from datetime import datetime, timedelta
from typing import AsyncIterator, Callable

DEFAULT_SPEED = 24.0         # 1 day per second, the same default as the old page
MAX_SPEED = 720.0
KEEPALIVE_S = 15.0           # a comment line now and then keeps proxies from closing an idle stream


class Playback:
    def __init__(self, first: str, replay_start: str, last: str, clock: Callable[[], float] = time.monotonic):
        self.first_ts, self.replay_start_ts, self.last_ts = (datetime.fromisoformat(x) for x in (first, replay_start, last))
        self.total_h = (self.last_ts - self.first_ts) / timedelta(hours=1)
        self.speed = DEFAULT_SPEED
        self._clock = clock
        self._offset = 0.0           # simulated hours since the first hour, as of `_since`
        self._since = clock()
        self.playing = False
        self.started = False         # has the replay been played since the last restart?
        self._subscribers: set[asyncio.Event] = set()

    # ---------- clock ----------

    def _now_offset(self) -> float:
        if not self.playing:
            return self._offset
        return min(self.total_h, self._offset + (self._clock() - self._since) * self.speed)

    def _settle(self) -> None:
        """Fold the elapsed real time into the offset; stop at the end of the window."""
        self._offset = self._now_offset()
        self._since = self._clock()
        if self.playing and self._offset >= self.total_h:
            self.playing = False

    def _changed(self) -> None:
        for event in self._subscribers:
            event.set()

    # ---------- commands ----------

    def play(self) -> None:
        self._settle()
        if not self.playing and self._offset < self.total_h:
            self.playing = self.started = True
            self._since = self._clock()
        self._changed()

    def pause(self) -> None:
        self._settle()
        self.playing = False
        self._changed()

    def restart(self) -> None:
        """Back to the first hour, playing."""
        self._offset = 0.0
        self.playing = self.started = False
        self.play()

    def set_speed(self, speed: float) -> None:
        if not math.isfinite(speed) or not 0 < speed <= MAX_SPEED:
            raise ValueError(f"speed must be above 0 and at most {MAX_SPEED:g} hours per second")
        self._settle()
        self.speed = float(speed)
        self._changed()

    # ---------- state ----------

    def state(self) -> dict:
        self._settle()
        position = None
        if self.started:
            ts = self.first_ts + timedelta(hours=math.floor(self._offset))
            position = ts.isoformat()
        else:
            ts = None
        phase = None if ts is None else ("replay" if ts >= self.replay_start_ts else "warmup")
        return {"playing": self.playing, "started": self.started, "finished": self._offset >= self.total_h,
                "speed": self.speed, "position": position, "phase": phase,
                "progress": self._offset / self.total_h if self.total_h else 1.0,
                "window": {"first": self.first_ts.isoformat(), "replay_start": self.replay_start_ts.isoformat(),
                           "last": self.last_ts.isoformat()}}

    def _seconds_to_next_hour(self) -> float | None:
        if not self.playing:
            return None
        return max(0.0, (math.floor(self._now_offset()) + 1 - self._now_offset()) / self.speed)

    async def events(self) -> AsyncIterator[str]:
        """Server-sent events: the state now, then again after every change and every simulated hour."""
        wake = asyncio.Event()
        self._subscribers.add(wake)
        try:
            while True:
                wake.clear()
                yield f"event: state\ndata: {json.dumps(self.state())}\n\n"
                wait = self._seconds_to_next_hour()
                try:
                    await asyncio.wait_for(wake.wait(), timeout=KEEPALIVE_S if wait is None else min(wait, KEEPALIVE_S))
                except asyncio.TimeoutError:
                    if wait is None:
                        yield ": keepalive\n\n"
        finally:
            self._subscribers.discard(wake)
