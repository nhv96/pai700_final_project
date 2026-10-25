# dashboard: playback console and building display

Two pages served by one small server. It is an isolated sub-project: it never imports code from the other parts and gets all its data over HTTP.

- **Playback console** (`/`, `dashboard/static/`): play, pause, restart and speed of the replay, the simulated clock (data time, UTC+1), progress in the window and whether the feed, twin and forecast services are reachable. It controls the clock behind the scenes; it shows no building data.
- **Building display** (`/bms/`, `dashboard/static/bms/`): the management display for the client. It shows the replayed buildings, a simulated classroom and the AI forecast, and follows the clock. Read-only. See `static/bms/README.md`.
- **Server** (`dashboard/app.py`, FastAPI): holds the shared replay clock and forwards `/api/buildings`, `/api/readings`, `/api/weather-forecast` and `/api/stream` to the feed, `/api/twin/*` to the twin service and `/api/forecast/*` to the forecast service. It computes one thing itself, `GET /api/status` (below), and holds no data besides the clock.

## Building status (`GET /api/status`)

Answers "which building needs attention?" at the shared clock's hour, from heat use only (there is no indoor temperature in the data, so "overheating" means "more heat than expected"). Logic: `dashboard/status.py`; thresholds are constants at its top.

| Per building | Meaning |
|---|---|
| `alert` | heat over the last 6 h is 60 % above expected (24 h: 40 %) and at least 10 % of the building's highest load; or the forecast for +1/6/24 h is 15 % above the highest load of the last 14 days |
| `watch` | the same at 25 % (6 h and 24 h) and 5 % of the highest load; or the forecast is 5 % above that highest load |
| `no_data` | no reading for this hour, or the meter shows the same value for 6 hours (reported as a data problem, never as overheating) |
| `ok` | none of the above |

Expected heat is what the forecast service predicted for each hour **24 hours earlier**. Where the service is down or has no value, the building's own recent days are used (median of the same hour on the same kind of day, adjusted for outdoor temperature); that is much noisier, so it needs a much bigger gap (watch 80 %, alert 150 % over 6 h). `basis` says which was used. Only data up to the clock is used. Buildings come back worst first, with `reasons` in plain words. Tests: `tests/test_status.py`.

### How the thresholds were chosen

Two checks on the frozen window (2022-10-01 to 2023-03-31, three buildings, real forecast model):

1. **Why 24 h earlier.** A 1 h-ahead forecast sees the last hour of heat and follows a surge: with a fake +60 % fault for 12 h it showed only +11 % over expected, against +55 % with the 24 h-earlier forecast. So the 1 h version was nearly blind to sustained over-use.
2. **False alarms and detection.** The status logic was run at every hour of the window (13,104 building-hours), and fake faults (+20 % to +100 % heat for 12 h, 60 random starts in building 8107) were injected to see what is caught. With the thresholds above: about 2 alert episodes and 10 watch episodes per building per month on real data (86 of 13,104 hours were `no_data`); an injected fault of +40 % is caught about 9 times in 10 at watch level, a doubling almost always, usually in the first hour.

Limits: there is no real fault data, only synthetic faults, so "false alarm" means "unusual compared with the forecast", which can be a real event (a holiday, a cold snap). A 25 % over-use in a quiet hour cannot be told from normal forecast error. Measured on the 6 h rule alone: raising the watch level from 25 % to 40 % cuts the episodes from 97 to 58 but catches only a third of +30 % faults (instead of three quarters). The thresholds are constants at the top of `dashboard/status.py`.


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
