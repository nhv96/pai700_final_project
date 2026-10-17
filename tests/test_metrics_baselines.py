import numpy as np
import pandas as pd
import pytest

from modeling import baselines as b
from modeling import metrics as m


def test_seasonal_naive_picks_the_hour_one_lag_before_the_target():
    L = 168
    hist = np.arange(L, dtype=float)[None, :]          # value == position, origin t is position 167
    for h in (1, 6, 24):
        assert b.seasonal_naive(hist, h, 24)[0] == L - 1 + h - 24
        assert b.seasonal_naive(hist, h, 168)[0] == h - 1


def test_seasonal_naive_rejects_lag_shorter_than_horizon():
    with pytest.raises(ValueError):
        b.seasonal_naive(np.zeros((1, 168)), horizon=24, lag=6)


def test_persistence_is_last_value():
    hist = np.arange(168, dtype=float)[None, :]
    assert b.persistence(hist)[0] == 167


def test_best_lag_chooses_weekly_pattern():
    rng = np.random.default_rng(0)
    week = rng.uniform(1, 100, 168)
    hist = np.tile(week, (50, 1))
    h = 6
    y = np.full(50, week[h - 1])                       # target repeats the value 168 h earlier
    assert b.best_lag(hist, y, h) == 168


def test_metrics_known_values():
    y, p = np.array([1000., 2000., 3000.]), np.array([1500., 2000., 2000.])
    assert m.mae_kwh(y, p) == pytest.approx(0.5)       # (0.5 + 0 + 1) / 3
    assert m.rmse_kwh(y, p) == pytest.approx(np.sqrt((0.25 + 0 + 1) / 3))
    assert m.wape(y, p) == pytest.approx(1.5 / 6)
    assert np.isnan(m.wape(np.zeros(3), p))
    assert m.skill(0.1, 0.2) == pytest.approx(0.5)


def test_score_table_summer_has_no_wape():
    t = pd.to_datetime(["2020-01-15", "2020-01-16", "2020-07-15", "2020-07-16"]).tz_localize("Etc/GMT-1")
    df = pd.DataFrame({"time": t, "y_true": [1000., 1000., 100., 100.],
                       "y_pred": [900., 1100., 50., 150.], "y_base": [800., 1200., 0., 200.],
                       "horizon": 1})
    out = m.score_table(df, by=["horizon"]).set_index("season")
    assert out.loc["summer", "n"] == 2 and np.isnan(out.loc["summer", "wape"])
    assert out.loc["summer", "mae_kwh"] == pytest.approx(0.05)
    assert out.loc["winter", "wape"] == pytest.approx(0.1)
    assert out.loc["winter", "skill"] == pytest.approx(0.5)     # baseline wape 0.2
    assert out.loc["all", "n"] == 4
