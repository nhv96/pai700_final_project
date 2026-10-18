"""Cut the shared time window out of the silver layer and freeze it as one parquet file plus a SHA-256 checksum.

The frozen file is the single data source for the twin, the AI model and the dashboard. It is immutable:
an existing file is never overwritten with different content unless --force is given.

Run from the feed/ folder:

    uv run python -m feed.freeze [--silver ../data/silver] [--out ../frozen]
    uv run python -m feed.freeze verify [--out ../frozen]     # check the file against its checksum

Only the silver parquet files are read (they already carry floor_area and year_of_construction).
Timestamps stay in the data's fixed UTC+1 time (Etc/GMT-1, no DST).
"""
import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

TZ = "Etc/GMT-1"
WARMUP_START = pd.Timestamp("2022-09-24 00:00", tz=TZ)   # 7 days of history before the replay starts
REPLAY_START = pd.Timestamp("2022-10-01 00:00", tz=TZ)
END = pd.Timestamp("2023-03-31 23:00", tz=TZ)            # last hour, inclusive
BUILDINGS = (8105, 8107, 8116)
NAME = "oslo_window_v1"

VALUE_COLUMNS = ["HtTot", "Tout", "SolGlob", "WindSpd", "WindDir"]
STATIC_COLUMNS = ["floor_area", "year_of_construction"]
COLUMNS = ["timestamp", "building_id", "phase", *VALUE_COLUMNS, *STATIC_COLUMNS]


def build_window(silver_dir: Path, buildings=BUILDINGS) -> pd.DataFrame:
    """One long table, sorted by timestamp then building. `phase` is "warmup" or "replay"."""
    parts = []
    for bid in buildings:
        df = pd.read_parquet(silver_dir / f"building_{bid}.parquet")
        df = df.loc[WARMUP_START:END].copy()
        df["building_id"] = bid
        parts.append(df.reset_index())
    window = pd.concat(parts, ignore_index=True)
    window["phase"] = pd.Series("replay", index=window.index).mask(window["timestamp"] < REPLAY_START, "warmup")
    window = window[COLUMNS].sort_values(["timestamp", "building_id"], ignore_index=True)
    validate(window, buildings)
    return window


def validate(window: pd.DataFrame, buildings=BUILDINGS) -> None:
    """Fail loudly: the frozen window must be complete, because replay and the model rely on a full hourly grid."""
    hours = pd.date_range(WARMUP_START, END, freq="h")
    for bid in buildings:
        sub = window[window["building_id"] == bid]
        if not pd.DatetimeIndex(sub["timestamp"]).equals(hours):
            raise ValueError(f"building {bid}: timestamps are not the complete hourly grid {hours[0]} .. {hours[-1]}")
        missing = sub[[*VALUE_COLUMNS, *STATIC_COLUMNS]].isna().sum()
        if missing.any():
            raise ValueError(f"building {bid}: empty values in the window: {missing[missing > 0].to_dict()}")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksum(path: Path) -> Path:
    """Write <file>.sha256 in `sha256sum` format, so `sha256sum -c` works."""
    sum_path = path.with_name(path.name + ".sha256")
    sum_path.write_text(f"{sha256_of(path)}  {path.name}\n")
    return sum_path


def verify(path: Path) -> bool:
    sum_path = path.with_name(path.name + ".sha256")
    expected = sum_path.read_text().split()[0]
    return sha256_of(path) == expected


def freeze(silver_dir: Path, out_dir: Path, force: bool = False) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{NAME}.parquet"
    candidate = out_dir / f".{NAME}.parquet.new"
    build_window(silver_dir).to_parquet(candidate, index=False)
    try:
        if target.exists() and sha256_of(target) != sha256_of(candidate) and not force:
            raise FileExistsError(f"{target} exists with different content; the frozen file is immutable (use --force to replace it)")
        candidate.replace(target)
    finally:
        candidate.unlink(missing_ok=True)
    write_checksum(target)
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?", choices=["freeze", "verify"], default="freeze")
    ap.add_argument("--silver", default="../data/silver", type=Path)
    ap.add_argument("--out", default="../frozen", type=Path)
    ap.add_argument("--force", action="store_true", help="replace an existing frozen file that differs")
    args = ap.parse_args(argv)

    if args.command == "verify":
        path = args.out / f"{NAME}.parquet"
        ok = verify(path)
        print(f"{path}: {'OK' if ok else 'CHECKSUM MISMATCH'}")
        return 0 if ok else 1

    path = freeze(args.silver, args.out, args.force)
    df = pd.read_parquet(path)
    print(f"{path}: {len(df)} rows, {df['building_id'].nunique()} buildings, "
          f"{df['timestamp'].min()} .. {df['timestamp'].max()}")
    print(f"sha256 {sha256_of(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
