"""Twin service: runs the digital twin on weather from the replay feed.

  GET /health
  GET /compare?start=2022-11-07&days=5&building=8105
      legacy vs combined (forecast heating + supply-temperature) controller, simulated
      for ``days`` school days from midnight of ``start`` on the feed's weather.

The weather comes from the feed (``FEED_URL``); this service holds no data and never
reads heat values. Results are cached, a combined 5-day run takes several seconds.

Run:  FEED_URL=http://localhost:8001 uvicorn --factory twin_service.app:create_app --port 8002
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from twin.feed_weather import FeedWeather, to_data_clock
from twin.params import load_params

from .runner import PREVIEW_MARGIN_H, compare

MAX_DAYS = 14
DEFAULT_START = "2022-11-07"  # a Monday, after the October daylight-saving shift (see twin/feed_weather.py)


def create_app(feed_url: str | None = None, transport: httpx.BaseTransport | None = None) -> FastAPI:
    feed_url = (feed_url or os.environ.get("FEED_URL", "http://localhost:8001")).rstrip("/")
    params = load_params()
    cache: dict[tuple, dict] = {}
    app = FastAPI(title="PAI700 twin service")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

    def feed_get(client: httpx.Client, path: str, **query):
        try:
            resp = client.get(path, params=query)
        except httpx.HTTPError:
            raise HTTPException(502, f"the replay feed at {feed_url} is not reachable")
        if resp.status_code != 200:
            raise HTTPException(502, f"the replay feed answered {resp.status_code} for {path}")
        return resp.json()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/compare")
    def compare_controllers(
        start: str = DEFAULT_START,
        days: Annotated[int, Query(ge=1, le=MAX_DAYS)] = 5,
        building: int | None = None,
    ):
        try:
            day = date.fromisoformat(start)
        except ValueError:
            raise HTTPException(422, f"start: not an ISO date: {start!r}")
        t0 = datetime.combine(day, time(0, 0))
        with httpx.Client(base_url=feed_url, transport=transport, timeout=30.0) as client:
            info = feed_get(client, "/buildings")
            ids = [b["building_id"] for b in info["buildings"]]
            if building is None:
                building = ids[0]
            elif building not in ids:
                raise HTTPException(404, f"unknown building id: {building}")
            first, last = to_data_clock(info["window"]["first"]), to_data_clock(info["window"]["last"])
            end = t0 + timedelta(days=days)
            if t0 < first or end > last:
                raise HTTPException(422, f"the run {t0:%Y-%m-%d} to {end:%Y-%m-%d} must lie inside the data window "
                                         f"{first:%Y-%m-%d} to {last:%Y-%m-%d}")
            key = (t0, days, building)
            if key not in cache:
                until = min(end + timedelta(hours=PREVIEW_MARGIN_H), last)
                rows = feed_get(client, "/readings", **{"from": f"{t0:%Y-%m-%dT%H:%M}", "until": f"{until:%Y-%m-%dT%H:%M}",
                                                         "building": building})
                weather = FeedWeather(rows, params.zone.south_facade_ratio)
                cache[key] = {
                    "start": f"{t0:%Y-%m-%d}", "days": days, "building": building,
                    "south_facade_ratio": params.zone.south_facade_ratio,
                    **compare(weather, params, t0, days),
                }
        return cache[key]

    return app
