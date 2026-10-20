"""Saved forecasting models and the code that uses them: shared by the export script and the forecast service.

A model folder (models/ai_v1/) holds manifest.json, LightGBM boosters (.txt) and GRU weights (.pt). The
manifest lists every file with its SHA-256; a folder with a missing or changed file is refused.

Forecast rule (decided on the validation folds, see notebooks/quality_inspect_decision.md):
  horizon 1      LightGBM, direct target
  horizon 6, 24  average of LightGBM and GRU, both on the residual target (HtTot minus seasonal naive)
Input: one building's hourly rows up to the origin (HtTot and weather, at least the last 168 hours) plus
weather rows for the next `horizon` hours (a "perfect forecast" in the replay). Output in Wh per hour.
"""
import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import torch

from etl import windows as w
from modeling import baselines as bl
from modeling import gru
from modeling.features import flat_features

TZ = "Etc/GMT-1"                        # the data's fixed UTC+1
WEATHER_IN = ["Tout", "SolGlob", "WindSpd", "WindDir"]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_frame(rows: list[dict]) -> pd.DataFrame:
    """Gold-like hourly frame for one building from feed rows (timestamp, HtTot?, Tout, SolGlob, WindSpd, WindDir).

    Rows without HtTot (the future weather) get NaN. Same column rules as etl/preprocess_htot.py:
    the wind angle becomes sine and cosine, the calendar columns are hour, weekday (Monday = 0), month."""
    df = pd.DataFrame(rows)
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(TZ)
    out = pd.DataFrame({"HtTot": df["HtTot"] if "HtTot" in df else np.nan,
                        **{c: df[c] for c in WEATHER_IN if c != "WindDir"}})
    angle = np.deg2rad(df["WindDir"])
    out["WindDir_sin"], out["WindDir_cos"] = np.sin(angle), np.cos(angle)
    out.index = pd.DatetimeIndex(ts, name="timestamp")
    out = out.sort_index()
    if out.index.has_duplicates:
        raise ValueError("duplicate timestamps")
    out["hour"], out["weekday"], out["month"] = out.index.hour, out.index.dayofweek, out.index.month
    return out


class Predictor:
    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.manifest = json.loads((self.folder / "manifest.json").read_text())
        for name, digest in self.manifest["files"].items():
            f = self.folder / name
            if not f.is_file() or sha256_of(f) != digest:
                raise ValueError(f"{f} is missing or does not match the manifest; refusing to load the models")
        self.version = self.manifest["version"]
        self.horizons = sorted(int(h) for h in self.manifest["horizons"])
        self.boosters, self.nets = {}, {}
        for h in self.horizons:
            spec = self.manifest["horizons"][str(h)]
            self.boosters[h] = lgb.Booster(model_file=str(self.folder / spec["trees"]))
            if "gru" in spec:
                net = gru.Net(len(gru.COLS), len(gru.FUT_COLS))
                net.load_state_dict(torch.load(self.folder / spec["gru"], weights_only=True))
                self.nets[h] = net.eval()
        self.trend_groups = tuple(self.manifest["features"]["trend_groups"])

    def _trees(self, h: int, frame: pd.DataFrame, building: int, origins, lag) -> tuple[np.ndarray, np.ndarray]:
        hist, future, _ = w.build_arrays(frame, origins, h, with_target=False)
        X = flat_features(hist, future, h, origins + pd.Timedelta(hours=h), self.trend_groups)
        X = X[self.boosters[h].feature_name()]                      # the column order of training
        hist_y = hist[:, :, w.HISTORY_FEATURES.index(w.TARGET)]
        anchor = bl.seasonal_naive(hist_y, h, lag) if lag else np.zeros(len(X), np.float32)
        return self.boosters[h].predict(X) + anchor, hist_y

    def _gru(self, h: int, frame: pd.DataFrame, building: int, origins, lag) -> np.ndarray:
        spec = self.manifest["horizons"][str(h)]
        d = gru.serve_data(frame, building, origins, h)
        sc = gru.Scaled(d, spec["gru_mean"], spec["gru_std"])
        base = bl.seasonal_naive(d.hist_y, h, lag).astype(np.float32)
        with torch.no_grad():
            return gru.predict(self.nets[h], sc, np.arange(len(origins)), base, base)

    def forecast(self, frame: pd.DataFrame, building: int, origins: pd.DatetimeIndex,
                 horizons=None) -> pd.DataFrame:
        """One row per origin and horizon: target_time and y_pred (Wh), plus the trees and GRU parts."""
        out = []
        for h in (horizons or self.horizons):
            spec = self.manifest["horizons"][str(h)]
            lag = spec["lags"].get(str(building)) if spec["target"] == "residual" else None
            if spec["target"] == "residual" and lag is None:
                raise KeyError(f"no seasonal-naive lag for building {building}: the models have not seen it")
            trees, _ = self._trees(h, frame, building, origins, lag)
            nn_pred = self._gru(h, frame, building, origins, lag) if h in self.nets else None
            pred = trees if nn_pred is None else (trees + nn_pred) / 2
            out.append(pd.DataFrame({"origin": origins, "horizon": h, "target_time": origins + pd.Timedelta(hours=h),
                                     "y_pred": np.maximum(pred, 0.0), "y_trees": np.maximum(trees, 0.0),
                                     "y_gru": np.nan if nn_pred is None else np.maximum(nn_pred, 0.0)}))
        return pd.concat(out, ignore_index=True)
