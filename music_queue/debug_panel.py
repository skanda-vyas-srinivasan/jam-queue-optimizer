"""Bounded loopback-only research UI; not a shared production service."""

from __future__ import annotations

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlparse
import uuid

import plotly.express as px
from plotly.offline import get_plotlyjs

from .catalog import load_catalog
from .plotting import build_embedding_frame_for_space
from .preferences import parse_request
from .queueing import generate_queue
from .session import SessionState

DEBUG_PANEL_DIR = Path(__file__).resolve().parent / "debug_panel"
MAX_BODY_BYTES = 65536


@dataclass
class DebugPanelApp:
    catalog: object
    embedding_cache: dict = field(default_factory=dict)
    sessions: dict = field(default_factory=dict)
    simulation_slot: threading.Semaphore = field(
        default_factory=lambda: threading.Semaphore(1)
    )
    session_lock: threading.Lock = field(default_factory=threading.Lock)

    def catalog_payload(self):
        return {
            "songs": [
                {
                    "track_id": t.id,
                    "song": t.title,
                    "folder": t.folder,
                    "duration": t.duration,
                    "artist": t.artist,
                    "recording_family": t.recording_family,
                }
                for t in self.catalog.tracks
            ],
            "count": len(self.catalog),
            "model_hash": self.catalog.model_hash,
        }

    def sample_room_payload(self):
        n = len(self.catalog)
        groups = (
            (0, 1, 2),
            (min(10, n - 1), min(11, n - 1), min(12, n - 1)),
            (min(20, n - 1), min(21, n - 1), min(22, n - 1)),
        )
        return {
            "listeners": [
                {
                    "id": f"listener_{i+1}",
                    "name": f"Listener {i+1}",
                    "liked": list(
                        dict.fromkeys(self.catalog.tracks[a].id for a in group)
                    ),
                    "accepted": [],
                    "disliked": [],
                    "blocked": [],
                }
                for i, group in enumerate(groups)
            ]
        }

    def embedding_figure(self, space="normalized"):
        if space not in {"raw", "normalized"}:
            raise ValueError("Unknown embedding space")
        if space not in self.embedding_cache:
            df = build_embedding_frame_for_space(self.catalog, space)
            df["track_id"] = [t.id for t in self.catalog.tracks]
            figure = px.scatter_3d(
                df,
                x="x",
                y="y",
                z="z",
                color="folder",
                hover_name="song",
                custom_data=["track_id"],
            )
            figure.update_traces(marker={"size": 5})
            figure.update_layout(
                template="plotly_white", margin={"l": 0, "r": 0, "t": 20, "b": 0}
            )
            self.embedding_cache[space] = json.loads(figure.to_json())
        return self.embedding_cache[space]

    def _session(self, id):
        with self.session_lock:
            if id not in self.sessions:
                raise ValueError("Unknown local session")
            return self.sessions[id]

    def create_session(self, payload):
        req = parse_request(self.catalog, {**payload, "queue_len": 1})
        with self.session_lock:
            if len(self.sessions) >= 16:
                raise ValueError(
                    "Local session resource limit reached; restart the debug process to clear sessions"
                )
            state = SessionState("session_" + uuid.uuid4().hex)
            for field_name in ("repeat_window", "artist_cooldown"):
                value = payload.get(field_name, getattr(state, field_name))
                if type(value) is not int or not 0 <= value <= 100:
                    raise ValueError(f"{field_name} must be an integer in [0,100]")
                setattr(state, field_name, value)
            state.set_membership(self.catalog, req.listeners, 0)
            self.sessions[state.id] = state
        return state.snapshot()

    def mutate_session(self, action, payload):
        state = self._session(payload.get("session_id"))
        revision = payload.get("revision")
        if action == "membership":
            req = parse_request(self.catalog, {**payload, "queue_len": 1})
            state.set_membership(self.catalog, req.listeners, revision)
        elif action == "playback":
            state.record_playback(
                self.catalog, payload.get("track_id"), payload.get("seconds"), revision
            )
        elif action == "override":
            state.override_promise(revision)
        elif action == "feedback":
            state.feedback(
                self.catalog,
                payload.get("listener_id"),
                payload.get("track_id"),
                payload.get("label"),
                revision,
            )
        else:
            raise ValueError("Unknown session action")
        return state.snapshot()

    def simulate(self, payload):
        if payload.get("session_id"):
            request = parse_request(self.catalog, payload)
            state = self._session(payload["session_id"])
            result = state.replan(self.catalog, request)
            session = state.snapshot()
        else:
            result = generate_queue(self.catalog, payload)
            session = None
        response = result.to_dict()
        tracks = {t.id: t for t in self.catalog.tracks}
        response["queue_rows"] = [
            {
                "slot": i + 1,
                "track_id": id,
                "song": tracks[id].title,
                "folder": tracks[id].folder,
                "duration": tracks[id].duration,
            }
            for i, id in enumerate(result.queue)
        ]
        policy = result.provenance.get("policy", {})
        model = policy.get("transition_model", "pooled")
        response["transition_rows"] = [
            {
                "from_song": tracks[a].title,
                "to_song": tracks[b].title,
                "transition_model": model,
                "selected_transition_value": self.catalog.transition_score(a, b, model),
                "weighted_edge": policy.get("transition_weight", 0.25)
                * self.catalog.transition_score(a, b, model)
                - policy.get("same_folder_penalty", 0.0)
                * (tracks[a].folder == tracks[b].folder),
                "evidence": "Unvalidated diagnostic signal; not listener-rated quality",
            }
            for a, b in zip(result.queue, result.queue[1:])
        ]
        response["session"] = session
        # Full logs are included only on explicit request; phase status remains visible.
        if not payload.get("include_logs", False):
            response["solver"].pop("logs", None)
        return response


class DebugPanelHandler(BaseHTTPRequestHandler):
    app: DebugPanelApp

    def setup(self):
        super().setup()
        self.connection.settimeout(10.0)

    def _send(self, body, content_type, status=200):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status=200):
        self._send(
            json.dumps(payload, allow_nan=False),
            "application/json; charset=utf-8",
            status,
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            files = {
                "/": ("index.html", "text/html"),
                "/index.html": ("index.html", "text/html"),
                "/app.js": ("app.js", "application/javascript"),
                "/styles.css": ("styles.css", "text/css"),
            }
            if parsed.path in files:
                file, mime = files[parsed.path]
                return self._send(
                    (DEBUG_PANEL_DIR / file).read_bytes(), mime + "; charset=utf-8"
                )
            if parsed.path == "/plotly.min.js":
                return self._send(get_plotlyjs(), "application/javascript")
            if parsed.path == "/api/catalog":
                return self._json(self.app.catalog_payload())
            if parsed.path == "/api/sample-room":
                return self._json(self.app.sample_room_payload())
            params = parse_qs(parsed.query)
            if parsed.path == "/api/embedding":
                return self._json(
                    self.app.embedding_figure(params.get("space", ["normalized"])[0])
                )
            if parsed.path == "/api/song-details":
                song = params.get("song", [None])[0]
                if not song:
                    raise ValueError("Missing song parameter")
                neighbors = int(params.get("neighbors", [8])[0])
                if not 0 <= neighbors <= 100:
                    raise ValueError("Neighbor count must be in [0,100]")
                return self._json(
                    {
                        "track_id": self.app.catalog.track_id(song),
                        "neighbors": self.app.catalog.nearest_neighbors(
                            song, neighbors
                        ).to_dict("records"),
                    }
                )
            if parsed.path == "/api/session":
                return self._json(
                    self.app._session(params.get("id", [None])[0]).snapshot()
                )
            return self._json({"error": "Unknown path"}, 404)
        except (ValueError, KeyError, TypeError) as exc:
            return self._json({"error": str(exc)}, 400)

    def do_POST(self):
        path = urlparse(self.path).path
        # Browser-origin writes are local same-origin only. No CORS bridge to
        # an arbitrary website and no remote sharing of this research server.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if urlparse("http://" + host).hostname not in {"127.0.0.1", "localhost"}:
            return self._json({"error": "Use the loopback hostname"}, 403)
        if origin and origin not in {f"http://{host}", f"https://{host}"}:
            return self._json({"error": "Cross-origin writes are not allowed"}, 403)
        acquired = False
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Use a bounded Content-Length request")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0:
                raise ValueError("Invalid content length")
            if length > MAX_BODY_BYTES:
                return self._json({"error": "Request exceeds 64 KiB"}, 413)
            raw = self.rfile.read(length)
            payload = json.loads(
                raw or b"{}",
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError("Nonfinite JSON number")
                ),
            )
            if not isinstance(payload, dict):
                raise ValueError("Request must be an object")
            if path == "/api/simulate":
                acquired = self.app.simulation_slot.acquire(blocking=False)
                if not acquired:
                    return self._json({"error": "Another simulation is running"}, 429)
                return self._json(self.app.simulate(payload))
            if path == "/api/session/create":
                return self._json(self.app.create_session(payload))
            if path.startswith("/api/session/"):
                return self._json(
                    self.app.mutate_session(path.rsplit("/", 1)[1], payload)
                )
            return self._json({"error": "Unknown path"}, 404)
        except (ValueError, KeyError, TypeError, TimeoutError) as exc:
            return self._json({"error": str(exc)}, 400)
        finally:
            if acquired:
                self.app.simulation_slot.release()

    def log_message(self, *args):
        pass


def serve_debug_panel(host="127.0.0.1", port=8765, artifact_dir=None):
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError(
            "The debug panel is loopback-only; production sharing is a separate release gate"
        )
    catalog = load_catalog() if artifact_dir is None else load_catalog(artifact_dir)
    app = DebugPanelApp(catalog)
    handler = type("BoundDebugPanelHandler", (DebugPanelHandler,), {"app": app})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Debug panel running at http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
