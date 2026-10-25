"""Dashboard server: serves the static page and forwards /api/* to the replay feed.

The page talks to one origin only. The feed stays the single data source; this server holds no data,
and adding sources later (AI forecasts, twin output) means adding routes here, not changing the feed.

  /api/buildings, /api/readings, /api/weather-forecast, /api/stream   forwarded to the feed unchanged
  /api/forecast/status                                                is the forecast service reachable?
  /api/forecast/series, /api/forecast/model                           forwarded to the forecast service (FORECAST_URL)
  /api/status                                                         building status from heat use (computed here)
  /api/twin/status                                                    is the twin service reachable?
  /api/twin/compare                                                   forwarded to the twin service (TWIN_URL)
  /api/playback, /api/playback/events                                 the shared replay clock: state, and its server-sent events
  POST /api/playback/play|pause|restart|speed                         control the shared clock
  /bms/                                                               the building-management display (static, follows the clock)

Run:  FEED_URL=http://localhost:8001 TWIN_URL=http://localhost:8002 FORECAST_URL=http://localhost:8003 uvicorn --factory dashboard.app:create_app --port 8000
"""
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from dashboard.playback import Playback
from dashboard.status import DAY_H, EXPECTED_HORIZON, HISTORY_DAYS, HORIZONS, assess, summarize

STATIC = Path(__file__).parent / "static"
ORDER = {"alert": 0, "watch": 1, "no_data": 2, "ok": 3}
FEED_ENDPOINTS = {"buildings", "readings", "weather-forecast", "stream"}


class SpeedBody(BaseModel):
    speed: float


FORECAST_ENDPOINTS = {"series": "/forecast/series", "model": "/model"}


def create_app(feed_url: str | None = None,
               transport: httpx.AsyncBaseTransport | None = None, twin_url: str | None = None,
               twin_transport: httpx.AsyncBaseTransport | None = None, forecast_url: str | None = None,
               forecast_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    feed_url = (feed_url or os.environ.get("FEED_URL", "http://localhost:8001")).rstrip("/")
    client = httpx.AsyncClient(base_url=feed_url, transport=transport, timeout=httpx.Timeout(10.0, read=None))
    twin_url = (twin_url or os.environ.get("TWIN_URL", "http://localhost:8002")).rstrip("/")
    twin = httpx.AsyncClient(base_url=twin_url, transport=twin_transport, timeout=120.0)  # a first run takes seconds

    forecast_url = (forecast_url or os.environ.get("FORECAST_URL", "http://localhost:8003")).rstrip("/")
    forecast = httpx.AsyncClient(base_url=forecast_url, transport=forecast_transport, timeout=120.0)

    @asynccontextmanager
    async def lifespan(_):
        yield
        await client.aclose()
        await twin.aclose()
        await forecast.aclose()

    app = FastAPI(title="PAI700 dashboard", lifespan=lifespan)

    playback: Playback | None = None

    async def get_playback() -> Playback:
        """The shared clock, created on first use because it needs the window bounds from the feed."""
        nonlocal playback
        if playback is None:
            try:
                resp = await client.get("/buildings", timeout=10.0)
                resp.raise_for_status()
                w = resp.json()["window"]
            except (httpx.HTTPError, KeyError, ValueError):
                raise HTTPException(502, f"the replay feed at {feed_url} is not reachable")
            playback = Playback(w["first"], w["replay_start"], w["last"])
        return playback

    @app.get("/api/playback")
    async def playback_state():
        return (await get_playback()).state()

    @app.get("/api/playback/events")
    async def playback_events():
        pb = await get_playback()
        return StreamingResponse(pb.events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/playback/speed")
    async def playback_speed(body: SpeedBody):
        pb = await get_playback()
        try:
            pb.set_speed(body.speed)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return pb.state()

    @app.post("/api/playback/{action}")
    async def playback_action(action: str):
        pb = await get_playback()
        if action not in ("play", "pause", "restart"):
            raise HTTPException(404, f"unknown playback action: {action}")
        getattr(pb, action)()
        return pb.state()

    async def forecast_points(building: int, first: datetime, last: datetime, horizons: str) -> dict:
        """Forecast series of one building as {horizon: {target_time: Wh}}; {} when the service cannot answer."""
        try:
            resp = await forecast.get("/forecast/series", params={
                "from": first.isoformat(), "until": last.isoformat(), "building": building, "horizons": horizons})
            resp.raise_for_status()
            series = resp.json()["series"]
        except (httpx.HTTPError, KeyError, ValueError):
            return {}
        return {int(h): {datetime.fromisoformat(p["target_time"]): p["wh"] for p in pts} for h, pts in series.items()}

    @app.get("/api/status")
    async def building_status():
        """Per-building status at the shared clock's hour, from heat use only (see dashboard/status.py)."""
        pb = await get_playback()
        position = pb.state()["position"]
        if position is None:
            return {"as_of": None, "summary": summarize([]), "buildings": [], "note": "The replay has not started."}
        now = datetime.fromisoformat(position)
        first = max(now - timedelta(days=HISTORY_DAYS), pb.first_ts)
        try:
            resp = await client.get("/readings", params={"from": first.isoformat(), "until": now.isoformat()})
            resp.raise_for_status()
            rows = resp.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, f"the replay feed at {feed_url} is not reachable")
        history: dict[int, dict] = {}
        for r in rows:
            history.setdefault(r["building_id"], {})[datetime.fromisoformat(r["timestamp"])] = (r["HtTot"], r["Tout"])

        async def one(building: int, hist: dict) -> dict:
            past, ahead = await asyncio.gather(
                forecast_points(building, now - timedelta(hours=DAY_H - 1 + EXPECTED_HORIZON), now - timedelta(hours=EXPECTED_HORIZON),
                                str(EXPECTED_HORIZON)),
                forecast_points(building, now, now, ",".join(map(str, HORIZONS))))
            return {"building_id": building, **assess(
                now, hist, past.get(EXPECTED_HORIZON, {}),
                {h: next(iter(pts.values())) for h, pts in ahead.items() if pts})}

        buildings = await asyncio.gather(*(one(b, h) for b, h in sorted(history.items())))
        buildings = sorted(buildings, key=lambda b: (ORDER[b["status"]], b["building_id"]))
        return {"as_of": position, "summary": summarize(buildings), "buildings": buildings,
                "note": "Judged on heat use only: there is no indoor temperature in the data. "
                        "Expected heat = the AI forecast, or the building's own recent days where the forecast is missing."}

    @app.get("/api/forecast/status")
    async def forecast_status():
        try:
            return {"available": (await forecast.get("/health", timeout=2.0)).status_code == 200}
        except httpx.HTTPError:
            return {"available": False}

    @app.get("/api/forecast/{name}")
    async def forecast_forward(name: str, request: Request):
        if name not in FORECAST_ENDPOINTS:
            raise HTTPException(404, f"unknown endpoint: forecast/{name}")
        try:
            resp = await forecast.get(FORECAST_ENDPOINTS[name], params=request.query_params.multi_items())
        except httpx.HTTPError:
            raise HTTPException(502, f"the forecast service at {forecast_url} is not reachable")
        return Response(resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))

    @app.get("/api/twin/status")
    async def twin_status():
        try:
            return {"available": (await twin.get("/health", timeout=2.0)).status_code == 200}
        except httpx.HTTPError:
            return {"available": False}

    @app.get("/api/twin/compare")
    async def twin_compare(request: Request):
        try:
            resp = await twin.get("/compare", params=request.query_params.multi_items())
        except httpx.HTTPError:
            raise HTTPException(502, f"the twin service at {twin_url} is not reachable")
        return Response(resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))

    @app.get("/api/{name}")
    async def forward(name: str, request: Request):
        if name not in FEED_ENDPOINTS:
            raise HTTPException(404, f"unknown endpoint: {name}")
        headers = {k: v for k, v in request.headers.items() if k == "last-event-id"}
        req = client.build_request("GET", f"/{name}", params=request.query_params.multi_items(), headers=headers)
        try:
            resp = await client.send(req, stream=True)
        except httpx.HTTPError:
            raise HTTPException(502, f"the replay feed at {feed_url} is not reachable")
        media_type = resp.headers.get("content-type")
        if name == "stream":
            return StreamingResponse(resp.aiter_raw(), status_code=resp.status_code, media_type=media_type,
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                                     background=BackgroundTask(resp.aclose))
        body = await resp.aread()
        await resp.aclose()
        return Response(body, status_code=resp.status_code, media_type=media_type)

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app
