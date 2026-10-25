import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.status import assess, baseline, summarize

TZ = timezone(timedelta(hours=1))
NOW = datetime(2022, 10, 20, 12, tzinfo=TZ)        # a Thursday


def hist(fn, days=14, now=NOW):
    """hour -> (Wh, Tout) for `days` days up to now; fn(t) gives Wh."""
    return {t: (fn(t), 5.0) for t in (now - timedelta(hours=i) for i in range(days * 24))}


def normal(t):
    return 100_000.0 + 1000 * t.hour


def test_baseline_is_the_median_of_the_same_hour_and_kind_of_day():
    h = hist(normal)
    assert baseline(NOW, 5.0, h) == normal(NOW)
    assert baseline(NOW, 5.0, {}) is None                       # too little history


def test_baseline_moves_along_the_temperature_slope():
    h = {t: (normal(t) - 1000 * (i // 24 % 8), 5.0 + (i // 24 % 8)) for i, t in enumerate(hist(normal))}   # warmer -> less heat
    colder, warmer = baseline(NOW, 0.0, h), baseline(NOW, 10.0, h)
    assert colder > warmer


def test_normal_building_is_ok():
    r = assess(NOW, hist(normal), {}, {})
    assert r["status"] == "ok" and r["basis"] == "baseline" and r["reasons"] == []


def test_overuse_against_the_baseline_alerts():
    h = hist(lambda t: normal(t) * (3.0 if t > NOW - timedelta(hours=6) else 1.0))
    r = assess(NOW, h, {}, {})
    assert r["status"] == "alert" and r["reasons"][0]["code"] == "excess_6h" and r["excess_6h"] > 1.5


def test_forecast_is_used_when_available_and_wins_over_the_baseline():
    h = hist(normal)
    past = {t: normal(t) * 0.5 for t in h if t > NOW - timedelta(hours=24)}      # the model expected much less
    r = assess(NOW, h, past, {})
    assert r["basis"] == "forecast" and r["status"] == "alert"


def test_the_forecast_is_trusted_more_than_the_baseline():
    h = hist(normal)
    last6 = lambda t: t > NOW - timedelta(hours=6)
    over = {t: v * 0.75 for t, (v, _) in h.items() if t > NOW - timedelta(hours=24)}       # actual is 33 % above this
    assert assess(NOW, h, over, {})["status"] == "watch"                                    # forecast basis: 25 % / 60 %
    h2 = hist(lambda t: normal(t) * (1.33 if last6(t) else 1.0))
    assert assess(NOW, h2, {}, {})["status"] == "ok"                                        # baseline basis: needs 80 %


def test_small_excess_next_to_the_highest_load_is_ignored():
    h = hist(lambda t: 100_000.0 if t.hour == 8 else 1_000.0)       # one big peak hour, otherwise tiny
    h[NOW] = (3_000.0, 5.0)                                         # +200 % but only 2 kW
    assert assess(NOW, h, {}, {})["status"] == "ok"


def test_high_forecast_load_is_flagged_as_load_soon():
    h = hist(normal)
    peak = max(v for v, _ in h.values())
    r = assess(NOW, h, {}, {1: peak * 0.9, 6: peak * 1.2})
    assert r["status"] == "alert" and r["reasons"][0]["code"] == "load_soon" and "6 h" in r["reasons"][0]["message"]
    assert assess(NOW, h, {}, {1: peak * 0.9})["status"] == "ok"


def test_missing_reading_and_stuck_meter_are_no_data_not_alerts():
    h = hist(normal)
    del h[NOW]
    assert assess(NOW, h, {}, {})["status"] == "no_data"
    stuck = hist(lambda t: 5000.0 if t > NOW - timedelta(hours=8) else normal(t))
    r = assess(NOW, stuck, {}, {})
    assert r["status"] == "no_data" and r["reasons"][0]["code"] == "stuck"


def test_not_enough_history_says_so_and_stays_ok():
    r = assess(NOW, hist(normal, days=1), {}, {})
    assert r["status"] == "ok" and r["reasons"][0]["code"] == "no_baseline"


def test_summary_counts():
    assert summarize([{"status": "ok"}, {"status": "alert"}, {"status": "ok"}]) == {"alert": 1, "watch": 0, "ok": 2, "no_data": 0}


# ---------- the endpoint ----------

START = datetime(2022, 9, 24, tzinfo=TZ)


def feed(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/buildings":
        return httpx.Response(200, json={"window": {"first": START.isoformat(), "replay_start": "2022-10-01T00:00:00+01:00",
                                                    "last": "2023-03-31T00:00:00+01:00"}})
    if request.url.path == "/readings":
        until = datetime.fromisoformat(request.url.params["until"])
        rows = []
        for t in (START + timedelta(hours=i) for i in range(24 * 30)):
            if t > until:
                break
            for b in (1, 2):
                wh = normal(t) * (3.0 if b == 2 and t > until - timedelta(hours=6) else 1.0)
                rows.append({"timestamp": t.isoformat(), "building_id": b, "HtTot": wh, "Tout": 5.0})
        return httpx.Response(200, json=rows)
    return httpx.Response(404)


def app(forecast_handler):
    c = TestClient(create_app("http://feed", transport=httpx.MockTransport(feed), forecast_url="http://fc",
                              forecast_transport=httpx.MockTransport(forecast_handler)))
    return c


def fc_down(request):
    raise httpx.ConnectError("refused")


def test_status_before_the_replay_starts():
    r = app(fc_down).get("/api/status").json()
    assert r["as_of"] is None and r["buildings"] == []


def run_clock(c, seconds=0.5):
    """Let the shared clock run fast for a moment (720 h per real second), then stop it."""
    c.post("/api/playback/speed", json={"speed": 720})
    c.post("/api/playback/play")
    time.sleep(seconds)
    c.post("/api/playback/pause")


def test_status_ranks_the_bad_building_first_and_falls_back_without_the_forecast():
    c = app(fc_down)
    run_clock(c)
    r = c.get("/api/status").json()
    assert [b["building_id"] for b in r["buildings"]] == [2, 1]
    assert [b["status"] for b in r["buildings"]] == ["alert", "ok"]
    assert r["buildings"][0]["basis"] == "baseline" and r["summary"] == {"alert": 1, "watch": 0, "ok": 1, "no_data": 0}


def test_status_uses_the_forecast_service_when_it_answers():
    def fc(request: httpx.Request) -> httpx.Response:
        hs = request.url.params["horizons"].split(",")
        first = datetime.fromisoformat(request.url.params["from"])
        last = datetime.fromisoformat(request.url.params["until"])
        n = int((last - first).total_seconds() // 3600) + 1
        series = {h: [{"target_time": (first + timedelta(hours=i + int(h))).isoformat(), "wh": 1.0} for i in range(n)] for h in hs}
        return httpx.Response(200, json={"series": series})
    c = app(fc)
    run_clock(c)
    r = c.get("/api/status").json()
    assert {b["basis"] for b in r["buildings"]} == {"forecast"}
    assert all(b["status"] == "alert" for b in r["buildings"])      # the fake model says 1 Wh: both use far more
