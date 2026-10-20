# dashboard: building heat monitor

A lightweight page for the client's staff to watch the heat use of several buildings. It is an isolated sub-project: it never imports code from the other parts and gets all its data from the replay feed (`../feed`) over HTTP.

- **Server** (`dashboard/app.py`, FastAPI): serves the page and forwards `/api/buildings`, `/api/readings`, `/api/weather-forecast` and `/api/stream` to the feed, `/api/twin/compare` to the twin service and `/api/forecast/*` to the forecast service. It holds no data. New sources are added here as new routes.
- **Page** (`dashboard/static/`, plain HTML, CSS and JavaScript, no build step): a table of buildings and two charts (heat use, outdoor temperature) for the selected building.

The buildings come from the feed, so adding a building to the frozen file adds it to the page.

## What it shows

Replay controls (play, pause, restart, speed), the simulated clock (data time, UTC+1), and a chart range (last 7 days, last 30 days, whole window). Per building: floor area, heat now (kW), last 24 hours (kWh and kWh per m²) and outdoor temperature. Hover a chart for a crosshair and the values; "Show the last 24 hours as a table" gives the same numbers as text.

The page owns its clock. Pause closes the stream; play opens it again from the last hour received.

The **digital-twin panel** (`static/twin.js`) asks the twin service for a simulated classroom week on the selected building's weather: legacy against combined controller, a totals table, room temperature and heat power charts. It is labelled as a simulation. The server forwards `/api/twin/compare` to the twin service (`TWIN_URL`, default `http://localhost:8002`).

The **AI forecast overlay**: tick "AI forecast made [1 / 6 / 24 h] before" and the heat chart gets a dashed line with what the model predicted for each hour that long before it. The forecasts come from the forecast service (`FORECAST_URL`, default `http://localhost:8003`; the box stays disabled while the service is unreachable). Only hours the replay has already reached are drawn, and each forecast used data up to its own origin only. A note under the chart says the forecast is for the whole building and uses the perfect weather forecast. The server forwards `/api/forecast/series` and `/api/forecast/model`; `/api/forecast/status` reports whether the service answers.

The **AI benchmark in the twin card**: after a simulation the heat-power chart gets a dashed line with the 24 h forecast for the whole building scaled to the room (room m² / building m²), and the table gets the same total in kWh. It is a rough reference only: the building number includes hot water and an average square metre, and no controller reads it. The note under the chart says this. If the forecast service is down or does not cover the period, the card says so and the rest still works.

Not built yet: status colours, and the forecast for the hours after the replay clock.

## Run

Both parts together, from the repository root:

```bash
docker compose up --build
# dashboard: http://localhost:8000      feed: http://localhost:8001/docs
```

On its own (the feed must be running, see `../feed/README.md`):

```bash
cd dashboard
uv sync
FEED_URL=http://localhost:8001 TWIN_URL=http://localhost:8002 FORECAST_URL=http://localhost:8003 uv run uvicorn --factory dashboard.app:create_app --port 8000
```

or `docker build -t pai700-dashboard dashboard && docker run --rm -p 8000:8000 -e FEED_URL=http://host.docker.internal:8001 --add-host host.docker.internal:host-gateway pai700-dashboard`.

## Tests

```bash
cd dashboard && uv run pytest
```
