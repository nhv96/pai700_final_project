"""Compare saved model predictions at horizon 1 with persistence (repeat the last known HtTot).

Persistence needs no model run: for a window with target hour T and horizon 1, the origin hour is
T - 1 h and its HtTot is in gold (the window is valid, so that hour exists).

Usage: python -m modeling.persistence_report [--gold ...] [--preds results/gbm/predictions.parquet]
"""
import argparse
from pathlib import Path

import pandas as pd

from modeling import metrics
from modeling.baselines import persistence

BY = ["scheme", "target"]


def add_persistence(preds: pd.DataFrame, gold: pd.DataFrame) -> pd.DataFrame:
    """Rows of horizon 1 with a y_persist column (Wh): the HtTot of the origin hour of each window."""
    p = preds[preds["horizon"] == 1].copy()
    last = gold.set_index(["building_id", gold.index])["HtTot"]
    key = pd.MultiIndex.from_arrays([p["building_id"], p["time"] - pd.Timedelta(hours=1)])
    p["y_persist"] = persistence(last.reindex(key).to_numpy()[:, None])
    if p["y_persist"].isna().any():
        raise ValueError("origin hour missing from gold for some windows")
    return p


def compare(p: pd.DataFrame, by=BY) -> pd.DataFrame:
    """Per group and season: the model, seasonal naive (y_base) and persistence side by side.

    skill_vs_persist is 1 - WAPE_model / WAPE_persistence. Summer has no WAPE (see metrics.py).
    """
    vs_persist = metrics.score_table(p.assign(y_base=p["y_persist"]), by=by)
    vs_seasonal = metrics.score_table(p, by=by)
    out = vs_seasonal[[*by, "season", "n", "mae_kwh", "rmse_kwh", "wape", "skill"]].rename(columns={"skill": "skill_vs_seasonal"})
    out["base_wape_seasonal"] = vs_seasonal["base_wape"].to_numpy()
    out["base_mae_seasonal"] = vs_seasonal["base_mae_kwh"].to_numpy()
    out["base_wape_persist"] = vs_persist["base_wape"].to_numpy()
    out["base_mae_persist"] = vs_persist["base_mae_kwh"].to_numpy()
    out["skill_vs_persist"] = vs_persist["skill"].to_numpy()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="data/gold/htot_oslo.parquet")
    ap.add_argument("--preds", default="results/gbm/predictions.parquet")
    ap.add_argument("--out", default="results/gbm")
    args = ap.parse_args()

    p = add_persistence(pd.read_parquet(args.preds), pd.read_parquet(args.gold))
    out = Path(args.out)
    compare(p).to_csv(out / "horizon1_vs_persistence.csv", index=False)
    compare(p, by=[*BY, "building_id"]).to_csv(out / "horizon1_vs_persistence_by_building.csv", index=False)
    cols = ["scheme", "target", "season", "n", "mae_kwh", "wape", "base_wape_seasonal", "base_wape_persist", "skill_vs_seasonal", "skill_vs_persist"]
    print(pd.read_csv(out / "horizon1_vs_persistence.csv")[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
