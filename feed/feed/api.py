"""HTTP replay feed over the frozen window.

  GET /health
  GET /buildings                                  static info, window bounds, checksum, units
  GET /readings?until=&from=&building=            heat + weather for from <= t <= until (until required)
  GET /weather-forecast?now=&hours=&building=     measured weather of the next hours, no heat ("perfect forecast")
  GET /stream?speed=&from=&building=              server-sent events, one event per simulated hour

Clocks are independent: the server has no "now". Each client declares its own (`until`, `now`, or the
position of its stream), and heat values after that moment are never returned.

Run:  FEED_DATA=../frozen/oslo_window_v1.parquet uvicorn --factory feed.api:create_app --port 8001
"""
import asyncio
import json
import math
import os
import time
from typing import Annotated

import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from feed.store import Store, parse_ts

DEFAULT_DATA = "../frozen/oslo_window_v1.parquet"
MAX_FORECAST_HOURS = 168
FORECAST_NOTE = "Measured weather replayed as a perfect forecast. Not a real forecast."

Buildings = Annotated[list[int] | None, Query(description="building ids; all if omitted")]


def create_app(data_path: str | None = None) -> FastAPI:
    store = Store(data_path or os.environ.get("FEED_DATA", DEFAULT_DATA))
    app = FastAPI(title="PAI700 replay feed")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

    def ts_param(name: str, value: str) -> pd.Timestamp:
        try:
            return parse_ts(value)
        except (ValueError, TypeError):
            raise HTTPException(422, f"{name}: not a valid ISO timestamp: {value!r}")

    def check_buildings(buildings):
        unknown = set(buildings or []) - store.building_ids
        if unknown:
            raise HTTPException(404, f"unknown building id(s): {sorted(unknown)}")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/buildings")
    def buildings():
        return store.info()

    @app.get("/readings")
    def readings(until: str, from_: Annotated[str | None, Query(alias="from")] = None, building: Buildings = None):
        check_buildings(building)
        lo = ts_param("from", from_) if from_ else None
        return store.readings(ts_param("until", until), lo, building)

    @app.get("/weather-forecast")
    def weather_forecast(now: str, hours: Annotated[int, Query(ge=1, le=MAX_FORECAST_HOURS)] = 24,
                         building: Buildings = None):
        check_buildings(building)
        return {"note": FORECAST_NOTE, "weather": store.weather_ahead(ts_param("now", now), hours, building)}

    @app.get("/stream")
    async def stream(speed: Annotated[float, Query(gt=0)] = 1.0,
                     from_: Annotated[str | None, Query(alias="from")] = None,
                     building: Buildings = None,
                     last_event_id: Annotated[str | None, Header()] = None):
        """Push one event per simulated hour, `speed` hours per real second. Starts at the warm-up by default.

        To pause or change speed, close the stream and open a new one with `from`. A reconnect with
        Last-Event-ID (sent by browsers automatically) continues after the last hour received.
        """
        if not math.isfinite(speed):
            raise HTTPException(422, "speed must be finite")
        check_buildings(building)
        if from_:
            start = store.index_at_or_after(ts_param("from", from_))
        elif last_event_id:
            start = store.index_after(ts_param("Last-Event-ID", last_event_id))
        else:
            start = 0

        async def events():
            t0 = time.monotonic()
            for n, i in enumerate(range(start, len(store.hours))):
                delay = t0 + n / speed - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                ts = store.hours[i].isoformat()
                payload = {"timestamp": ts, "readings": store.hour_rows(i, building)}
                yield f"id: {ts}\nevent: reading\ndata: {json.dumps(payload)}\n\n"
            yield f"event: end\ndata: {json.dumps({'last': store.last.isoformat()})}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
