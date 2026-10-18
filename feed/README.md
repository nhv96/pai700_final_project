# feed: frozen data window and replay service

The one data source shared by the digital twin, the AI model and the dashboard. It has two parts.

1. **Freeze** cuts a fixed time window out of the silver layer and writes one parquet file plus a SHA-256 checksum into `../frozen/`.
2. **Replay** is an HTTP service that plays the frozen file like IoT sensors: one reading per building per simulated hour.

Window: 2022-09-24 to 2023-03-31 (hourly, fixed UTC+1). The first 168 hours are the `warmup` phase (history for models), the rest, from 2022-10-01, is the `replay` phase. Buildings: Oslo 8105, 8107, 8116. This feed does not import from `etl/`; it reads the silver parquet files only.

## Freeze

```bash
cd feed
uv sync
uv run python -m feed.freeze                 # ../data/silver -> ../frozen/oslo_window_v1.parquet (+ .sha256)
uv run python -m feed.freeze verify          # check the file against its checksum
```

The frozen file is immutable: freezing again with different content fails unless `--force` is given. The window must be complete (no gaps, no empty values) or the freeze fails.

## Replay service

```bash
cd feed
FEED_DATA=../frozen/oslo_window_v1.parquet uv run uvicorn --factory feed.api:create_app --port 8001
```

Docker (build context is `feed/`, the frozen file is mounted read-only):

```bash
docker build -t pai700-feed feed
docker run --rm -p 8001:8001 -v "$PWD/frozen:/data:ro" pai700-feed
```

The service refuses to start if the file does not match its `.sha256`. Interactive docs: http://localhost:8001/docs

### Clocks and the "no future heat" rule

The server has no "now". Every client has its own clock and says where it is: `until` for `/readings`, `now` for `/weather-forecast`, the stream position for `/stream`. Heat values after that moment are never returned.

### Endpoints

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /buildings` | building info (floor area, year of construction), window bounds, checksum, units |
| `GET /readings?until=&from=&building=` | heat + weather for `from <= t <= until`. `until` is required. `from` defaults to the window start. `building` can repeat; default is all. |
| `GET /weather-forecast?now=&hours=&building=` | measured weather (no heat) for the next `hours` hours (1 to 168, default 24). This is a **perfect forecast**, not a real one. |
| `GET /stream?speed=&from=&building=` | server-sent events, one `reading` event per simulated hour, then an `end` event |

Timestamps are ISO 8601. One without an offset is read as the data's own time (UTC+1, no DST).

Reading fields: `timestamp`, `building_id`, `phase`, `HtTot` (Wh per hour), `Tout` (C), `SolGlob` (W/m2), `WindSpd` (m/s), `WindDir` (degrees).

### Stream

`speed` is simulated hours per real second (default 1). The window is 4,536 hours, so `speed=10` replays everything in about 7.5 minutes. The stream starts at the warm-up by default; pass `from=2022-10-01T00:00` to skip it. Each event:

```
id: 2022-10-01T00:00:00+01:00
event: reading
data: {"timestamp": "...", "readings": [ {...building 8105...}, {...8107...}, {...8116...} ]}
```

To pause or change speed, close the stream and open a new one with `from`. A reconnect with `Last-Event-ID` (browsers send it automatically) continues after the last hour received.

## Tests

```bash
cd feed && uv run pytest
```
