"""Run the GRU experiment on the gold layer; same output tables as modeling.run_gbm.

Usage: python -m modeling.run_gru [--out results/gru] [--horizons 1 6 24] [--folds fold10 ...]
"""
import argparse
from pathlib import Path

import pandas as pd

from etl import windows as w
from modeling import gru, metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="data/gold/htot_oslo.parquet")
    ap.add_argument("--out", default="results/gru")
    ap.add_argument("--horizons", nargs="+", type=int, default=list(w.HORIZONS))
    ap.add_argument("--folds", nargs="+", help="fold names, default all")
    ap.add_argument("--schemes", nargs="+", choices=gru.SCHEMES, default=list(gru.SCHEMES))
    ap.add_argument("--targets", nargs="+", choices=gru.TARGETS, default=["residual"])
    ap.add_argument("--epochs", type=int, default=gru.MAX_EPOCHS)
    args = ap.parse_args()

    gold = pd.read_parquet(args.gold)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    preds = gru.run_all(gold, args.horizons, args.schemes, args.targets, args.folds, args.epochs)
    preds.to_parquet(out / "predictions.parquet")
    for name, by in {"overall": ["scheme", "target", "horizon"],
                     "by_building": ["scheme", "target", "horizon", "building_id"],
                     "by_fold": ["scheme", "target", "horizon", "fold"]}.items():
        metrics.score_table(preds, by=by).to_csv(out / f"{name}.csv", index=False)
    print(pd.read_csv(out / "overall.csv").round(3).to_string(index=False))


if __name__ == "__main__":
    main()
