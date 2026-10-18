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
