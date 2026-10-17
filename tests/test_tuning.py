import json

import numpy as np
import pandas as pd

from modeling import gbm, tuning
from tests.test_gbm import SMALL, fold_for, make_gold


def test_sample_params_deterministic_and_in_range():
    assert tuning.sample_params(0, 5) == tuning.sample_params(0, 5)
    assert tuning.sample_params(0, 5) != tuning.sample_params(0, 6)
    assert tuning.sample_params(0, 5) != tuning.sample_params(1, 5)
    for trial in range(1, 200):
        p = tuning.sample_params(0, trial)
        assert p["objective"] in ("l1", "huber", "l2")
        assert 15 <= p["num_leaves"] <= 127 and 20 <= p["min_child_samples"] <= 400
        assert 0.5 <= p["subsample"] <= 1 and 0.4 <= p["colsample_bytree"] <= 1
        assert 0.01 <= p["reg_lambda"] <= 30
        assert ("alpha" in p) == (p["objective"] == "huber")


def test_trial_zero_is_the_default_setting():
    p = tuning.sample_params(0, 0)
    assert all(gbm.PARAMS[k] == v for k, v in p.items())


def test_early_stopping_uses_fewer_trees_than_the_maximum():
    gold = make_gold(noise=300.0)       # noise-free data never stops improving
    f = fold_for(gold)
    d = gbm.load_horizon(gold, 6, gold.index.max())
    train = np.flatnonzero(d.time < f.val_start)
    model = gbm.fit_model(d.X.iloc[train], d.y[train], d.time[train], dict(SMALL, n_estimators=50), stop_days=5)
    assert 1 <= model.n_estimators_ < gbm.MAX_TREES
    assert model.n_estimators_ == model.booster_.num_trees()


def test_run_fold_with_early_stopping_fits_twice(monkeypatch):
    gold = make_gold()
    d = gbm.load_horizon(gold, 6, gold.index.max())
    calls = []
    real = gbm.lgb.LGBMRegressor.fit
    monkeypatch.setattr(gbm.lgb.LGBMRegressor, "fit", lambda self, X, y, *a, **k: (calls.append(len(X)), real(self, X, y, *a, **k))[1])
    f = fold_for(gold)
    res = gbm.run_fold(d, f, "pooled", "residual", params=SMALL, stop_days=5)
    n_train = int((d.time < f.val_start).sum())
    assert calls[-1] == n_train and calls[0] < n_train          # stop fit on the earlier part, refit on all
    assert (res["time"] >= f.val_start).all() and (res["time"] < f.val_end).all()


def test_evaluate_trial_scores_every_scheme_and_horizon():
    gold = make_gold()
    f = fold_for(gold)
    datas = {h: gbm.load_horizon(gold, h, gold.index.max()) for h in (6, 24)}
    res = tuning.evaluate_trial(datas, [f], SMALL, workers=2, stop_days=5)
    assert set(res["wape"]) == {"pooled_h6", "pooled_h24", "lobo_h6", "lobo_h24"}
    assert np.isclose(res["score"], np.mean(list(res["wape"].values())))
    assert res["score"] < 0.05                                  # the series is exactly periodic


def test_search_writes_trials_and_resumes(tmp_path, monkeypatch):
    gold = make_gold()
    f = fold_for(gold)
    f = type(f)("fold03", f.val_start, f.val_end)
    datas = {h: gbm.load_horizon(gold, h, gold.index.max()) for h in (6, 24)}
    monkeypatch.setattr(tuning, "load_data", lambda g: (datas, [f]))
    monkeypatch.setattr(gbm, "PARAMS", SMALL)
    monkeypatch.setattr(tuning, "STOP_DAYS", 5)
    tuning.search(gold, tmp_path, trials=2, seed=0, workers=2, threads=1, log=lambda m: None)
    first = [json.loads(x) for x in (tmp_path / "trials.jsonl").read_text().splitlines()]
    assert [t["trial"] for t in first] == [0, 1, 2]
    tuning.search(gold, tmp_path, trials=3, seed=0, workers=2, threads=1, log=lambda m: None)
    again = [json.loads(x) for x in (tmp_path / "trials.jsonl").read_text().splitlines()]
    assert [t["trial"] for t in again] == [0, 1, 2, 3]            # old trials not repeated
    assert tuning.best_trial(again)["score"] == min(t["score"] for t in again)


def test_compare_to_first_run_has_both_runs():
    idx = pd.date_range("2020-01-01", periods=24, freq="h", tz="Etc/GMT-1")
    base = pd.DataFrame({"time": idx, "y_true": 100.0, "y_pred": 90.0, "y_base": 80.0, "fold": "fold01",
                         "scheme": "pooled", "target": "residual", "horizon": 6})
    t = tuning.compare_to_first_run(base.assign(y_pred=95.0), base)
    assert t["wape_first"].iloc[0] > t["wape_tuned"].iloc[0] and t["wape_change"].iloc[0] < 0
