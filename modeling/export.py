"""Train the final models on everything before the test block and save them (models/ai_v1/).

The same choices as modeling/final.py (horizon 1: trees direct; horizons 6 and 24: trees + GRU on the
residual target), the same settings and seeds, so the saved models reproduce the test-block scores.
Only windows with target before the test block are used. The test block is not loaded.

Usage: python -m modeling.export [--gold data/gold/htot_oslo.parquet] [--out models/ai_v1]
"""
import argparse
import json
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from etl import windows as w
from modeling import gbm, gru
from modeling.features import DEFAULT_TREND_GROUPS
from modeling.predictor import sha256_of

VERSION = "ai_v1"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="data/gold/htot_oslo.parquet")
    ap.add_argument("--out", default=f"models/{VERSION}")
    ap.add_argument("--final-scores", default="results/final/overall.csv", help="test scores to record, if present")
    args = ap.parse_args()

    gold = pd.read_parquet(args.gold)
    _, t0 = w.make_folds(gold.index)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    horizons = {}
    for h in w.HORIZONS:
        d = gbm.load_horizon(gold, h, t0, daytypes=True, trends=True)
        assert (d.time < t0).all()
        target = "direct" if h == 1 else "residual"
        lags = {} if target == "direct" else gbm.chosen_lags(d, t0)
        anchor = np.zeros(len(d.y), np.float32) if target == "direct" else gbm.baseline_forecast(d, t0)
        model = gbm.fit_model(d.X, d.y - anchor, d.time, gbm.PARAMS)
        spec = {"target": target, "lags": {str(b): int(l) for b, l in lags.items()}, "trees": f"lgb_h{h}.txt",
                "n_training_windows": int(len(d.y))}
        model.booster_.save_model(str(out / spec["trees"]))
        if h > 1:
            g = gru.load_horizon(gold, h, t0)
            base = gbm.baseline_forecast(g, t0)
            sc = gru.Scaled.fit(g, t0)
            net = gru.fit_net(sc, np.arange(len(g.y)), base, base, log=print)
            spec.update(gru=f"gru_h{h}.pt", gru_mean=sc.mean.tolist(), gru_std=sc.std.tolist())
            torch.save(net.state_dict(), out / spec["gru"])
        horizons[str(h)] = spec
        print(f"horizon {h} saved")

    files = sorted(p.name for p in out.iterdir() if p.suffix in (".txt", ".pt"))
    manifest = {
        "version": VERSION, "train_end": str(t0), "lookback": w.LOOKBACK,
        "features": {"daytypes": True, "trend_groups": list(DEFAULT_TREND_GROUPS)},
        "rule": "horizon 1: trees (direct); horizons 6 and 24: average of trees and GRU (residual)",
        "horizons": horizons,
        "files": {f: sha256_of(out / f) for f in files},
        "versions": {"lightgbm": version("lightgbm"), "torch": version("torch"), "pandas": version("pandas")},
        "units": "Wh per hour",
        "test_scores": (pd.read_csv(args.final_scores).query("season == 'all'")[["horizon", "mae_kwh", "wape", "skill"]]
                        .round(4).to_dict("records") if Path(args.final_scores).is_file() else None),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {out}/manifest.json")


if __name__ == "__main__":
    main()
