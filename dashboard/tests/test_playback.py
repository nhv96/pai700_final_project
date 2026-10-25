import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.playback import MAX_SPEED, Playback

FIRST, REPLAY, LAST = "2022-09-24T00:00:00+01:00", "2022-10-15T00:00:00+01:00", "2022-10-25T00:00:00+01:00"


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def make():
    clock = Clock()
    return Playback(FIRST, REPLAY, LAST, clock), clock


def test_not_started_has_no_position():
    pb, _ = make()
    s = pb.state()
    assert not s["playing"] and not s["started"] and s["position"] is None and s["phase"] is None


def test_play_advances_with_real_time_and_speed():
    pb, clock = make()
    pb.set_speed(10)
    pb.play()
    assert pb.state()["position"] == FIRST          # the first hour is there at once
    clock.t += 5.5                                  # 55 simulated hours
    s = pb.state()
    assert s["position"] == "2022-09-26T07:00:00+01:00" and s["phase"] == "warmup" and s["playing"]


def test_pause_freezes_and_play_resumes_from_there():
    pb, clock = make()
    pb.set_speed(24)
    pb.play()
    clock.t += 2                                    # 48 h
    pb.pause()
    clock.t += 1000
    assert pb.state()["position"] == "2022-09-26T00:00:00+01:00" and not pb.state()["playing"]
    pb.play()
    clock.t += 1
    assert pb.state()["position"] == "2022-09-27T00:00:00+01:00"


def test_speed_change_keeps_the_position():
    pb, clock = make()
    pb.set_speed(24)
    pb.play()
    clock.t += 1                                    # 24 h
    pb.set_speed(1)
    clock.t += 3
    assert pb.state()["position"] == "2022-09-25T03:00:00+01:00"


def test_phase_switches_to_replay():
    pb, clock = make()
    pb.set_speed(24)
    pb.play()
    clock.t += 21
    assert pb.state()["phase"] == "replay"


def test_stops_at_the_end_and_cannot_play_again_until_restart():
    pb, clock = make()
    pb.set_speed(MAX_SPEED)
    pb.play()
    clock.t += 10
    s = pb.state()
    assert s["finished"] and not s["playing"] and s["position"] == LAST and s["progress"] == 1
    pb.play()
    assert not pb.state()["playing"]
    pb.restart()
    s = pb.state()
    assert s["playing"] and s["position"] == FIRST and not s["finished"]


@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan"), MAX_SPEED + 1])
def test_bad_speed_is_refused(bad):
    pb, _ = make()
    with pytest.raises(ValueError):
        pb.set_speed(bad)


def test_events_send_state_first_and_again_after_a_change():
    async def run():
        pb, _ = make()
        gen = pb.events()
        first = json.loads((await gen.__anext__()).split("data: ")[1])
        nxt = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0.01)
        assert not nxt.done()                        # nothing happens while paused
        pb.play()
        second = json.loads((await asyncio.wait_for(nxt, 1)).split("data: ")[1])
        await gen.aclose()
        return first, second, pb._subscribers
    first, second, subs = asyncio.run(run())
    assert not first["playing"] and second["playing"] and not subs


def feed(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/buildings":
        return httpx.Response(200, json={"buildings": [], "window": {"first": FIRST, "replay_start": REPLAY, "last": LAST}})
    return httpx.Response(404)


def client(handler=feed):
    return TestClient(create_app("http://feed", transport=httpx.MockTransport(handler)))


def test_http_controls_share_one_clock():
    c = client()
    assert c.get("/api/playback").json()["playing"] is False
    assert c.post("/api/playback/speed", json={"speed": 6}).json()["speed"] == 6
    assert c.post("/api/playback/play").json()["playing"] is True
    assert c.get("/api/playback").json()["playing"] is True
    assert c.post("/api/playback/pause").json()["playing"] is False
    assert c.post("/api/playback/restart").json()["position"] == FIRST


def test_http_rejects_bad_input():
    c = client()
    assert c.post("/api/playback/speed", json={"speed": 0}).status_code == 422
    assert c.post("/api/playback/speed", json={}).status_code == 422
    assert c.post("/api/playback/rewind").status_code == 404


def test_playback_needs_the_feed():
    def down(request):
        raise httpx.ConnectError("refused")
    assert client(down).get("/api/playback").status_code == 502


def test_bms_page_is_served():
    r = client().get("/bms/")
    assert r.status_code == 200 and "Heat Control" in r.text
