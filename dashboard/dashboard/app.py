"""Dashboard server: serves the static page and forwards /api/* to the replay feed.

The page talks to one origin only. The feed stays the single data source; this server holds no data,
and adding sources later (AI forecasts, twin output) means adding routes here, not changing the feed.

  /api/buildings, /api/readings, /api/weather-forecast, /api/stream   forwarded to the feed unchanged
  /api/forecast/status                                                is an AI forecasts file present?

Run:  FEED_URL=http://localhost:8001 uvicorn --factory dashboard.app:create_app --port 8000
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


def create_app(feed_url: str | None = None, forecasts_path: str | None = None,
               transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    feed_url = (feed_url or os.environ.get("FEED_URL", "http://localhost:8001")).rstrip("/")
    forecasts = forecasts_path or os.environ.get("DASHBOARD_FORECASTS")
    client = httpx.AsyncClient(base_url=feed_url, transport=transport, timeout=httpx.Timeout(10.0, read=None))

    @asynccontextmanager
    async def lifespan(_):
        yield
        await client.aclose()

    app = FastAPI(title="PAI700 dashboard", lifespan=lifespan)

    @app.get("/api/forecast/status")
    def forecast_status():
        return {"available": bool(forecasts) and Path(forecasts).is_file()}

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
