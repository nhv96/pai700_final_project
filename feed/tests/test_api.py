import json
import time

import pytest
from fastapi.testclient import TestClient

from feed import freeze as fz
from feed.api import create_app
from feed.store import Store


@pytest.fixture()
def client(frozen_path):
    return TestClient(create_app(str(frozen_path)))


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields.get("event"), fields.get("id"), json.loads(fields["data"])))
    return events


def test_buildings_info(client):
    body = client.get("/buildings").json()
    assert [b["building_id"] for b in body["buildings"]] == [8105, 8107, 8116]
    assert body["window"]["replay_start"].startswith("2022-10-01T00:00:00+01:00")
    assert body["window"]["last"].startswith("2023-03-31T23:00:00+01:00")
    assert len(body["sha256"]) == 64


def test_readings_never_go_past_until(client):
    rows = client.get("/readings", params={"until": "2022-12-01T10:00:00+01:00", "from": "2022-12-01T08:00"}).json()
    assert {r["timestamp"] for r in rows} == {f"2022-12-01T{h:02d}:00:00+01:00" for h in (8, 9, 10)}
    assert len(rows) == 9
    assert all(r["phase"] == "replay" for r in rows)


def test_readings_until_is_required_and_clamped(client):
    assert client.get("/readings").status_code == 422
    rows = client.get("/readings", params={"until": "2030-01-01T00:00", "from": "2023-03-31T22:00"}).json()
    assert len(rows) == 6                                    # 2 hours x 3 buildings, clamped to the window end


def test_readings_building_filter_and_unknown(client):
    rows = client.get("/readings", params={"until": "2022-10-01T00:00", "from": "2022-10-01T00:00", "building": [8107]}).json()
    assert [r["building_id"] for r in rows] == [8107]
    assert client.get("/readings", params={"until": "2022-10-01T00:00", "building": [1]}).status_code == 404
    assert client.get("/readings", params={"until": "yesterday-ish"}).status_code == 422


def test_timezone_offsets_are_converted(client):
    a = client.get("/readings", params={"until": "2022-12-01T10:00:00+01:00", "from": "2022-12-01T10:00:00+01:00"}).json()
    b = client.get("/readings", params={"until": "2022-12-01T09:00:00Z", "from": "2022-12-01T09:00:00Z"}).json()
    assert a == b and len(a) == 3


def test_weather_forecast_has_no_heat_and_only_the_future(client):
    body = client.get("/weather-forecast", params={"now": "2022-12-01T10:00", "hours": 6, "building": [8105]}).json()
    assert "perfect forecast" in body["note"]
    w = body["weather"]
    assert [r["timestamp"][11:13] for r in w] == ["11", "12", "13", "14", "15", "16"]
    assert all("HtTot" not in r and "phase" not in r for r in w)
    assert set(w[0]) == {"timestamp", "building_id", "Tout", "SolGlob", "WindSpd", "WindDir"}
    assert client.get("/weather-forecast", params={"now": "2022-12-01T10:00", "hours": 0}).status_code == 422
    assert client.get("/weather-forecast", params={"now": "2022-12-01T10:00", "hours": 169}).status_code == 422


def test_weather_forecast_stops_at_window_end(client):
    w = client.get("/weather-forecast", params={"now": "2023-03-31T21:00", "hours": 24}).json()["weather"]
    assert len(w) == 2 * 3


def test_stream_sends_one_event_per_hour_then_end(client):
    r = client.get("/stream", params={"speed": 1e6, "from": "2023-03-31T21:00"})
    events = parse_sse(r.text)
    assert [e[0] for e in events] == ["reading"] * 3 + ["end"]
    assert [e[1][11:13] for e in events[:3]] == ["21", "22", "23"]
    assert all(len(e[2]["readings"]) == 3 for e in events[:3])
    assert events[-1][2]["last"].startswith("2023-03-31T23:00")


def test_stream_defaults_to_warmup_and_marks_phase(client):
    with client.stream("GET", "/stream", params={"speed": 1e6}) as r:
        first = next(l for l in r.iter_lines() if l.startswith("data: "))
    data = json.loads(first[6:])
    assert data["timestamp"].startswith("2022-09-24T00:00")
    assert {x["phase"] for x in data["readings"]} == {"warmup"}


def test_stream_resumes_after_last_event_id(client):
    r = client.get("/stream", params={"speed": 1e6}, headers={"Last-Event-ID": "2023-03-31T21:00:00+01:00"})
    assert [e[1][11:13] for e in parse_sse(r.text)[:2]] == ["22", "23"]


def test_stream_speed_paces_events(client):
    t = time.monotonic()
    client.get("/stream", params={"speed": 20, "from": "2023-03-31T19:00", "building": [8105]})
    assert time.monotonic() - t >= 0.2                       # 5 hours -> 4 gaps of 0.05 s
    assert client.get("/stream", params={"speed": 0}).status_code == 422


def test_refuses_file_that_does_not_match_checksum(frozen_path, tmp_path):
    bad = tmp_path / frozen_path.name
    bad.write_bytes(frozen_path.read_bytes() + b"x")
    (tmp_path / (frozen_path.name + ".sha256")).write_text((frozen_path.parent / (frozen_path.name + ".sha256")).read_text())
    with pytest.raises(ValueError, match="checksum"):
        Store(bad)
