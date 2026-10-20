import httpx
import pytest
from fastapi.testclient import TestClient

from forecast_service.app import create_app
from modeling.predictor import Predictor
from .conftest import feed_rows, make_fake_feed

NOW = "2022-10-15T10:00"


@pytest.fixture
def client(model_dir):
    return TestClient(create_app("http://feed", str(model_dir), httpx.MockTransport(make_fake_feed(feed_rows()))))


def test_health_and_model(client):
    assert client.get("/health").json() == {"status": "ok", "model": "test"}
    m = client.get("/model").json()
    assert m["horizons"] == [1, 6, 24] and m["buildings"] == [8105] and "perfect forecast" in m["note"]


def test_forecast_has_all_horizons_with_target_times(client):
    r = client.get("/forecast", params={"now": NOW})
    assert r.status_code == 200
    body = r.json()
    assert [f["horizon"] for f in body["forecasts"]] == [1, 6, 24]
    assert [f["target_time"][:13] for f in body["forecasts"]] == ["2022-10-15T11", "2022-10-15T16", "2022-10-16T10"]
    for f in body["forecasts"]:
        assert f["wh"] >= 0
    h1, h6 = body["forecasts"][0], body["forecasts"][1]
    assert h1["gru_wh"] is None and h6["gru_wh"] is not None          # horizon 1 is trees only
    assert h6["wh"] == pytest.approx((h6["trees_wh"] + h6["gru_wh"]) / 2, abs=0.2)  # the blend is the plain average


def test_forecast_ignores_heat_after_the_origin(model_dir):
    rows = feed_rows()
    changed = [dict(r, HtTot=r["HtTot"] * 3) if r["timestamp"][:16] > NOW else r for r in rows]
    a, b = (TestClient(create_app("http://feed", str(model_dir), httpx.MockTransport(make_fake_feed(x))))
            .get("/forecast", params={"now": NOW}).json() for x in (rows, changed))
    assert a["forecasts"] == b["forecasts"]


def test_series_matches_single_forecasts(client):
    s = client.get("/forecast/series", params={"from": "2022-10-14T00:00", "until": "2022-10-14T05:00"}).json()
    assert [len(s["series"][h]) for h in ("1", "6", "24")] == [6, 6, 6]
    single = client.get("/forecast", params={"now": "2022-10-14T03:00"}).json()["forecasts"]
    for f in single:
        row = next(x for x in s["series"][str(f["horizon"])] if x["origin"].startswith("2022-10-14T03"))
        assert row["wh"] == pytest.approx(f["wh"], abs=0.2)


def test_origin_without_enough_history_is_refused(client):
    r = client.get("/forecast", params={"now": "2022-10-02T00:00"})
    assert r.status_code == 422 and "168" in r.json()["detail"]


def test_series_covers_only_possible_origins(client):
    s = client.get("/forecast/series", params={"from": "2022-10-19T00:00", "until": "2022-10-20T23:00"}).json()
    # data ends 2022-10-20 23:00: a 24 h forecast needs the weather of the next 24 h
    assert s["covered"]["1"]["last_origin"].startswith("2022-10-20T22")
    assert s["covered"]["24"]["last_origin"].startswith("2022-10-20T22") is False
    assert s["covered"]["24"]["last_origin"].startswith("2022-10-19T23")


def test_bad_input(client):
    assert client.get("/forecast", params={"now": "not a date"}).status_code == 422
    assert client.get("/forecast", params={"now": NOW, "horizons": "2"}).status_code == 422
    assert client.get("/forecast", params={"now": NOW, "building": 1}).status_code == 404
    assert client.get("/forecast/series", params={"from": NOW, "until": "2022-10-01T00:00"}).status_code == 422


def test_a_changed_model_file_is_refused(model_dir, tmp_path):
    import shutil
    copy = tmp_path / "m"
    shutil.copytree(model_dir, copy)
    (copy / "lgb_h1.txt").write_text("tampered")
    with pytest.raises(ValueError, match="manifest"):
        Predictor(copy)


def test_unreachable_feed_is_502(model_dir):
    def down(request):
        raise httpx.ConnectError("down")
    c = TestClient(create_app("http://feed", str(model_dir), httpx.MockTransport(down)))
    assert c.get("/forecast", params={"now": NOW}).status_code == 502
