# twin_service: the digital twin as an HTTP service

Runs the twin (`../twin/`) on weather from the replay feed (`../feed/`) and returns the legacy controller against the combined controller (forecast heating plus supply-temperature control, see `../docs/controllers-and-scenario.md`). The dashboard forwards to it at `/api/twin/compare`.

It holds no data and never reads heat values: it fetches hourly `Tout` and `SolGlob` from the feed and builds a `FeedWeather` (`../twin/feed_weather.py`: linear interpolation, sun on a horizontal surface times one assumed ratio for the south facade).

Everything it returns is **simulated** with assumed room parameters. The combined controller uses a perfect forecast and a perfect room model (best case). The response carries this as `note`.

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /compare?start=2022-11-07&days=5&building=8105` | summary and 10-minute series for `legacy` and `combined`, the weather used, `room_floor_area_m2`, setpoint and purge limit, a `note`. `start` is a date (midnight), `days` 1 to 14, `building` defaults to the first. The run must lie inside the data window. |

The room starts at 17 °C (school at setback), as in `scenarios/overshoot.py`. Results are cached per (start, days, building). A first 5-day run takes about 2 seconds.

## Run

The service imports `twin/` and `config/` from the repository root.

```bash
# the feed must be running (see ../feed/README.md)
cd twin_service
uv sync
FEED_URL=http://localhost:8001 PYTHONPATH=.. uv run uvicorn --factory twin_service.app:create_app --port 8002
```

Docker (the build context is the repository root):

```bash
docker build -f twin_service/Dockerfile -t pai700-twin-service .
```

or `docker compose up --build` from the root, which starts the feed, the twin service and the dashboard together.

## Tests

```bash
cd twin_service && uv run pytest
```
