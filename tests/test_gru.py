import numpy as np
import pandas as pd

from etl import windows as w
from modeling import gru


def _gold(n=400, bid=1):
    idx = pd.date_range("2018-01-01", periods=n, freq="h")
    t = np.arange(n, dtype=float)
    return pd.DataFrame({"building_id": bid, "HtTot": t * 10 + 1, "Tout": t, "SolGlob": 0.0, "WindSpd": 1.0,
                         "WindDir_sin": 0.0, "WindDir_cos": 1.0}, index=idx)


def test_batch_alignment_and_scaling():
    gold = _gold()
    d = gru.load_horizon(gold, 6, pd.Timestamp("2018-02-01"))
    sc = gru.Scaled.fit(d, pd.Timestamp("2018-01-10"))
    rows = np.array([0, 5])
    hist, fut, _ = sc.batch(rows, np.zeros(len(d.y), np.float32))
    assert hist.shape == (2, w.LOOKBACK, len(gru.COLS)) and fut.shape == (2, 6, len(gru.FUT_COLS))
    raw = lambda x: x * sc.std[0] + sc.mean[0]
    origin = d.pos[0]
    assert np.isclose(raw(hist[0, -1, 0].item()), gold["HtTot"].iloc[origin])            # last history hour = origin
    assert np.isclose(raw(hist[0, 0, 0].item()), gold["HtTot"].iloc[origin - w.LOOKBACK + 1])
    assert np.isclose(d.y[0], gold["HtTot"].iloc[origin + 6])                            # target = origin + horizon
    assert np.isclose(fut[0, 0, 0].item() * sc.std[1] + sc.mean[1], gold["Tout"].iloc[origin + 1])
    assert len(gru.FUT_COLS) == len(gru.COLS) - 1                                         # no HtTot in the future


def test_net_output_shape():
    net = gru.Net(len(gru.COLS), len(gru.FUT_COLS), hidden=8)
    import torch
    out = net(torch.zeros(3, w.LOOKBACK, len(gru.COLS)), torch.zeros(3, 6, len(gru.FUT_COLS)), torch.zeros(3))
    assert out.shape == (3,)
