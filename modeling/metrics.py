"""Forecast scores. HtTot is in Wh per hour; errors are reported in kWh (divide by 1000).

WAPE = sum of absolute errors / sum of actual values. It is a percentage-like score that stays
stable when single hours are small, but it is not stable in summer when the whole season is close
to zero, so summer is reported in absolute units (MAE, RMSE in kWh) and WAPE is left empty there.
"""
import numpy as np
import pandas as pd

WH_PER_KWH = 1000.0
SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}


def mae_kwh(y_true, y_pred) -> float:
    return float(np.mean(np.abs(np.asarray(y_pred) - np.asarray(y_true))) / WH_PER_KWH)


def rmse_kwh(y_true, y_pred) -> float:
    return float(np.sqrt(np.mean((np.asarray(y_pred) - np.asarray(y_true)) ** 2)) / WH_PER_KWH)


def wape(y_true, y_pred) -> float:
    """Sum of absolute errors divided by the sum of actuals. NaN if the actuals sum to zero."""
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    total = np.abs(y_true).sum()
    return float(np.abs(y_pred - y_true).sum() / total) if total > 0 else float("nan")


def skill(wape_model: float, wape_baseline: float) -> float:
    """1 - WAPE_model / WAPE_baseline. 0 = no better than the baseline, 1 = perfect."""
    return float("nan") if not wape_baseline > 0 else 1.0 - wape_model / wape_baseline


def score_table(df: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """Scores per group and season, plus an 'all' row.

    df columns: y_true, y_pred, y_base (all Wh), time (target hour, tz-aware), and the `by` columns,
    for example ["building_id", "horizon", "fold"]. Returns n, mae_kwh, rmse_kwh, wape, skill and
    the baseline's mae_kwh and wape. In summer wape and skill are NaN.
    """
    by = list(by or [])
    df = df.assign(season=df["time"].dt.month.map(SEASONS))
    rows = []
    for key, grp in df.groupby(by, sort=True) if by else [((), df)]:
        key = key if isinstance(key, tuple) else (key,)
        for season, part in [("all", grp), *grp.groupby("season", sort=False)]:
            w_model = wape(part["y_true"], part["y_pred"])
            w_base = wape(part["y_true"], part["y_base"])
            summer = season == "summer"
            rows.append({
                **dict(zip(by, key)), "season": season, "n": len(part),
                "mae_kwh": mae_kwh(part["y_true"], part["y_pred"]),
                "rmse_kwh": rmse_kwh(part["y_true"], part["y_pred"]),
                "wape": np.nan if summer else w_model,
                "skill": np.nan if summer else skill(w_model, w_base),
                "base_mae_kwh": mae_kwh(part["y_true"], part["y_base"]),
                "base_wape": np.nan if summer else w_base,
            })
    return pd.DataFrame(rows)
