"""A tiny model folder (a few trees, random GRU weights) and a fake feed, so the tests need no real models."""
import json
from datetime import datetime, timedelta

import httpx
import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
import torch

from etl import windows as w
from modeling import gru
from modeling.features import DEFAULT_TREND_GROUPS, flat_features
from modeling.predictor import make_frame, sha256_of

BUILDING = 8105
FIRST = datetime(2022, 10, 1)
HOURS = 24 * 20


def feed_rows(hours=HOURS, building=BUILDING):
    rows = []
    for k in range(hours):
        t = FIRST + timedelta(hours=k)
        rows.append({"timestamp": f"{t:%Y-%m-%dT%H:00:00}+01:00", "building_id": building, "phase": "replay",
                     "HtTot": 50000.0 + 20000.0 * (7 <= t.hour <= 16) + 100.0 * (k % 7),
                     "Tout": 2.0 + (k % 24) / 4, "SolGlob": max(0.0, 100.0 * (12 - abs(t.hour - 12))),
                     "WindSpd": 1.0 + (k % 5), "WindDir": float((k * 17) % 360)})
    return rows


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("models")
    frame = make_frame(feed_rows())
    manifest = {"version": "test", "train_end": "2022-10-20T00:00:00+01:00", "lookback": w.LOOKBACK,
                "features": {"daytypes": True, "trend_groups": list(DEFAULT_TREND_GROUPS)},
                "rule": "test", "horizons": {}, "units": "Wh per hour", "test_scores": None, "files": {}}
    torch.manual_seed(0)
    for h in w.HORIZONS:
        origins = w.valid_origins(frame.index, h)
        hist, future, y = w.build_arrays(frame, origins, h)
        X = flat_features(hist, future, h, origins + pd.Timedelta(hours=h), True)
        booster = lgb.train({"objective": "l1", "verbose": -1, "num_leaves": 4, "min_data_in_leaf": 5},
                            lgb.Dataset(X, y), num_boost_round=5)
        spec = {"target": "direct" if h == 1 else "residual", "lags": {} if h == 1 else {str(BUILDING): 24},
                "trees": f"lgb_h{h}.txt"}
        booster.save_model(str(out / spec["trees"]))
        if h > 1:
            torch.save(gru.Net(len(gru.COLS), len(gru.FUT_COLS)).state_dict(), out / f"gru_h{h}.pt")
            spec.update(gru=f"gru_h{h}.pt", gru_mean=[5e4, 2.0, 100.0, 2.0], gru_std=[2e4, 3.0, 200.0, 1.0])
        manifest["horizons"][str(h)] = spec
    manifest["files"] = {p.name: sha256_of(p) for p in out.iterdir()}
    (out / "manifest.json").write_text(json.dumps(manifest))
    return out


def make_fake_feed(rows, calls=None):
    last = rows[-1]["timestamp"]

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url)
        p = request.url.params
        if request.url.path == "/buildings":
            return httpx.Response(200, json={"buildings": [{"building_id": BUILDING}, {"building_id": 8107}],
                                             "window": {"first": rows[0]["timestamp"], "last": last}})
        if request.url.path == "/readings":      # like the real feed: nothing after `until`
            return httpx.Response(200, json=[r for r in rows if p["from"] <= r["timestamp"][:16] <= p["until"]])
        if request.url.path == "/weather-forecast":
            lo = pd.Timestamp(p["now"]); hi = lo + pd.Timedelta(hours=int(p["hours"]))
            out = [{k: v for k, v in r.items() if k not in ("HtTot", "phase")} for r in rows
                   if lo < pd.Timestamp(r["timestamp"][:19]) <= hi]
            return httpx.Response(200, json={"note": "perfect", "weather": out})
        return httpx.Response(404)
    return handler
