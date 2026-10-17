"""Flat feature table for tree models, built from the windows of etl/windows.py.

One row per window (origin t, target t + horizon). Tree models do not need scaling, so the raw
values (HtTot in Wh) are used. Only information known at the origin is used, except the measured
weather of the next hours, which stands in for a perfect forecast (see etl/windows.py).
"""
import numpy as np
import pandas as pd

from etl import windows as w
from modeling import baselines as bl

RECENT_HOURS = 24                  # every one of the last 24 hours of HtTot is a feature
EXTRA_LAGS = (48, 72, 96, 120, 144, 167)    # hours back from the origin, for the days before
MEAN_SPANS = (6, 24, 168)          # rolling mean of HtTot over the last n hours

_H = {name: i for i, name in enumerate(w.HISTORY_FEATURES)}
_F = {name: i for i, name in enumerate(w.FUTURE_FEATURES)}


def flat_features(hist: np.ndarray, future: np.ndarray, horizon: int) -> pd.DataFrame:
    """hist (n, lookback, F_hist) and future (n, horizon, F_future) as one table of float32 columns."""
    lookback = hist.shape[1]
    y = hist[:, :, _H[w.TARGET]]
    cols = {}
    for k in range(RECENT_HOURS):
        cols[f"y_lag{k}"] = y[:, lookback - 1 - k]           # lag0 = the origin hour itself
    for k in EXTRA_LAGS:
        cols[f"y_lag{k}"] = y[:, lookback - 1 - k]
    for span in MEAN_SPANS:
        cols[f"y_mean{span}"] = y[:, -span:].mean(axis=1)
    cols["y_std24"] = y[:, -24:].std(axis=1)
    for lag in bl.LAGS:                                       # the seasonal naive values themselves
        cols[f"naive{lag}"] = bl.seasonal_naive(y, horizon, lag) if lag >= horizon else np.full(len(y), np.nan)

    for name in ("Tout", "SolGlob", "WindSpd"):               # weather at the origin and over the last day
        cols[f"{name}_now"] = hist[:, -1, _H[name]]
        cols[f"{name}_mean24"] = hist[:, -24:, _H[name]].mean(axis=1)

    for name in w.WEATHER:                                    # measured weather at the target hour
        cols[f"{name}_target"] = future[:, -1, _F[name]]
    for name in ("Tout", "SolGlob"):                          # and averaged over the whole horizon
        cols[f"{name}_fut_mean"] = future[:, :, _F[name]].mean(axis=1)

    for name in w.CALENDAR:                                   # calendar of the target hour
        cols[f"{name}_target"] = future[:, -1, _F[name]]
    return pd.DataFrame(cols).astype(np.float32)
