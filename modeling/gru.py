"""GRU sequence model on the 168 h window, scored on the same rolling-origin folds as the trees.

Same schemes (pooled, lobo), targets (direct, residual), seasonal-naive anchor and output table as
modeling/gbm.py, so metrics.score_table and persistence_report work unchanged.

Model: one GRU reads the last 168 hours (HtTot, weather, clock, day types), a second small GRU reads the
next `horizon` hours of weather and calendar (the measured "perfect forecast"), and a small network turns
both final states, plus the seasonal-naive value, into one number. Inputs are scaled with statistics of
the training period only. The number of epochs comes from the last STOP_DAYS of the training period
(early stopping); nothing at or after the validation start is used for any choice.
"""
from dataclasses import dataclass, field
import copy
import time as clock

import numpy as np
import pandas as pd
import torch
from torch import nn

from etl import windows as w
from modeling import baselines as bl
from modeling.daytypes import day_flags

HIDDEN = 64
BATCH = 512
LR = 2e-3
MAX_EPOCHS = 12
PATIENCE = 3
STOP_DAYS = 60
MIN_STOP_ROWS = 200
SEED = 0
SCHEMES = ("pooled", "lobo")
TARGETS = ("direct", "residual")

LEVELS = [w.TARGET, "Tout", "SolGlob", "WindSpd"]            # scaled with training statistics
OTHER = ["WindDir_sin", "WindDir_cos"]
CLOCK = ["hour_sin", "hour_cos", "wday_sin", "wday_cos", "month_sin", "month_cos"]
DAYTYPE = ["holiday", "school_break", "off"]
COLS = [*LEVELS, *OTHER, *CLOCK, *DAYTYPE]                   # one row per hour
FUT_COLS = [c for c in COLS if c != w.TARGET]                # the future has no HtTot
_LEVEL_IDX = [COLS.index(c) for c in LEVELS]


def hourly_matrix(b: pd.DataFrame) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """One building on a full hourly grid, shape (T, len(COLS)); hours missing from gold are NaN."""
    grid = pd.date_range(b.index.min(), b.index.max(), freq="h")
    full = b.reindex(grid)
    cyc = lambda x, period: (np.sin(2 * np.pi * x / period), np.cos(2 * np.pi * x / period))
    hs, hc = cyc(grid.hour.to_numpy(), 24)
    ws, wc = cyc(grid.weekday.to_numpy(), 7)
    ms, mc = cyc(grid.month.to_numpy() - 1, 12)
    flags = day_flags(grid)
    cols = {**{c: full[c].to_numpy() for c in [*LEVELS, *OTHER]},
            "hour_sin": hs, "hour_cos": hc, "wday_sin": ws, "wday_cos": wc, "month_sin": ms, "month_cos": mc,
            **{c: flags[c].to_numpy() for c in DAYTYPE}}
    return grid, np.stack([np.asarray(cols[c], dtype=np.float32) for c in COLS], axis=1)


@dataclass
class HorizonData:
    horizon: int
    mats: dict                      # building -> (T, F) raw hourly matrix
    grids: dict                     # building -> hourly DatetimeIndex
    building: np.ndarray
    pos: np.ndarray                 # origin position in the building's grid
    time: pd.DatetimeIndex          # target hour
    y: np.ndarray                   # target HtTot, Wh
    hist_y: np.ndarray              # (n, lookback) HtTot history, Wh, for the seasonal naive
    buildings: list = field(default_factory=list)


def load_horizon(gold: pd.DataFrame, horizon: int, test_start: pd.Timestamp) -> HorizonData:
    mats, grids, bld, pos, tim, ys, hist = {}, {}, [], [], [], [], []
    for bid, b in gold.groupby("building_id"):
        grid, mat = hourly_matrix(b)
        origins = w.targets_in(w.valid_origins(b.index, horizon), horizon, None, test_start)
        p = grid.get_indexer(origins)
        if ((p < w.LOOKBACK - 1) | (p + horizon >= len(grid))).any():
            raise ValueError("window reaches outside the building's time range")
        win = p[:, None] + np.arange(-w.LOOKBACK + 1, 1)
        y = mat[p + horizon, 0]
        if np.isnan(mat[win]).any() or np.isnan(mat[p[:, None] + np.arange(1, horizon + 1)][:, :, 1:]).any() or np.isnan(y).any():
            raise ValueError("window contains a missing hour; origins must come from valid_origins")
        mats[bid], grids[bid] = mat, grid
        bld.append(np.full(len(p), bid)); pos.append(p); ys.append(y); hist.append(mat[win, 0])
        tim.append(origins + pd.Timedelta(hours=horizon))
    return HorizonData(horizon, mats, grids, np.concatenate(bld), np.concatenate(pos),
                       tim[0].append(tim[1:]), np.concatenate(ys), np.concatenate(hist), list(mats))


def baseline_forecast(d: HorizonData, val_start: pd.Timestamp) -> np.ndarray:
    base = np.empty(len(d.y), dtype=np.float32)
    for bid in d.buildings:
        mine = d.building == bid
        lag = bl.best_lag(d.hist_y[mine & (d.time < val_start)], d.y[mine & (d.time < val_start)], d.horizon)
        base[mine] = bl.seasonal_naive(d.hist_y[mine], d.horizon, lag)
    return base


class Net(nn.Module):
    def __init__(self, n_hist: int, n_fut: int, hidden: int = HIDDEN):
        super().__init__()
        self.enc = nn.GRU(n_hist, hidden, batch_first=True)
        self.fut = nn.GRU(n_fut, hidden // 2, batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden + hidden // 2 + 1, hidden), nn.ReLU(), nn.Linear(hidden, 1))

    def forward(self, hist, fut, base):
        _, h = self.enc(hist)
        _, f = self.fut(fut)
        return self.head(torch.cat([h[-1], f[-1], base[:, None]], dim=1)).squeeze(1)


class Scaled:
    """The hourly matrices scaled with statistics of the training period, and a batch builder."""
    def __init__(self, d: HorizonData, train_end: pd.Timestamp):
        # mean/std of the levels over the training windows' hours: all gold hours before train_end
        cat = np.concatenate([m[g < train_end] for m, g in ((d.mats[b], d.grids[b]) for b in d.buildings)])
        self.mean = np.nanmean(cat[:, _LEVEL_IDX], axis=0)
        self.std = np.nanstd(cat[:, _LEVEL_IDX], axis=0) + 1e-6
        self.d = d
        self.scaled = {}
        for b in d.buildings:
            m = d.mats[b].copy()
            m[:, _LEVEL_IDX] = (m[:, _LEVEL_IDX] - self.mean) / self.std
            self.scaled[b] = np.nan_to_num(m)
        self.y_scale = float(self.std[0])

    def batch(self, rows: np.ndarray, base: np.ndarray):
        d, h = self.d, self.d.horizon
        hist = np.empty((len(rows), w.LOOKBACK, len(COLS)), np.float32)
        fut = np.empty((len(rows), h, len(FUT_COLS)), np.float32)
        fut_idx = [COLS.index(c) for c in FUT_COLS]
        for bid in d.buildings:
            sel = np.flatnonzero(d.building[rows] == bid)
            if len(sel):
                p = d.pos[rows[sel]]
                m = self.scaled[bid]
                hist[sel] = m[p[:, None] + np.arange(-w.LOOKBACK + 1, 1)]
                fut[sel] = m[p[:, None] + np.arange(1, h + 1)][:, :, fut_idx]
        b = (base[rows] - self.mean[0]) / self.std[0]
        return torch.from_numpy(hist), torch.from_numpy(fut), torch.from_numpy(b.astype(np.float32))


def _predict(net, sc, rows, base, anchor):
    net.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(rows), 2048):
            r = rows[i:i + 2048]
            out.append(net(*sc.batch(r, base)).numpy() * sc.y_scale + anchor[r])
    return np.concatenate(out)


def fit_net(sc: Scaled, train: np.ndarray, base: np.ndarray, anchor: np.ndarray, log=None,
            max_epochs: int = MAX_EPOCHS) -> nn.Module:
    """Train with the L1 loss; the last STOP_DAYS of the training period pick the best epoch."""
    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)
    d = sc.d
    stop = d.time[train] >= d.time[train].max() - pd.Timedelta(days=STOP_DAYS)
    fit_rows, stop_rows = train[~stop], train[stop]
    if len(stop_rows) < MIN_STOP_ROWS or len(fit_rows) < MIN_STOP_ROWS:
        fit_rows, stop_rows = train, train[-MIN_STOP_ROWS:]
    target = ((d.y - anchor) / sc.y_scale).astype(np.float32)
    net = Net(len(COLS), len(FUT_COLS))
    opt = torch.optim.AdamW(net.parameters(), lr=LR, weight_decay=1e-4)
    best, best_state, bad = np.inf, None, 0
    for epoch in range(max_epochs):
        net.train()
        order = rng.permutation(fit_rows)
        for i in range(0, len(order), BATCH):
            r = order[i:i + BATCH]
            loss = (net(*sc.batch(r, base)) - torch.from_numpy(target[r])).abs().mean()
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
        err = np.abs(_predict(net, sc, stop_rows, base, anchor) - d.y[stop_rows]).sum() / np.abs(d.y[stop_rows]).sum()
        if log:
            log(f"      epoch {epoch + 1} stop-WAPE {err:.4f}")
        if err < best - 1e-4:
            best, best_state, bad = err, copy.deepcopy(net.state_dict()), 0
        else:
            bad += 1
            if bad >= PATIENCE:
                break
    net.load_state_dict(best_state)
    return net


def run_fold(d: HorizonData, fold: w.Fold, scheme: str, target: str, held_out=None, log=None,
             max_epochs: int = MAX_EPOCHS) -> pd.DataFrame:
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
    sc = Scaled(d, fold.val_start)
    net = fit_net(sc, train, base, anchor, log, max_epochs)
    pred = np.maximum(_predict(net, sc, val, base, anchor), 0.0)
    return pd.DataFrame({
        "time": d.time[val], "y_true": d.y[val], "y_pred": pred, "y_base": base[val],
        "horizon": d.horizon, "fold": fold.name, "building_id": d.building[val],
        "scheme": scheme, "target": target,
    })


def run_all(gold: pd.DataFrame, horizons=w.HORIZONS, schemes=SCHEMES, targets=("residual",), folds=None,
            max_epochs: int = MAX_EPOCHS, log=print, on_result=None) -> pd.DataFrame:
    all_folds, t0 = w.make_folds(gold.index)
    folds = [f for f in all_folds if folds is None or f.name in folds]
    out = []
    for h in horizons:
        d = load_horizon(gold, h, t0)
        log(f"horizon {h}: {len(d.y)} windows")
        for fold in folds:
            for target in targets:
                for scheme in schemes:
                    for held_out in ([None] if scheme == "pooled" else d.buildings):
                        t = clock.time()
                        res = run_fold(d, fold, scheme, target, held_out, log, max_epochs)
                        if len(res):
                            out.append(res)
                            if on_result:
                                on_result(res)
                        log(f"  h{h} {fold.name} {scheme} {target} {held_out or ''} {clock.time() - t:.0f}s")
    return pd.concat(out, ignore_index=True)
