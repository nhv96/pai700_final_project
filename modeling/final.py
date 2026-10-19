"""Final evaluation on the untouched test block (2022-03-01 onward). Run it once, after the choices are made.

Choices fixed from the validation folds (notebooks/quality_inspect_decision.md, 2026-10-19):
  horizon 1      trees alone, direct target (better than residual in 10 of 10 folds)
  horizon 6, 24  50/50 average of trees (residual target) and GRU (residual target)
Features: day types + DEFAULT_TREND_GROUPS. All models are trained on every window whose target hour is
before the test block and scored on windows whose target hour is in it. Nothing is tuned on the test block.

Usage: python -m modeling.final [--dry-run] [--out results/final]
"""
import argparse
from pathlib import Path

import pandas as pd

from etl import windows as w
from modeling import gbm, gru, metrics
from modeling.persistence_report import add_persistence, compare


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="data/gold/htot_oslo.parquet")
    ap.add_argument("--out", default="results/final")
    ap.add_argument("--dry-run", action="store_true", help="only print window counts, train nothing")
    args = ap.parse_args()

    gold = pd.read_parquet(args.gold)
    _, t0 = w.make_folds(gold.index)
    end = gold.index.max() + pd.Timedelta(hours=1)
    test = w.Fold("test", t0, end)
    print(f"test block {t0} to {gold.index.max()}")

    out = []
    for h in w.HORIZONS:
        d = gbm.load_horizon(gold, h, end, daytypes=True, trends=True)
        n_test = int((d.time >= t0).sum())
        print(f"horizon {h}: {len(d.y) - n_test} training windows, {n_test} test windows")
        if args.dry_run:
            continue
        if h == 1:
            res = gbm.run_fold(d, test, "pooled", "direct")
        else:
            trees = gbm.run_fold(d, test, "pooled", "residual")
            nn = gru.run_fold(gru.load_horizon(gold, h, end), test, "pooled", "residual", log=print)
            key = ["time", "building_id"]
            res = trees.merge(nn[[*key, "y_pred"]], on=key, suffixes=("", "_gru"), validate="1:1")
            if len(res) != len(trees) or len(trees) != len(nn):
                raise ValueError("trees and GRU predictions do not cover the same windows")
            res["y_pred_trees"] = res["y_pred"]
            res["y_pred"] = (res["y_pred_trees"] + res["y_pred_gru"]) / 2
        out.append(res)
    if args.dry_run:
        return

    preds = pd.concat(out, ignore_index=True)
    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(dest / "predictions.parquet")
    for name, by in {"overall": ["horizon"], "by_building": ["horizon", "building_id"]}.items():
        metrics.score_table(preds, by=by).to_csv(dest / f"{name}.csv", index=False)
    print(pd.read_csv(dest / "overall.csv").round(3).to_string(index=False))
    p1 = add_persistence(preds, gold)
    compare(p1, by=["scheme"]).to_csv(dest / "horizon1_vs_persistence.csv", index=False)
    print(pd.read_csv(dest / "horizon1_vs_persistence.csv").round(3).to_string(index=False))


if __name__ == "__main__":
    main()
