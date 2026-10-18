"""Flat feature table for tree models, built from the windows of etl/windows.py.

One row per window (origin t, target t + horizon). Tree models do not need scaling, so the raw
values (HtTot in Wh) are used. Only information known at the origin is used, except the measured
weather of the next hours, which stands in for a perfect forecast (see etl/windows.py).
"""
import numpy as np
import pandas as pd

from etl import windows as w
from modeling import baselines as bl
from modeling.daytypes import daytype_features

RECENT_HOURS = 24                  # every one of the last 24 hours of HtTot is a feature
EXTRA_LAGS = (48, 72, 96, 120, 144, 167)    # hours back from the origin, for the days before
MEAN_SPANS = (6, 24, 168)          # rolling mean of HtTot over the last n hours

_H = {name: i for i, name in enumerate(w.HISTORY_FEATURES)}
_F = {name: i for i, name in enumerate(w.FUTURE_FEATURES)}


HEATING_BASE = 15.0                # degrees C: below this a building needs heat (degree-hours)
SLOPE_HOURS = 6                    # hours used for the least-squares slope of HtTot
DAYS_BACK = 7                      # days used for the "same hour of day" averages


def trend_features(hist: np.ndarray, future: np.ndarray, horizon: int) -> dict:
    """How HtTot and the weather are changing, as ready-made columns (trees cannot subtract columns)."""
    L = hist.shape[1]
    y = hist[:, :, _H[w.TARGET]]
    cols = {}
    for k in (1, 3, 6, 24):                                   # change of HtTot since k hours ago
        cols[f"y_diff{k}"] = y[:, -1] - y[:, -1 - k]
    x = np.arange(SLOPE_HOURS) - (SLOPE_HOURS - 1) / 2
    cols[f"y_slope{SLOPE_HOURS}"] = (y[:, -SLOPE_HOURS:] * x).sum(axis=1) / (x ** 2).sum()

    # Typical level at the target hour of day, and how far the origin hour is from its own typical level
    target_pos = [L - 1 + horizon - 24 * k for k in range(1, DAYS_BACK + 1) if 0 <= L - 1 + horizon - 24 * k <= L - 1]
    origin_pos = [L - 1 - 24 * k for k in range(0, DAYS_BACK)]
    typical_target = y[:, target_pos].mean(axis=1)
    deviation_now = y[:, -1] - y[:, origin_pos].mean(axis=1)
    cols["y_target_hod_mean"] = typical_target
    cols["y_dev_now"] = deviation_now
    cols["y_target_hod_adj"] = typical_target + deviation_now

    tout, sol, wind = (hist[:, :, _H[n]] for n in ("Tout", "SolGlob", "WindSpd"))
    f_tout, f_sol = future[:, :, _F["Tout"]], future[:, :, _F["SolGlob"]]
    for k in (3, 6, 24):
        cols[f"Tout_d{k}"] = tout[:, -1] - tout[:, -1 - k]
    cols["Tout_fut_change"] = f_tout[:, -1] - tout[:, -1]     # change from the origin to the target hour
    cols["Tout_fut_min"] = f_tout.min(axis=1)
    for span in (72, 168):
        cols[f"Tout_mean{span}"] = tout[:, -span:].mean(axis=1)
    for span in (24, 72, 168):                                # accumulated cold (degree-hours per hour)
        cols[f"hdd{span}"] = np.maximum(HEATING_BASE - tout[:, -span:], 0).mean(axis=1)
    cols["hdd_fut_mean"] = np.maximum(HEATING_BASE - f_tout, 0).mean(axis=1)
    cols["SolGlob_sum24"] = sol[:, -24:].sum(axis=1)
    cols["SolGlob_d3"] = sol[:, -1] - sol[:, -4]
    cols["SolGlob_fut_change"] = f_sol[:, -1] - sol[:, -1]
    cols["WindSpd_d3"] = wind[:, -1] - wind[:, -4]
    return cols


def flat_features(hist: np.ndarray, future: np.ndarray, horizon: int,
                  target_time: pd.DatetimeIndex | None = None, trends: bool = False) -> pd.DataFrame:
    """hist (n, lookback, F_hist) and future (n, horizon, F_future) as one table of float32 columns.

    With target_time (the target hour of each window), holiday and school-break flags are added.
    With trends=True, change and accumulation features (trend_features) are added.
    """
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
    if trends:
        cols.update(trend_features(hist, future, horizon))
    out = pd.DataFrame(cols).astype(np.float32)
    if target_time is not None:
        out = pd.concat([out, daytype_features(target_time)], axis=1)
    return out
