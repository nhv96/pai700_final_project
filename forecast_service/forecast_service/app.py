"""Forecast service: heat-use forecasts (HtTot, Wh per hour) from the saved AI models.

  GET /health
  GET /model                                                  version, rule, training end, test scores
  GET /forecast?now=&building=&horizons=1,6,24                the forecasts made at hour `now` (last known hour)
  GET /forecast/series?from=&until=&building=                 forecasts made at every origin in [from, until],
                                                              grouped by horizon, for a chart overlay

The service holds no data. It asks the replay feed (FEED_URL) for the hourly readings up to the origin
(`/readings`, never later than `until`) and for the weather of the next 24 hours (`/weather-forecast`, a perfect
forecast in the replay). Models are loaded once from MODEL_DIR (checked against the manifest checksums).
Everything is in the data's fixed UTC+1 time.

Run:  FEED_URL=http://localhost:8001 MODEL_DIR=../models/ai_v1 PYTHONPATH=.. uvicorn --factory forecast_service.app:create_app --port 8003
"""
from __future__ import annotations

import os
from collections import OrderedDict
from typing import Annotated

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from etl import windows as w
from modeling.predictor import TZ, Predictor, make_frame

MAX_SERIES_HOURS = 31 * 24
CACHE_SIZE = 32
NOTE = ("Forecast of the whole building's heat use. The next hours of weather are measured values replayed as a "
        "perfect forecast, so real forecast errors are not included: the accuracy is an upper bound.")


def parse_ts(name: str, value: str) -> pd.Timestamp:
    try:
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        raise HTTPException(422, f"{name}: not a valid ISO timestamp: {value!r}")
    ts = ts.tz_localize(TZ) if ts.tzinfo is None else ts.tz_convert(TZ)
    return ts.floor("h")


def create_app(feed_url: str | None = None, model_dir: str | None = None,
               transport: httpx.BaseTransport | None = None) -> FastAPI:
    feed_url = (feed_url or os.environ.get("FEED_URL", "http://localhost:8001")).rstrip("/")
    predictor = Predictor(model_dir or os.environ.get("MODEL_DIR", "models/ai_v1"))
    cache: OrderedDict = OrderedDict()
    app = FastAPI(title="PAI700 forecast service")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

    def feed_get(client: httpx.Client, path: str, **query):
        try:
            resp = client.get(path, params=query)
        except httpx.HTTPError:
            raise HTTPException(502, f"the replay feed at {feed_url} is not reachable")
        if resp.status_code != 200:
            raise HTTPException(502, f"the replay feed answered {resp.status_code} for {path}")
        return resp.json()

    def run(building: int | None, first: pd.Timestamp, last: pd.Timestamp, horizons: list[int]) -> dict:
        """Forecasts from every origin in [first, last]. Origins without enough history or future weather
        are left out of that horizon (the response says which range each horizon covers)."""
        with httpx.Client(base_url=feed_url, transport=transport, timeout=60.0) as client:
            info = feed_get(client, "/buildings")
            ids = [b["building_id"] for b in info["buildings"]]
            if building is None:
                building = ids[0]
            elif building not in ids:
                raise HTTPException(404, f"unknown building id: {building}")
            key = (building, first, last, tuple(horizons))
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
            lo = first - pd.Timedelta(hours=w.LOOKBACK - 1)
            fmt = lambda t: t.strftime("%Y-%m-%dT%H:%M")
            rows = feed_get(client, "/readings", **{"from": fmt(lo), "until": fmt(last), "building": building})
            ahead = feed_get(client, "/weather-forecast", now=fmt(last), hours=max(horizons), building=building)["weather"]
        frame = make_frame(rows + ahead)
        hours = pd.date_range(frame.index.min(), frame.index.max(), freq="h")
        if len(hours) != len(frame):
            raise HTTPException(422, "the feed returned a gap in the hourly rows")
        series, covered = {}, {}
        for h in horizons:
            # an origin needs 168 h of history before it and h hours of weather after it
            origins = pd.date_range(first, last, freq="h")
            origins = origins[(origins >= frame.index.min() + pd.Timedelta(hours=w.LOOKBACK - 1))
                              & (origins + pd.Timedelta(hours=h) <= frame.index.max())]
            origins = origins[frame.loc[origins, "HtTot"].notna()]
            if not len(origins):
                series[str(h)], covered[str(h)] = [], None
                continue
            f = predictor.forecast(frame, building, origins, [h])
            series[str(h)] = [{"origin": o.isoformat(), "target_time": t.isoformat(), "wh": round(float(v), 1),
                               "trees_wh": round(float(a), 1),
                               "gru_wh": None if pd.isna(g) else round(float(g), 1)}
                              for o, t, v, a, g in zip(f["origin"], f["target_time"], f["y_pred"], f["y_trees"], f["y_gru"])]
            covered[str(h)] = {"first_origin": origins[0].isoformat(), "last_origin": origins[-1].isoformat()}
        out = {"building": building, "model": predictor.version, "units": "Wh per hour", "note": NOTE,
               "covered": covered, "series": series}
        cache[key] = out
        if len(cache) > CACHE_SIZE:
            cache.popitem(last=False)
        return out

    def horizon_list(text: str | None) -> list[int]:
        try:
            hs = sorted({int(x) for x in text.split(",")}) if text else list(predictor.horizons)
        except ValueError:
            raise HTTPException(422, f"horizons: not a comma-separated list of integers: {text!r}")
        bad = [h for h in hs if h not in predictor.horizons]
        if bad:
            raise HTTPException(422, f"horizons {bad} are not available; the models cover {predictor.horizons}")
        return hs

    @app.get("/health")
    def health():
        return {"status": "ok", "model": predictor.version}

    @app.get("/model")
    def model():
        m = predictor.manifest
        return {"version": m["version"], "train_end": m["train_end"], "rule": m["rule"], "horizons": predictor.horizons,
                "lookback_hours": m["lookback"], "units": m["units"], "test_scores": m.get("test_scores"),
                "buildings": sorted({int(b) for s in m["horizons"].values() for b in s["lags"]}), "note": NOTE}

    @app.get("/forecast")
    def forecast(now: str, building: int | None = None, horizons: str | None = None):
        t = parse_ts("now", now)
        hs = horizon_list(horizons)
        res = run(building, t, t, hs)
        missing = [h for h in hs if not res["series"][str(h)]]
        if missing:
            raise HTTPException(422, f"no forecast at {t.isoformat()} for horizons {missing}: it needs {w.LOOKBACK} "
                                     f"hours of history and the weather of the next hours inside the data window")
        return {"building": res["building"], "model": res["model"], "units": res["units"], "note": res["note"],
                "origin": t.isoformat(),
                "forecasts": [{"horizon": h, **res["series"][str(h)][0]} for h in hs]}

    @app.get("/forecast/series")
    def series(from_: Annotated[str, Query(alias="from")], until: str, building: int | None = None,
               horizons: str | None = None):
        lo, hi = parse_ts("from", from_), parse_ts("until", until)
        if hi < lo:
            raise HTTPException(422, "until is before from")
        if (hi - lo) > pd.Timedelta(hours=MAX_SERIES_HOURS):
            raise HTTPException(422, f"at most {MAX_SERIES_HOURS} hours per request")
        return run(building, lo, hi, horizon_list(horizons))

    return app
