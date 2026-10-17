import numpy as np
import pandas as pd

from modeling import persistence_report as pr

TZ = "Etc/GMT-1"


def test_add_persistence_uses_the_origin_hour():
    idx = pd.date_range("2020-01-01", periods=10, freq="h", tz=TZ)
    gold = pd.concat([pd.DataFrame({"HtTot": np.arange(10) * 10.0, "building_id": b}, index=idx) for b in (1, 2)])
    gold.loc[gold["building_id"] == 2, "HtTot"] += 1000
    preds = pd.DataFrame({"time": [idx[5], idx[7], idx[7], idx[8]], "building_id": [1, 1, 2, 2],
                          "horizon": [1, 1, 1, 6], "y_true": 0.0, "y_pred": 0.0, "y_base": 0.0})
    p = pr.add_persistence(preds, gold)
    assert len(p) == 3                                        # horizon 6 row dropped
    assert list(p["y_persist"]) == [40.0, 60.0, 1060.0]       # value one hour before the target


def test_compare_perfect_persistence_has_skill_zero_against_itself():
    idx = pd.date_range("2020-01-01", periods=48, freq="h", tz=TZ)
    y = np.linspace(100, 200, 48)
    p = pd.DataFrame({"time": idx, "y_true": y, "y_pred": y, "y_base": y + 50, "y_persist": y + 10,
                      "scheme": "pooled", "target": "direct"})
    t = pr.compare(p).query("season == 'all'").iloc[0]
    assert t["wape"] == 0 and t["skill_vs_persist"] == 1 and t["skill_vs_seasonal"] == 1
    assert t["base_wape_persist"] < t["base_wape_seasonal"]
