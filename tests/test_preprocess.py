import numpy as np
import pandas as pd

from etl import preprocess_htot as p


def make_silver(start, n=48):
    idx = pd.date_range(start, periods=n, freq="h", tz=p.TZ)
    df = pd.DataFrame({
        "building_id": 1,
        p.TARGET: np.arange(1, n + 1, dtype=float) * 1000,
        "Tout": 5.0, "SolGlob": 0.0, "WindSpd": 2.0, "WindDir": 90.0,
    }, index=idx)
    return df


def test_zero_heat_dropped_in_winter_kept_in_summer():
    winter, summer = make_silver("2020-01-10"), make_silver("2020-07-10")
    winter.iloc[10, winter.columns.get_loc(p.TARGET)] = 0
    summer.iloc[10, summer.columns.get_loc(p.TARGET)] = 0
    assert len(p.to_gold(winter)) == len(winter) - 1
    assert len(p.to_gold(summer)) == len(summer)


def test_wind_direction_becomes_sin_cos():
    g = p.to_gold(make_silver("2020-01-10"))
    assert "WindDir" not in g.columns
    assert g["WindDir_sin"].iloc[0] == 1.0 or abs(g["WindDir_sin"].iloc[0] - 1.0) < 1e-12
    assert abs(g["WindDir_cos"].iloc[0]) < 1e-12


def test_wind_gap_across_north_is_not_averaged_through_south():
    s = make_silver("2020-01-10", 10)
    s.iloc[0, s.columns.get_loc("WindDir")] = 350.0
    s.iloc[2, s.columns.get_loc("WindDir")] = 10.0
    s.iloc[1, s.columns.get_loc("WindDir")] = np.nan
    g = p.to_gold(s)
    assert g["WindDir_cos"].iloc[1] > 0.95   # still pointing north, not 180 degrees (south)
