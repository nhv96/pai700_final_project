"""Plot the test-block forecasts against the actual HtTot for a winter week and a holiday week.

Usage: python -m modeling.plot_final [--preds results/final/predictions.parquet] [--out results/final/figures]
Weeks are Monday to Sunday (fixed UTC+1). Each panel is one building; the 1 h and 24 h forecasts are
the ones scored in modeling.final (horizon 1: trees; horizon 24: average of trees and GRU).
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

WEEKS = {"winter": ("2023-01-16", "A winter week (16-22 Jan 2023)"),
         "holiday": ("2022-12-19", "Christmas week (19-25 Dec 2022; school break from 21 Dec)")}
HORIZONS = {1: ("1 h ahead", "tab:orange"), 24: ("24 h ahead", "tab:green")}


def plot_week(p: pd.DataFrame, start: str, title: str, path: Path) -> None:
    t0 = pd.Timestamp(start, tz=p["time"].dt.tz)
    p = p[(p["time"] >= t0) & (p["time"] < t0 + pd.Timedelta(days=7))]
    buildings = sorted(p["building_id"].unique())
    fig, axes = plt.subplots(len(buildings), 1, figsize=(11, 3 * len(buildings)), sharex=True)
    for ax, b in zip(axes, buildings):
        pb = p[p["building_id"] == b]
        actual = pb[pb["horizon"] == 1].set_index("time")["y_true"] / 1000
        ax.plot(actual.index, actual, color="black", lw=1.6, label="Actual")
        for h, (label, color) in HORIZONS.items():
            f = pb[pb["horizon"] == h].set_index("time")["y_pred"] / 1000
            ax.plot(f.index, f, color=color, lw=1.1, label=f"Forecast {label}")
        ax.set_ylabel(f"Building {b}\nHtTot (kWh/h)")
        ax.grid(alpha=0.3)
    axes[0].legend(ncol=3, loc="upper right")
    axes[0].set_title(title)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", default="results/final/predictions.parquet")
    ap.add_argument("--out", default="results/final/figures")
    args = ap.parse_args()
    p = pd.read_parquet(args.preds)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, (start, title) in WEEKS.items():
        plot_week(p, start, title, out / f"{name}_week.png")
        print(out / f"{name}_week.png")


if __name__ == "__main__":
    main()
