# dashboard: playback console and building display

Two pages served by one small server. It is an isolated sub-project: it never imports code from the other parts and gets all its data over HTTP.

- **Playback console** (`/`, `dashboard/static/`): play, pause, restart and speed of the replay, the simulated clock (data time, UTC+1), progress in the window and whether the feed, twin and forecast services are reachable. It controls the clock behind the scenes; it shows no building data.
- **Building display** (`/bms/`, `dashboard/static/bms/`): the management display for the client. It shows the replayed buildings, a simulated classroom and the AI forecast, and follows the clock. Read-only. See `static/bms/README.md`.
- **Server** (`dashboard/app.py`, FastAPI): holds the shared replay clock and forwards `/api/buildings`, `/api/readings`, `/api/weather-forecast` and `/api/stream` to the feed, `/api/twin/*` to the twin service and `/api/forecast/*` to the forecast service. It holds no data besides the clock.

The buildings come from the feed, so adding a building to the frozen file adds it to the display.

## Shared replay clock and the BMS display

The server keeps one replay clock for all pages (`dashboard/playback.py`): `GET /api/playback` (state), `GET /api/playback/events` (server-sent events: the state now, then after every change and every simulated hour) and `POST /api/playback/play|pause|restart` and `POST /api/playback/speed` with `{"speed": hours_per_second}`. The window bounds come from the feed; the feed itself stays without a clock. The clock stops at the end of the window and `restart` goes back to the first hour.

The building display (the former `bms-dashboard/`, work of a teammate) lives in `dashboard/static/bms/` and is served at `/bms/`. It reads our API and follows this clock; the console at `/` controls it.

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
