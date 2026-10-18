import httpx
import pytest
from fastapi.testclient import TestClient

from twin_service.app import create_app

# Hourly weather for 2022-11-01 .. 2022-11-30 (cold, sunny noon), served like the real feed.
def _rows():
    from datetime import datetime, timedelta
    t, rows = datetime(2022, 11, 1), []
    while t < datetime(2022, 12, 1):
        sun = max(0.0, 150.0 * (1 - abs(t.hour - 12) / 5)) if 7 <= t.hour <= 17 else 0.0
        rows.append({"timestamp": f"{t:%Y-%m-%dT%H:00:00}+01:00", "building_id": 8105, "phase": "replay",
                     "HtTot": 1.0, "Tout": 2.0, "SolGlob": sun, "WindSpd": 1.0, "WindDir": 1.0})
        t += timedelta(hours=1)
    return rows


ROWS = _rows()
calls = []


def fake_feed(request: httpx.Request) -> httpx.Response:
    calls.append(request.url)
    if request.url.path == "/buildings":
        return httpx.Response(200, json={"buildings": [{"building_id": 8105}, {"building_id": 8107}],
                                         "window": {"first": ROWS[0]["timestamp"], "last": ROWS[-1]["timestamp"]}})
    if request.url.path == "/readings":
        return httpx.Response(200, json=[r for r in ROWS
                                         if request.url.params["from"] <= r["timestamp"][:16] <= request.url.params["until"]])
    return httpx.Response(404)


@pytest.fixture
def client():
    calls.clear()
    return TestClient(create_app("http://feed", transport=httpx.MockTransport(fake_feed)))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_compare_returns_both_runs_and_a_warning(client):
    r = client.get("/compare", params={"start": "2022-11-07", "days": 2})
    assert r.status_code == 200
    body = r.json()
    assert set(body["runs"]) == {"legacy", "combined"}
    leg, comb = body["runs"]["legacy"], body["runs"]["combined"]
    assert leg["summary"]["heat_vs_legacy_pct"] == 0.0
    assert len(leg["series"]["time"]) == 2 * 24 * 6  # 10-minute points
    assert set(leg["series"]) == {"time", "t_air_C", "radiator_kW", "coil_kW", "supply_air_C"}
    assert len(body["weather"]["t_outdoor_C"]) == len(leg["series"]["time"])
    assert "Simulation" in body["note"] and body["south_facade_ratio"] == 1.5
    # the combined controller never uses more heat than twice legacy; sanity, not a claim
    assert comb["summary"]["heat_kWh"] > 0


def test_second_identical_request_is_cached(client):
    client.get("/compare", params={"start": "2022-11-07", "days": 1})
    n = len([u for u in calls if u.path == "/readings"])
    client.get("/compare", params={"start": "2022-11-07", "days": 1})
    assert len([u for u in calls if u.path == "/readings"]) == n


def test_run_must_lie_inside_the_window(client):
    assert client.get("/compare", params={"start": "2022-10-01"}).status_code == 422
    assert client.get("/compare", params={"start": "2022-11-29", "days": 5}).status_code == 422


def test_bad_inputs(client):
    assert client.get("/compare", params={"start": "tomorrow"}).status_code == 422
    assert client.get("/compare", params={"start": "2022-11-07", "building": 1}).status_code == 404
    assert client.get("/compare", params={"start": "2022-11-07", "days": 99}).status_code == 422


def test_feed_down_gives_502():
    def down(request):
        raise httpx.ConnectError("refused")
    c = TestClient(create_app("http://feed", transport=httpx.MockTransport(down)))
    assert c.get("/compare").status_code == 502
