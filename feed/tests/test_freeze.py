import pandas as pd
import pytest

from feed import freeze as fz

IDX = pd.date_range("2022-09-01", "2023-04-30 23:00", freq="h", tz=fz.TZ, name="timestamp")


def make_silver(tmp_path, buildings=fz.BUILDINGS, hole=None):
    for i, bid in enumerate(buildings):
        df = pd.DataFrame({"building_id": bid, "HtTot": 1000.0 * (i + 1), "Tout": 1.0, "SolGlob": 0.0,
                           "WindSpd": 2.0, "WindDir": 90.0, "floor_area": 5000.0 + i,
                           "year_of_construction": 1980 + i}, index=IDX)
        if hole is not None:
            df.loc[hole, "HtTot"] = float("nan")
        df.to_parquet(tmp_path / f"building_{bid}.parquet")


def test_window_bounds_phases_and_static(tmp_path):
    make_silver(tmp_path)
    w = fz.build_window(tmp_path)
    assert list(w.columns) == fz.COLUMNS
    assert len(w) == 3 * 4536
    assert w["timestamp"].min() == fz.WARMUP_START and w["timestamp"].max() == fz.END
    assert (w.loc[w["phase"] == "warmup", "timestamp"] < fz.REPLAY_START).all()
    assert (w["phase"] == "warmup").sum() == 3 * 168
    assert w.groupby("building_id")["floor_area"].nunique().eq(1).all()
    assert w.equals(w.sort_values(["timestamp", "building_id"], ignore_index=True))


def test_gap_in_window_fails(tmp_path):
    make_silver(tmp_path, hole=pd.Timestamp("2022-12-24 12:00", tz=fz.TZ))
    with pytest.raises(ValueError, match="empty values"):
        fz.build_window(tmp_path)


def test_gap_outside_window_is_fine(tmp_path):
    make_silver(tmp_path, hole=pd.Timestamp("2022-09-10 12:00", tz=fz.TZ))
    assert len(fz.build_window(tmp_path)) == 3 * 4536


def test_freeze_checksum_verify_and_immutability(tmp_path):
    silver, out = tmp_path / "silver", tmp_path / "out"
    silver.mkdir()
    make_silver(silver)
    path = fz.freeze(silver, out)
    assert fz.verify(path)
    assert (out / "oslo_window_v1.parquet.sha256").read_text().split()[1] == path.name

    fz.freeze(silver, out)                       # same content: fine
    make_silver(silver, buildings=(8105, 8107, 8116), hole=None)
    df = pd.read_parquet(silver / "building_8105.parquet")
    df["HtTot"] += 1
    df.to_parquet(silver / "building_8105.parquet")
    with pytest.raises(FileExistsError):         # different content: refused
        fz.freeze(silver, out)
    assert fz.verify(path)
    fz.freeze(silver, out, force=True)
    assert fz.verify(path)


def test_verify_detects_change(tmp_path):
    silver, out = tmp_path / "silver", tmp_path / "out"
    silver.mkdir()
    make_silver(silver)
    path = fz.freeze(silver, out)
    path.write_bytes(path.read_bytes() + b"x")
    assert not fz.verify(path)
