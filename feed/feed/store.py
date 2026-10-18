"""In-memory view of the frozen window: static building info, hourly readings, perfect-forecast weather.

The file is verified against its .sha256 on load. The store is read-only.
"""
from pathlib import Path

import pandas as pd

from feed.freeze import STATIC_COLUMNS, TZ, sha256_of, verify

HEAT_AND_WEATHER = ["HtTot", "Tout", "SolGlob", "WindSpd", "WindDir"]
WEATHER = ["Tout", "SolGlob", "WindSpd", "WindDir"]


def parse_ts(value: str) -> pd.Timestamp:
    """ISO timestamp -> the data's fixed UTC+1 time. A timestamp without offset is taken as data time."""
    ts = pd.Timestamp(value)
    return ts.tz_localize(TZ) if ts.tzinfo is None else ts.tz_convert(TZ)


class Store:
    def __init__(self, path: Path):
        path = Path(path)
        if not path.with_name(path.name + ".sha256").exists():
            raise FileNotFoundError(f"missing checksum file for {path}")
        if not verify(path):
            raise ValueError(f"{path} does not match its checksum; refusing to serve it")
        self.sha256 = sha256_of(path)
        df = pd.read_parquet(path)

        static = df.drop_duplicates("building_id").set_index("building_id")[STATIC_COLUMNS]
        self.buildings = [{"building_id": int(b), "floor_area": float(r["floor_area"]),
                           "year_of_construction": int(r["year_of_construction"])}
                          for b, r in static.sort_index().iterrows()]
        self.building_ids = {b["building_id"] for b in self.buildings}

        self.hours = pd.DatetimeIndex(sorted(df["timestamp"].unique()))
        by_hour = {h: [] for h in self.hours}
        for r in df.to_dict("records"):
            by_hour[r["timestamp"]].append(r)
        self._readings = [[self._reading(r) for r in by_hour[h]] for h in self.hours]
        self._weather = [[{k: v for k, v in r.items() if k not in ("HtTot", "phase")} for r in rows]
                         for rows in self._readings]
        self.first, self.last = self.hours[0], self.hours[-1]
        self.replay_start = pd.Timestamp(df.loc[df["phase"] == "replay", "timestamp"].min())

    @staticmethod
    def _reading(r: dict) -> dict:
        out = {"timestamp": r["timestamp"].isoformat(), "building_id": int(r["building_id"]), "phase": r["phase"]}
        out.update({c: float(r[c]) for c in HEAT_AND_WEATHER})
        return out

    def info(self) -> dict:
        return {"buildings": self.buildings, "sha256": self.sha256,
                "window": {"first": self.first.isoformat(), "replay_start": self.replay_start.isoformat(),
                           "last": self.last.isoformat()},
                "units": {"HtTot": "Wh per hour", "Tout": "C", "SolGlob": "W/m2", "WindSpd": "m/s",
                          "WindDir": "degrees", "floor_area": "m2"}}

    def index_at_or_after(self, ts: pd.Timestamp) -> int:
        """Index of the first hour >= ts (len(hours) if there is none)."""
        return int(self.hours.searchsorted(ts, side="left"))

    def index_after(self, ts: pd.Timestamp) -> int:
        return int(self.hours.searchsorted(ts, side="right"))

    def hour_rows(self, i: int, buildings=None) -> list[dict]:
        return self._select(self._readings[i], buildings)

    def readings(self, until: pd.Timestamp, from_: pd.Timestamp | None = None, buildings=None) -> list[dict]:
        """Heat + weather for first <= from_ <= t <= until. Nothing after `until` is ever returned."""
        lo = 0 if from_ is None else self.index_at_or_after(from_)
        hi = self.index_after(until)
        return [r for i in range(lo, hi) for r in self._select(self._readings[i], buildings)]

    def weather_ahead(self, now: pd.Timestamp, hours: int, buildings=None) -> list[dict]:
        """Measured weather (no heat) for the `hours` hours after `now`: a perfect forecast."""
        lo = self.index_after(now)
        hi = self.index_after(now + pd.Timedelta(hours=hours))
        return [r for i in range(lo, hi) for r in self._select(self._weather[i], buildings)]

    @staticmethod
    def _select(rows: list[dict], buildings) -> list[dict]:
        return rows if not buildings else [r for r in rows if r["building_id"] in buildings]
