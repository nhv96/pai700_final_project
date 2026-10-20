"""Dashboard server: serves the static page and forwards /api/* to the replay feed.

The page talks to one origin only. The feed stays the single data source; this server holds no data,
and adding sources later (AI forecasts, twin output) means adding routes here, not changing the feed.

  /api/buildings, /api/readings, /api/weather-forecast, /api/stream   forwarded to the feed unchanged
  /api/forecast/status                                                is the forecast service reachable?
  /api/forecast/series, /api/forecast/model                           forwarded to the forecast service (FORECAST_URL)
  /api/twin/compare                                                   forwarded to the twin service (TWIN_URL)

Run:  FEED_URL=http://localhost:8001 TWIN_URL=http://localhost:8002 FORECAST_URL=http://localhost:8003 uvicorn --factory dashboard.app:create_app --port 8000
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

STATIC = Path(__file__).parent / "static"
FEED_ENDPOINTS = {"buildings", "readings", "weather-forecast", "stream"}


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
