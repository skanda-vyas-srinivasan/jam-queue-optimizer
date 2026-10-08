from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import threading
from http.server import ThreadingHTTPServer

import pytest


@pytest.fixture
def server():
    from music_queue.debug_panel import DebugPanelApp, DebugPanelHandler
    from tests.test_artifacts import catalog

    app = DebugPanelApp(catalog())
    handler = type("Handler", (DebugPanelHandler,), {"app": app})
    http_server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    yield http_server.server_port, app
    http_server.shutdown()
    http_server.server_close()
    thread.join()
