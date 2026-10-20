import httpx
from fastapi.testclient import TestClient

from dashboard.app import create_app

class Chunks(httpx.AsyncByteStream):
    """A body that can only be streamed (MockTransport would otherwise read it up front)."""
    async def __aiter__(self):
        yield SSE[:20]
        yield SSE[20:]


SSE = b'id: a\nevent: reading\ndata: {"x": 1}\n\nevent: end\ndata: {}\n\n'


def fake_feed(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/stream":
        return httpx.Response(200, stream=Chunks(), headers={"content-type": "text/event-stream",
                                                         "x-seen-last-event-id": request.headers.get("last-event-id", "")})
    if request.url.path == "/readings":
        return httpx.Response(200, json={"query": str(request.url.query, "utf-8")})
    if request.url.path == "/buildings":
        return httpx.Response(200, json={"buildings": []})
    return httpx.Response(404, json={"detail": "nope"})


def make(**kw):
    return TestClient(create_app("http://feed", transport=httpx.MockTransport(fake_feed), **kw))


def test_forwards_json_with_repeated_query_params():
    r = make().get("/api/readings", params=[("until", "2022-10-01T00:00"), ("building", "8105"), ("building", "8107")])
    assert r.status_code == 200
    q = r.json()["query"]
    assert q.count("building=") == 2 and "until=" in q


def test_forwards_stream_and_last_event_id():
    r = make().get("/api/stream", headers={"Last-Event-ID": "2022-10-01T00:00:00+01:00"})
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.content == SSE


def test_feed_errors_pass_through():
    assert make().get("/api/buildings").json() == {"buildings": []}


def test_only_feed_endpoints_are_forwarded():
    assert make().get("/api/secret").status_code == 404


def test_feed_down_gives_502():
    def down(request):
        raise httpx.ConnectError("refused")
    c = TestClient(create_app("http://feed", transport=httpx.MockTransport(down)))
    assert c.get("/api/buildings").status_code == 502


def forecast_app(handler):
    return TestClient(create_app("http://feed", transport=httpx.MockTransport(fake_feed), forecast_url="http://fc",
                                 forecast_transport=httpx.MockTransport(handler)))


def test_forecast_status_follows_the_service():
    ok = lambda request: httpx.Response(200, json={"status": "ok"})
    def down(request):
        raise httpx.ConnectError("refused")
    assert forecast_app(ok).get("/api/forecast/status").json() == {"available": True}
    assert forecast_app(down).get("/api/forecast/status").json() == {"available": False}


def test_forecast_series_is_forwarded_and_others_are_not():
    def fc(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/forecast/series"
        return httpx.Response(200, json={"q": str(request.url.query, "utf-8")})
    c = forecast_app(fc)
    r = c.get("/api/forecast/series", params={"from": "2022-10-08T00:00", "until": "2022-10-09T00:00", "horizons": "24"})
    assert r.status_code == 200 and "horizons=24" in r.json()["q"]
    assert c.get("/api/forecast/forecast").status_code == 404
    assert c.get("/api/forecast/secret").status_code == 404


def test_forecast_service_errors_pass_through_and_down_is_502():
    c = forecast_app(lambda request: httpx.Response(422, json={"detail": "bad"}))
    assert c.get("/api/forecast/series").status_code == 422
    def down(request):
        raise httpx.ConnectError("refused")
    assert forecast_app(down).get("/api/forecast/series").status_code == 502


def test_serves_page():
    r = make().get("/")
    assert r.status_code == 200 and "<title>" in r.text


def test_twin_compare_is_forwarded():
    def twin(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/compare"
        return httpx.Response(200, json={"q": str(request.url.query, "utf-8")})
    c = TestClient(create_app("http://feed", transport=httpx.MockTransport(fake_feed),
                              twin_url="http://twin", twin_transport=httpx.MockTransport(twin)))
    r = c.get("/api/twin/compare", params={"start": "2022-11-07", "days": 3})
    assert r.status_code == 200 and "days=3" in r.json()["q"]


def test_twin_down_gives_502():
    def down(request):
        raise httpx.ConnectError("refused")
    c = TestClient(create_app("http://feed", transport=httpx.MockTransport(fake_feed),
                              twin_url="http://twin", twin_transport=httpx.MockTransport(down)))
    assert c.get("/api/twin/compare").status_code == 502


def test_twin_errors_pass_through():
    def bad(request):
        return httpx.Response(422, json={"detail": "outside the window"})
    c = TestClient(create_app("http://feed", transport=httpx.MockTransport(fake_feed),
                              twin_url="http://twin", twin_transport=httpx.MockTransport(bad)))
    r = c.get("/api/twin/compare", params={"start": "2000-01-01"})
    assert r.status_code == 422 and r.json()["detail"] == "outside the window"
