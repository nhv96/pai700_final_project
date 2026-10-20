"""Time splits, windows and scaling for forecasting HtTot from the gold layer.

Decisions are tracked in notebooks/quality_inspect_decision.md. Terms:
  origin  the last hour whose values are known when the forecast is made (t)
  target  the hour being predicted (t + horizon)

A window is valid only if every hour from t - LOOKBACK + 1 to t + horizon exists in gold,
so past values, the measured future weather and the target are all present.
A window belongs to the split that contains its target hour; nothing after the target is used.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

LOOKBACK = 168                  # hours of history per window (one week)
HORIZONS = (1, 6, 24)           # hours ahead
N_FOLDS = 10                    # rolling-origin folds
FOLD_MONTHS = 6                 # length of each validation block
TEST_FRAC = 0.15                # last share of the time span, kept untouched

TARGET = "HtTot"
WEATHER = ["Tout", "SolGlob", "WindSpd", "WindDir_sin", "WindDir_cos"]
CALENDAR = ["hour", "weekday", "month"]
HISTORY_FEATURES = [TARGET, *WEATHER, *CALENDAR]   # known for the past hours
FUTURE_FEATURES = [*WEATHER, *CALENDAR]            # measured weather + calendar of the next hours
SCALED = [TARGET, "Tout", "SolGlob", "WindSpd"]    # wind sin/cos are already in [-1, 1], calendar integers stay as they are


@dataclass(frozen=True)
class Fold:
    """Train on targets before val_start, validate on targets in [val_start, val_end)."""
    name: str
    val_start: pd.Timestamp
    val_end: pd.Timestamp


def test_start(index: pd.DatetimeIndex) -> pd.Timestamp:
    """First day of the month nearest to the point where the last TEST_FRAC of the time span begins."""
    cut = index.min() + (index.max() - index.min()) * (1 - TEST_FRAC)
    month = cut.floor("D").replace(day=1)
    if cut.day > 15:
        month += pd.DateOffset(months=1)
    return month


def make_folds(index: pd.DatetimeIndex) -> tuple[list[Fold], pd.Timestamp]:
    """N_FOLDS expanding-window folds of FOLD_MONTHS each, ending where the test block starts.

    The same calendar dates are used for every building.
    """
    t0 = test_start(index)
    step = pd.DateOffset(months=FOLD_MONTHS)
    folds = []
    for k in range(N_FOLDS):
        start = t0 - step * (N_FOLDS - k)
        folds.append(Fold(f"fold{k + 1:02d}", start, start + step))
    return folds, t0


def valid_origins(index: pd.DatetimeIndex, horizon: int, lookback: int = LOOKBACK) -> pd.DatetimeIndex:
    """Origins t of one building for which every hour t-lookback+1 .. t+horizon is present in index."""
    grid = pd.date_range(index.min(), index.max(), freq="h")
    span = lookback + horizon
    present = pd.Series(grid.isin(index), index=grid).astype(int)
    complete = present.rolling(span).min().eq(1)   # True at the last hour of a complete window
    return complete.index[complete] - pd.Timedelta(hours=horizon)


def targets_in(origins: pd.DatetimeIndex, horizon: int, start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    """Origins whose target hour lies in [start, end). Use start=None for 'everything before end'."""
    target = origins + pd.Timedelta(hours=horizon)
    keep = target < end
    if start is not None:
        keep &= target >= start
    return origins[keep]


def fit_scaler(frames: pd.DataFrame, before: pd.Timestamp) -> pd.DataFrame:
    """Mean and std of SCALED columns over rows strictly before `before` (training period only)."""
    return frames.loc[frames.index < before, SCALED].agg(["mean", "std"])


def apply_scaler(df: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out[SCALED] = (out[SCALED] - stats.loc["mean"]) / stats.loc["std"]
    return out


def build_arrays(df: pd.DataFrame, origins: pd.DatetimeIndex, horizon: int, lookback: int = LOOKBACK,
                 with_target: bool = True):
    """Arrays for one building. Returns hist (n, lookback, F_hist), future (n, horizon, F_future), y (n,).

    with_target=False is for serving: the target hour has no HtTot yet (the rows after the origin only
    carry weather and calendar), so y is returned as NaN and not checked."""
    grid = pd.date_range(df.index.min(), df.index.max(), freq="h")
    full = df.reindex(grid)
    hist_all = full[HISTORY_FEATURES].to_numpy(dtype=np.float32)
    fut_all = full[FUTURE_FEATURES].to_numpy(dtype=np.float32)
    y_all = full[TARGET].to_numpy(dtype=np.float32)

    pos = grid.get_indexer(origins)
    # negative indices would silently wrap around in numpy, so check the bounds explicitly
    if ((pos < lookback - 1) | (pos + horizon >= len(grid))).any():
        raise ValueError("window reaches outside the building's time range")
    hist = hist_all[pos[:, None] + np.arange(-lookback + 1, 1)]
    future = fut_all[pos[:, None] + np.arange(1, horizon + 1)]
    y = y_all[pos + horizon]
    if np.isnan(hist).any() or np.isnan(future).any() or (with_target and np.isnan(y).any()):
        raise ValueError("window contains a missing hour; origins must come from valid_origins")
    return hist, future, y
