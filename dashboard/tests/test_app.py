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


def test_forecast_status(tmp_path):
    assert make().get("/api/forecast/status").json() == {"available": False}
    f = tmp_path / "forecasts.parquet"
    assert make(forecasts_path=str(f)).get("/api/forecast/status").json() == {"available": False}
    f.write_bytes(b"x")
    assert make(forecasts_path=str(f)).get("/api/forecast/status").json() == {"available": True}


def test_serves_page():
    r = make().get("/")
    assert r.status_code == 200 and "<title>" in r.text
