import numpy as np
import pandas as pd

from modeling.daytypes import day_flags, daytype_features
from modeling.features import flat_features


def _days(*s):
    return pd.DatetimeIndex(pd.to_datetime(list(s)), tz="Etc/GMT-1")


def test_known_days():
    f = day_flags(_days("2018-02-21", "2018-03-29", "2018-12-24", "2018-05-17", "2018-06-12", "2018-10-03"))
    assert f["holiday"].tolist() == [0, 1, 1, 1, 0, 0]
    assert f["school_break"].tolist() == [1, 1, 1, 0, 0, 1]      # winter week 8, Easter, Christmas, autumn week 40
    assert f["off"].tolist() == [0, 1, 1, 1, 0, 0]


def test_weekend_is_off_but_not_holiday():
    f = day_flags(_days("2018-06-09"))                            # a Saturday
    assert f["holiday"][0] == 0 and f["off"][0] == 1


def test_prev_and_next_day_columns():
    f = daytype_features(_days("2018-05-16"))                     # the day before 17 May
    assert f["holiday_next"][0] == 1 and f["holiday"][0] == 0


def test_features_unchanged_without_time():
    hist = np.random.default_rng(0).random((4, 168, 9)).astype(np.float32)
    future = np.random.default_rng(1).random((4, 6, 8)).astype(np.float32)
    plain = flat_features(hist, future, 6)
    t = _days("2018-05-17", "2018-05-18", "2018-05-19", "2018-05-20")
    extra = flat_features(hist, future, 6, t)
    assert list(extra.columns[:len(plain.columns)]) == list(plain.columns)
    assert extra.shape[1] == plain.shape[1] + 9


def test_trend_features_on_a_ramp():
    n, h = 3, 6
    L = 168
    hist = np.zeros((n, L, 9), dtype=np.float32)
    hist[:, :, 0] = np.arange(L)                     # HtTot rises 1 per hour
    hist[:, :, 1] = 10.0                             # Tout constant
    future = np.zeros((n, h, 8), dtype=np.float32)
    future[:, :, 0] = 4.0                            # Tout will be 4
    X = flat_features(hist, future, h, trends=True)
    assert (X["y_diff1"] == 1).all() and (X["y_diff24"] == 24).all() and np.allclose(X["y_slope6"], 1)
    assert (X["Tout_fut_change"] == -6).all() and np.allclose(X["hdd_fut_mean"], 11) and np.allclose(X["hdd24"], 5)
    # target hour is L-1+6; same hour on earlier days sits at 24k back, so the typical level is the mean of those
    pos = [L - 1 + h - 24 * k for k in range(1, 8)]
    assert np.allclose(X["y_target_hod_mean"], np.mean(pos))
    assert np.allclose(X["y_dev_now"], (L - 1) - np.mean([L - 1 - 24 * k for k in range(7)]))


def test_trend_groups_can_be_left_out():
    from modeling.features import DEFAULT_TREND_GROUPS, TREND_GROUPS
    hist = np.random.default_rng(0).random((3, 168, 9)).astype(np.float32)
    future = np.random.default_rng(1).random((3, 6, 8)).astype(np.float32)
    full = flat_features(hist, future, 6, trends=True)
    assert set(full.columns) == set(flat_features(hist, future, 6, trends=DEFAULT_TREND_GROUPS).columns)
    assert set(flat_features(hist, future, 6, trends=TREND_GROUPS).columns) - set(full.columns) >= {"SolGlob_sum24"}
    less = flat_features(hist, future, 6, trends=tuple(g for g in DEFAULT_TREND_GROUPS if g != "accumulated_cold"))
    gone = set(full.columns) - set(less.columns)
    assert gone == {"Tout_mean72", "Tout_mean168", "hdd24", "hdd72", "hdd168", "hdd_fut_mean"}
