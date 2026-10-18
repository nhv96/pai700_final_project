"""Run the LightGBM experiment on the gold layer and write predictions and score tables.

Usage: python -m modeling.run_gbm [--gold data/gold/htot_oslo.parquet] [--out results/gbm]
"""
import argparse
from pathlib import Path

import pandas as pd

from modeling import gbm, metrics
from modeling.features import TREND_GROUPS


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="data/gold/htot_oslo.parquet")
    ap.add_argument("--out", default="results/gbm")
    ap.add_argument("--daytypes", action="store_true", help="add holiday and school-break features")
    ap.add_argument("--trends", action="store_true", help="add change and accumulation features")
    ap.add_argument("--drop-trend-group", choices=TREND_GROUPS, help="with --trends: leave this group out (ablation)")
    ap.add_argument("--targets", nargs="+", choices=gbm.TARGETS, default=list(gbm.TARGETS))
    args = ap.parse_args()
    trends = tuple(g for g in TREND_GROUPS if g != args.drop_trend_group) if args.trends else False

    gold = pd.read_parquet(args.gold)
    preds = gbm.run_all(gold, daytypes=args.daytypes, trends=trends, targets=args.targets)
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
