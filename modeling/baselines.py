"""Naive forecasts to beat. They use only the HtTot history of the window, in Wh (unscaled).

Window layout (see etl/windows.py): hist has LOOKBACK hours, the last one is the origin t.
The target hour is t + horizon. A seasonal naive forecast copies the value one season earlier,
at t + horizon - lag. For a valid window that hour is always inside hist, so it always exists.
"""
import numpy as np

LAGS = (24, 168)    # same hour yesterday, same hour last week


def persistence(hist_y: np.ndarray) -> np.ndarray:
    """Repeat the last known value. Only meaningful for the 1 hour horizon."""
    return hist_y[:, -1]


def seasonal_naive(hist_y: np.ndarray, horizon: int, lag: int) -> np.ndarray:
    """Value of the target hour one `lag` earlier. hist_y has shape (n, lookback)."""
    lookback = hist_y.shape[1]
    pos = lookback - 1 + horizon - lag          # position of hour t + horizon - lag in hist
    if lag < horizon or pos < 0:
        raise ValueError(f"lag {lag} cannot be used with horizon {horizon} and lookback {lookback}")
    return hist_y[:, pos]


def best_lag(hist_y: np.ndarray, y: np.ndarray, horizon: int, lags=LAGS) -> int:
    """Lag with the lowest WAPE on the given (training) windows."""
    errors = {lag: np.abs(seasonal_naive(hist_y, horizon, lag) - y).sum() for lag in lags if lag >= horizon}
    return min(errors, key=errors.get)
