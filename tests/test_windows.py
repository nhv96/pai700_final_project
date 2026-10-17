import numpy as np
import pandas as pd
import pytest

from etl import windows as w

TZ = "Etc/GMT-1"


def make_df(n=1000, gap=None, start="2020-01-01"):
    idx = pd.date_range(start, periods=n, freq="h", tz=TZ)
    df = pd.DataFrame({c: np.arange(n, dtype=float) for c in [w.TARGET, *w.WEATHER]}, index=idx)
    df["hour"], df["weekday"], df["month"] = idx.hour, idx.dayofweek, idx.month
    if gap is not None:
        df = df.drop(df.index[gap[0]:gap[1]])
    return df


def test_valid_origins_complete_series():
    df = make_df(500)
    o = w.valid_origins(df.index, horizon=6)
    assert o[0] == df.index[w.LOOKBACK - 1]          # first origin has a full history
    assert o[-1] == df.index[-1] - pd.Timedelta(hours=6)  # last origin has its target


def test_valid_origins_skip_windows_crossing_a_gap():
    df = make_df(1000, gap=(400, 410))                # hours 400..409 missing
    h = 6
    o = w.valid_origins(df.index, h)
    gap_hours = pd.date_range(df.index[399], periods=12, freq="h") + pd.Timedelta(hours=1)
    missing = set(pd.date_range("2020-01-01", periods=1000, freq="h", tz=TZ)[400:410])
    for t in o:
        window = pd.date_range(t - pd.Timedelta(hours=w.LOOKBACK - 1), t + pd.Timedelta(hours=h), freq="h")
        assert not (set(window) & missing)
    # origins right after the gap only come back once the full history is past it
    assert df.index[409 + 1] not in o


def test_build_arrays_alignment():
    df = make_df(400)
    o = w.valid_origins(df.index, 6)[:3]
    hist, fut, y = w.build_arrays(df, o, 6)
    t = df.index.get_loc(o[0])
    assert hist.shape == (3, w.LOOKBACK, len(w.HISTORY_FEATURES))
    assert fut.shape == (3, 6, len(w.FUTURE_FEATURES))
    assert hist[0, -1, 0] == t                        # last history hour is the origin
    assert fut[0, 0, 0] == t + 1 and fut[0, -1, 0] == t + 6   # Tout column is 0 of future features
    assert y[0] == t + 6


def test_build_arrays_rejects_invalid_origin():
    df = make_df(400)
    with pytest.raises(ValueError):
        w.build_arrays(df, df.index[:1], 6)


def test_folds_are_consecutive_and_end_at_test_start():
    idx = pd.date_range("2012-10-01", "2023-10-22 23:00", freq="h", tz=TZ)
    folds, t0 = w.make_folds(idx)
    assert len(folds) == w.N_FOLDS
    assert folds[-1].val_end == t0
    for a, b in zip(folds, folds[1:]):
        assert a.val_end == b.val_start
    assert folds[0].val_start > idx.min() + pd.DateOffset(years=3)   # enough history for the first fold
    share = (idx.max() - t0) / (idx.max() - idx.min())
    assert 0.13 < share < 0.17


def test_targets_in_splits_by_target_hour_without_overlap():
    df = make_df(2000)
    h = 24
    o = w.valid_origins(df.index, h)
    cut = df.index[1200]
    train = w.targets_in(o, h, None, cut)
    val = w.targets_in(o, h, cut, df.index[1500])
    assert (train + pd.Timedelta(hours=h)).max() < cut
    assert (val + pd.Timedelta(hours=h)).min() >= cut
    assert len(train.intersection(val)) == 0


def test_scaler_uses_only_training_rows():
    df = make_df(500)
    cut = df.index[300]
    stats = w.fit_scaler(df, cut)
    expected = df.loc[df.index < cut, w.TARGET]
    assert stats.loc["mean", w.TARGET] == pytest.approx(expected.mean())
    scaled = w.apply_scaler(df, stats)
    assert scaled.loc[df.index < cut, w.TARGET].mean() == pytest.approx(0, abs=1e-9)
    assert (scaled[w.CALENDAR] == df[w.CALENDAR]).all().all()
