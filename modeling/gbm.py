"""Gradient-boosted trees (LightGBM) on the flat window features, scored on the rolling-origin folds.

Two training schemes
  pooled  one model per fold and horizon, trained on all buildings before the fold, scored on each building.
  lobo    leave-one-building-out: trained on the other buildings only, scored on the held-out building,
          which the model has never seen. Tells how well the model carries over to a new building.
Two targets
  direct    the model predicts HtTot.
  residual  the model predicts HtTot minus the seasonal naive forecast and the forecast is added back.

The seasonal-naive lag (24 or 168) is chosen per building and fold on that building's windows with
targets before the fold's validation start. It defines y_base and the residual anchor. Nothing at or
after the validation start, and nothing from the final test block, is used for any choice.
"""
from dataclasses import dataclass, field
import os

import lightgbm as lgb
import numpy as np
import pandas as pd

from etl import windows as w
from modeling import baselines as bl
from modeling.features import flat_features

PARAMS = dict(
    objective="l1",            # absolute error, the closest training loss to MAE and WAPE
    n_estimators=400, learning_rate=0.05, num_leaves=63, min_child_samples=100,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
    random_state=0, n_jobs=os.cpu_count(), verbose=-1,
)
SCHEMES = ("pooled", "lobo")
TARGETS = ("direct", "residual")

# Early stopping (used when tuning): the last STOP_DAYS of the training period, never the validation
# block, tell when to stop adding trees. The model is then refitted on all training windows with that
# many trees, so it also sees the most recent weeks.
STOP_DAYS = 60
MAX_TREES = 1500
PATIENCE = 50
MIN_STOP_ROWS = 200


@dataclass
class HorizonData:
    """All valid windows of all buildings for one horizon, with target hour before the test block."""
    horizon: int
    X: pd.DataFrame
    y: np.ndarray                  # target HtTot, Wh
    hist_y: np.ndarray             # HtTot history, Wh, shape (n, lookback)
    time: pd.DatetimeIndex         # target hour
    building: np.ndarray
    buildings: list = field(default_factory=list)


def load_horizon(gold: pd.DataFrame, horizon: int, test_start: pd.Timestamp) -> HorizonData:
    parts = []
    for bid, b in gold.groupby("building_id"):
        origins = w.targets_in(w.valid_origins(b.index, horizon), horizon, None, test_start)
        hist, future, y = w.build_arrays(b, origins, horizon)
        parts.append((bid, origins + pd.Timedelta(hours=horizon), flat_features(hist, future, horizon),
                      y, hist[:, :, w.HISTORY_FEATURES.index(w.TARGET)].copy()))
    return HorizonData(
        horizon=horizon,
        X=pd.concat([p[2] for p in parts], ignore_index=True),
        y=np.concatenate([p[3] for p in parts]),
        hist_y=np.concatenate([p[4] for p in parts]),
        time=parts[0][1].append([p[1] for p in parts[1:]]),
        building=np.concatenate([np.full(len(p[3]), p[0]) for p in parts]),
        buildings=[p[0] for p in parts],
    )


def baseline_forecast(d: HorizonData, val_start: pd.Timestamp) -> np.ndarray:
    """Seasonal naive forecast of every window, using the lag chosen per building before val_start."""
    base = np.empty(len(d.y), dtype=np.float32)
    for bid in d.buildings:
        mine = d.building == bid
        train = mine & (d.time < val_start)
        lag = bl.best_lag(d.hist_y[train], d.y[train], d.horizon)
        base[mine] = bl.seasonal_naive(d.hist_y[mine], d.horizon, lag)
    return base


def fit_model(X: pd.DataFrame, y: np.ndarray, time: pd.DatetimeIndex, params: dict, stop_days: int | None = None):
    """Fit one LightGBM model. With stop_days, the number of trees comes from early stopping on the
    last stop_days of `time` (the training period), followed by a refit on all rows."""
    if stop_days is not None:
        stop = np.asarray(time >= time.max() - pd.Timedelta(days=stop_days))
        if stop.sum() >= MIN_STOP_ROWS and (~stop).sum() >= MIN_STOP_ROWS:
            first = lgb.LGBMRegressor(**{**params, "n_estimators": MAX_TREES, "metric": "l1"})
            first.fit(X[~stop], y[~stop], eval_X=X[stop], eval_y=y[stop],
                      callbacks=[lgb.early_stopping(PATIENCE, verbose=False)])
            params = {**params, "n_estimators": max(int(first.best_iteration_), 1)}
    return lgb.LGBMRegressor(**params).fit(X, y)


def run_fold(d: HorizonData, fold: w.Fold, scheme: str, target: str, held_out=None, params=None,
             stop_days: int | None = None) -> pd.DataFrame:
    """Train on windows with target before the fold, predict the fold's validation windows."""
    base = baseline_forecast(d, fold.val_start)
    in_val = (d.time >= fold.val_start) & (d.time < fold.val_end)
    in_train = d.time < fold.val_start
    if scheme == "lobo":
        in_train &= d.building != held_out
        in_val &= d.building == held_out
    train, val = np.flatnonzero(in_train), np.flatnonzero(in_val)
    if len(train) == 0 or len(val) == 0:
        return pd.DataFrame()

    anchor = base if target == "residual" else np.zeros_like(base)
    model = fit_model(d.X.iloc[train], d.y[train] - anchor[train], d.time[train], params or PARAMS, stop_days)
    pred = np.maximum(model.predict(d.X.iloc[val]) + anchor[val], 0.0)     # heat use cannot be negative
    return pd.DataFrame({
        "time": d.time[val], "y_true": d.y[val], "y_pred": pred, "y_base": base[val],
        "horizon": d.horizon, "fold": fold.name, "building_id": d.building[val],
        "scheme": scheme, "target": target,
    })


def run_all(gold: pd.DataFrame, horizons=w.HORIZONS, schemes=SCHEMES, targets=TARGETS, params=None,
            stop_days: int | None = None, log=print) -> pd.DataFrame:
    folds, t0 = w.make_folds(gold.index)
    out = []
    for h in horizons:
        d = load_horizon(gold, h, t0)
        log(f"horizon {h}: {len(d.y)} windows")
        for fold in folds:
            for target in targets:
                for scheme in schemes:
                    runs = [None] if scheme == "pooled" else d.buildings
                    for held_out in runs:
                        res = run_fold(d, fold, scheme, target, held_out, params, stop_days)
                        if len(res):
                            out.append(res)
            log(f"  {fold.name} done")
    return pd.concat(out, ignore_index=True)
