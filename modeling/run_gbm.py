"""Run the LightGBM experiment on the gold layer and write predictions and score tables.

Usage: python -m modeling.run_gbm [--gold data/gold/htot_oslo.parquet] [--out results/gbm]
"""
import argparse
from pathlib import Path

import pandas as pd

from modeling import gbm, metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="data/gold/htot_oslo.parquet")
    ap.add_argument("--out", default="results/gbm")
    ap.add_argument("--daytypes", action="store_true", help="add holiday and school-break features")
    ap.add_argument("--trends", action="store_true", help="add change and accumulation features")
    args = ap.parse_args()

    gold = pd.read_parquet(args.gold)
    preds = gbm.run_all(gold, daytypes=args.daytypes, trends=args.trends)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(out / "predictions.parquet")
    for name, by in {"overall": ["scheme", "target", "horizon"],
                     "by_building": ["scheme", "target", "horizon", "building_id"],
                     "by_fold": ["scheme", "target", "horizon", "fold"]}.items():
        metrics.score_table(preds, by=by).to_csv(out / f"{name}.csv", index=False)
    print(pd.read_csv(out / "overall.csv").round(3).to_string(index=False))


if __name__ == "__main__":
    main()
