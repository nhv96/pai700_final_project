import pandas as pd
import pytest

from feed import freeze as fz
from tests.test_freeze import make_silver


@pytest.fixture(scope="session")
def frozen_path(tmp_path_factory):
    root = tmp_path_factory.mktemp("feed")
    silver = root / "silver"
    silver.mkdir()
    make_silver(silver)
    # make the three buildings distinguishable hour by hour
    for bid in fz.BUILDINGS:
        df = pd.read_parquet(silver / f"building_{bid}.parquet")
        df["HtTot"] = [bid * 1000.0 + i for i in range(len(df))]
        df.to_parquet(silver / f"building_{bid}.parquet")
    return fz.freeze(silver, root / "out")
