from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import threading

import pytest

from music_queue.debug_panel import DebugPanelApp, DebugPanelHandler, serve_debug_panel
from tests.test_artifacts import catalog


@pytest.fixture
def server():
    app = DebugPanelApp(catalog())
    handler = type("Handler", (DebugPanelHandler,), {"app": app})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port, app
    server.shutdown()
    server.server_close()
    thread.join()


def request(server, method, path, payload=None, headers=None):
    port, _ = server
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    body = json.dumps(payload) if payload is not None else None
    connection.request(
        method, path, body, headers or {"Content-Type": "application/json"}
    )
    result = connection.getresponse()
    data = result.read()
    status = result.status
    connection.close()
    return status, (
        json.loads(data)
        if result.getheader("Content-Type", "").startswith("application/json")
        else data
    )


def test_http_simulation_uses_structured_status_and_stable_ids(server):
    status, c = request(server, "GET", "/api/catalog")
    assert status == 200 and c["count"] == 3 and c["songs"][0]["track_id"] == "t0"
    p = {
        "listeners": [
            {"id": "a", "name": "same", "liked": ["t0"]},
            {"id": "b", "name": "same", "liked": ["t2"]},
        ],
        "queue_len": 2,
        "method": "dp",
    }
    status, result = request(server, "POST", "/api/simulate", p)
    assert status == 200 and result["valid_incumbent"]
    assert set(result["per_listener"]) == {"a", "b"} and len(result["queue_rows"]) == 2
    p["listeners"][1]["liked"] = []
    assert request(server, "POST", "/api/simulate", p)[1]["status"] == "INVALID_REQUEST"


def test_http_bad_requests_get_errors_and_bounded_concurrency(server):
    assert request(server, "GET", "/api/embedding?space=invalid")[0] == 400
    assert request(server, "GET", "/api/song-details?song=unknown")[0] == 400
    assert request(server, "POST", "/api/simulate", [])[0] == 400
    assert request(server, "POST", "/api/simulate", {"x": "a" * 70000})[0] == 413
    assert (
        request(
            server,
            "POST",
            "/api/simulate",
            {},
            headers={"Origin": "http://unrelated.example"},
        )[0]
        == 403
    )
    server[1].simulation_slot.acquire()
    try:
        assert request(server, "POST", "/api/simulate", {})[0] == 429
    finally:
        server[1].simulation_slot.release()
    with pytest.raises(ValueError, match="loopback"):
        serve_debug_panel(host="0.0.0.0")


def test_local_session_api_revision_and_confirmed_playback(server):
    p = {
        "listeners": [{"id": "a", "name": "A", "liked": ["t0", "t1", "t2"]}],
        "queue_len": 2,
        "method": "dp",
    }
    status, session = request(server, "POST", "/api/session/create", p)
    assert status == 200
    p.update(session_id=session["id"], revision=session["revision"])
    result = request(server, "POST", "/api/simulate", p)[1]
    assert result["session"]["histories"]["a"]["played_seconds"] == 0
    session = result["session"]
    playback = {
        "session_id": session["id"],
        "revision": session["revision"],
        "track_id": session["promised_next"],
        "seconds": 30,
    }
    status, played = request(server, "POST", "/api/session/playback", playback)
    assert status == 200 and played["histories"]["a"]["accepted_seconds"] == 30
    assert request(server, "POST", "/api/session/playback", playback)[0] == 400
