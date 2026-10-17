import numpy as np
import pandas as pd

from etl import windows as w
from modeling import gbm
from modeling.features import flat_features

TZ = "Etc/GMT-1"
SMALL = dict(gbm.PARAMS, n_estimators=5, num_leaves=4, min_child_samples=5, n_jobs=1)


def make_gold(n=24 * 60, buildings=(1, 2, 3), noise=0.0):
    """Perfectly daily-periodic heat use, so the lag-24 seasonal naive is exact."""
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz=TZ)
    frames = []
    for b in buildings:
        df = pd.DataFrame({
            w.TARGET: 1000.0 * b + 500.0 * np.sin(2 * np.pi * idx.hour / 24)
            + np.random.default_rng(b).normal(0, noise, n),
            "Tout": np.cos(np.arange(n) / 50.0), "SolGlob": 10.0 * idx.hour, "WindSpd": 3.0,
            "WindDir_sin": 0.0, "WindDir_cos": 1.0,
        }, index=idx)
        df["hour"], df["weekday"], df["month"] = idx.hour, idx.dayofweek, idx.month
        df["building_id"] = b
        frames.append(df)
    return pd.concat(frames)


def fold_for(gold, days=10):
    start = gold.index.min() + pd.Timedelta(days=40)
    return w.Fold("t", start, start + pd.Timedelta(days=days))


def test_flat_features_values():
    n, h = 4, 6
    hist = np.random.default_rng(0).random((n, w.LOOKBACK, len(w.HISTORY_FEATURES)), dtype=np.float32)
    future = np.random.default_rng(1).random((n, h, len(w.FUTURE_FEATURES)), dtype=np.float32)
    X = flat_features(hist, future, h)
    y = hist[:, :, w.HISTORY_FEATURES.index(w.TARGET)]
    assert len(X) == n and not X.isna().any().any()
    assert np.allclose(X["y_lag0"], y[:, -1])
    assert np.allclose(X["y_lag167"], y[:, 0])
    assert np.allclose(X["naive24"], y[:, w.LOOKBACK - 1 + h - 24])        # same hour yesterday
    assert np.allclose(X["naive168"], y[:, h - 1])                          # same hour last week
    assert np.allclose(X["Tout_target"], future[:, -1, w.FUTURE_FEATURES.index("Tout")])
    assert np.allclose(X["hour_target"], future[:, -1, w.FUTURE_FEATURES.index("hour")])


def test_load_horizon_excludes_test_block():
    gold = make_gold()
    cut = gold.index.min() + pd.Timedelta(days=50)
    d = gbm.load_horizon(gold, 6, cut)
    assert (d.time < cut).all()
    assert len(d.y) == len(d.X) == len(d.hist_y) == len(d.building)


def test_residual_model_reproduces_exact_baseline():
    gold = make_gold()
    d = gbm.load_horizon(gold, 6, gold.index.max())
    res = gbm.run_fold(d, fold_for(gold), "pooled", "residual", params=SMALL)
    assert np.allclose(res["y_pred"], res["y_true"], atol=1e-2)             # residual is zero everywhere
    assert np.allclose(res["y_base"], res["y_true"], atol=1e-2)


def test_predictions_stay_inside_validation_block():
    gold = make_gold()
    f = fold_for(gold)
    d = gbm.load_horizon(gold, 24, gold.index.max())
    res = gbm.run_fold(d, f, "pooled", "direct", params=SMALL)
    assert (res["time"] >= f.val_start).all() and (res["time"] < f.val_end).all()
    assert set(res["building_id"]) == {1, 2, 3}
    assert (res["y_pred"] >= 0).all()


def test_lobo_scores_only_held_out_building_and_never_trains_on_it(monkeypatch):
    gold = make_gold()
    d = gbm.load_horizon(gold, 6, gold.index.max())
    seen = []
    real_fit = gbm.lgb.LGBMRegressor.fit

    def spy(self, X, y, *a, **k):
        seen.append(len(X))
        return real_fit(self, X, y, *a, **k)

    monkeypatch.setattr(gbm.lgb.LGBMRegressor, "fit", spy)
    f = fold_for(gold)
    res = gbm.run_fold(d, f, "lobo", "direct", held_out=2, params=SMALL)
    assert set(res["building_id"]) == {2}
    n_train_expected = int(((d.time < f.val_start) & (d.building != 2)).sum())
    assert seen == [n_train_expected]
