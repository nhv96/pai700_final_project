"""Silver and gold layers for predicting HtTot from weather (COFACTOR-SBHUB Oslo).

Decisions are tracked in notebooks/quality_inspect_decision.md. Run from the project root:

    uv run python -m etl.preprocess_htot
"""
from pathlib import Path

import pandas as pd

RAW = Path("datasets/COFACTOR-SBHUB-Oslo/Dataset_buildings_csv_files")
SILVER = Path("data/silver")
GOLD = Path("data/gold")

BUILDINGS = [8105, 8107, 8116]
TARGET = "HtTot"
WEATHER = ["Tout", "SolGlob", "WindSpd", "WindDir"]
COLUMNS = [TARGET, *WEATHER]

TOUT_SENTINEL = -100     # Tout below this (-273.15 in the data) is a missing-value marker
MAX_INTERP_HOURS = 3     # weather gaps longer than this stay empty
FLAT_MIN_RUN = 6         # HtTot runs of identical values (> 0) at least this long are dropped
SPLIT = (0.70, 0.15, 0.15)  # train / validation / test, chronological, per building
TZ = "Etc/GMT-1"        # fixed UTC+1 all year, no DST


def read_building(building_id: int) -> pd.DataFrame:
    """Read one raw file: parse the metadata block, then the data rows."""
    path = RAW / f"export_{building_id}.txt"
    meta = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        header_line = int(f.readline().strip().split(";")[1])
        for _ in range(2, header_line):
            line = f.readline().strip()
            if ";" in line:
                k, v = line.split(";", 1)
                meta[k] = v.rstrip(";")
    df = pd.read_csv(path, sep=";", skiprows=header_line - 1, usecols=["TimeStamp", *COLUMNS])
    df["timestamp"] = pd.to_datetime(df.pop("TimeStamp").str[:19]).dt.tz_localize(TZ)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.attrs["meta"] = meta
    return df


def to_silver(df: pd.DataFrame, building_id: int) -> pd.DataFrame:
    """Typed, unified schema on a complete hourly grid. Gaps stay as NaN, nothing is filled."""
    df = df.astype("float64").reindex(pd.date_range(df.index.min(), df.index.max(), freq="h"))
    df.index.name = "timestamp"
    df.loc[df["Tout"] < TOUT_SENTINEL, "Tout"] = pd.NA
    df["SolGlob"] = df["SolGlob"].clip(lower=0)
    meta = df.attrs.get("meta", {})
    df.insert(0, "building_id", building_id)
    df["floor_area"] = float(meta["floor_area"])
    df["year_of_construction"] = int(meta["year_of_construction"])
    return df


def short_gap_interpolate(s: pd.Series, max_hours: int) -> pd.Series:
    """Linearly fill NaN gaps of at most max_hours. Longer gaps are left entirely empty."""
    filled = s.interpolate(limit_area="inside")
    gap_id = s.notna().cumsum()
    gap_len = s.isna().groupby(gap_id).transform("sum")
    return s.where(~(s.isna() & (gap_len <= max_hours)), filled)


def flat_run_mask(s: pd.Series, min_run: int) -> pd.Series:
    """True for every hour that belongs to a run of >= min_run identical values above zero."""
    run_id = s.ne(s.shift()).cumsum()
    run_len = s.groupby(run_id).transform("size")
    return s.gt(0) & (run_len >= min_run)


def to_gold(silver: pd.DataFrame) -> pd.DataFrame:
    """Model-ready rows: short weather gaps interpolated, bad/empty HtTot rows dropped, split labelled."""
    g = silver.copy()
    for col in WEATHER:
        g[col] = short_gap_interpolate(g[col], MAX_INTERP_HOURS)
    g.loc[g[TARGET].eq(0) | flat_run_mask(g[TARGET], FLAT_MIN_RUN), TARGET] = pd.NA
    g = g.dropna(subset=COLUMNS)

    n = len(g)
    n_train, n_val = int(n * SPLIT[0]), int(n * SPLIT[1])
    split = ["train"] * n_train + ["val"] * n_val + ["test"] * (n - n_train - n_val)
    g["split"] = split
    return g


def main() -> None:
    SILVER.mkdir(parents=True, exist_ok=True)
    GOLD.mkdir(parents=True, exist_ok=True)
    gold_parts = []
    for bid in BUILDINGS:
        silver = to_silver(read_building(bid), bid)
        silver.to_parquet(SILVER / f"building_{bid}.parquet")
        gold = to_gold(silver)
        gold_parts.append(gold)
        counts = gold["split"].value_counts().to_dict()
        print(f"{bid}: silver {len(silver)} rows -> gold {len(gold)} rows "
              f"({gold.index.min().date()} to {gold.index.max().date()}) {counts}")
    pd.concat(gold_parts).to_parquet(GOLD / "htot_oslo.parquet")


if __name__ == "__main__":
    main()
