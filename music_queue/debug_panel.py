from __future__ import annotations

from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
import plotly.express as px
from plotly.offline import get_plotlyjs

from .catalog import SongCatalog, load_catalog
from .plotting import build_embedding_frame_for_space
from .queueing import (
    build_queue,
    rank_room_candidates,
    score_queue,
    select_candidate_shortlist,
    select_candidate_shortlist_with_details,
    user_representation_sets,
)

DEBUG_PANEL_DIR = Path(__file__).resolve().parent / "debug_panel"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(inner) for inner in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if pd.isna(value):
        return None
    return value


def _frame_records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is not None:
        df = df.head(limit)
    rows = df.to_dict(orient="records")
    return [_json_safe(row) for row in rows]


@dataclass
class DebugPanelApp:
    catalog: SongCatalog
    embedding_cache: dict[str, dict[str, Any]] = field(default_factory=dict)

    def catalog_payload(self) -> dict[str, Any]:
        songs = [
            {"song": str(song), "folder": str(folder)}
            for song, folder in zip(self.catalog.names, self.catalog.folders)
        ]
        folders: dict[str, list[str]] = {}
        for row in songs:
            folders.setdefault(row["folder"], []).append(row["song"])
        for folder_songs in folders.values():
            folder_songs.sort()
        return {
            "songs": songs,
            "folders": folders,
            "count": len(songs),
        }

    def sample_room_payload(self) -> dict[str, list[str]]:
        song_names = self.catalog.names.tolist()
        if len(song_names) < 23:
            raise ValueError("Catalog is too small to build the sample room.")
        return {
            "user_A": [song_names[0], song_names[1], song_names[2]],
            "user_B": [song_names[10], song_names[11], song_names[12]],
            "user_C": [song_names[20], song_names[21], song_names[22]],
        }

    def embedding_figure(self, space: str = "normalized") -> dict[str, Any]:
        if space not in self.embedding_cache:
            df = build_embedding_frame_for_space(self.catalog, space=space)
            fig = px.scatter_3d(
                df,
                x="x",
                y="y",
                z="z",
                color="folder",
                hover_name="song",
                title=f"Song Embedding Space ({space})",
            )
            fig.update_traces(marker={"size": 5, "opacity": 0.9})
            fig.update_layout(
                template="plotly_white",
                paper_bgcolor="#f7f4ec",
                plot_bgcolor="#f7f4ec",
                margin={"l": 0, "r": 0, "t": 48, "b": 0},
                legend={"orientation": "h", "y": -0.1},
            )
            self.embedding_cache[space] = json.loads(fig.to_json())
        return self.embedding_cache[space]

    def song_details_payload(self, song_name: str, neighbors: int = 8) -> dict[str, Any]:
        resolved = self.catalog.resolve_song_name(song_name)
        return {
            "song": resolved,
            "folder": self.catalog.get_folder(resolved),
            "neighbors": _frame_records(self.catalog.nearest_neighbors(resolved, k=neighbors)),
        }

    def _user_seed_neighbors(
        self,
        room: dict[str, list[str]],
        neighbors_per_seed: int = 5,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for user, liked_songs in room.items():
            for liked_song in liked_songs:
                resolved = self.catalog.resolve_song_name(liked_song)
                neighbors = self.catalog.nearest_neighbors(resolved, k=neighbors_per_seed)
                rows.append(
                    {
                        "user": user,
                        "seed_song": resolved,
                        "seed_folder": self.catalog.get_folder(resolved),
                        "neighbors": _frame_records(neighbors),
                    }
                )
        return rows

    def _queue_affinity_rows(
        self,
        queue: list[str],
        shortlist_df: pd.DataFrame,
        room: dict[str, list[str]],
        user_representation_top_k: int | None,
    ) -> list[dict[str, Any]]:
        shortlist_scores = shortlist_df.set_index("song")
        representation_sets = user_representation_sets(shortlist_df.reset_index(drop=True), user_representation_top_k)
        shortlist_index_map = {
            row["song"]: idx for idx, row in shortlist_df.reset_index(drop=True)[["song"]].to_dict("index").items()
        }
        rows: list[dict[str, Any]] = []
        for song in queue:
            row: dict[str, Any] = {
                "song": song,
                "folder": self.catalog.get_folder(song),
                "room_score": (
                    float(shortlist_scores.loc[song, "room_score"])
                    if song in shortlist_scores.index
                    else None
                ),
            }
            shortlist_idx = shortlist_index_map.get(song)
            for user in room:
                user_score_value = (
                    float(shortlist_scores.loc[song, user])
                    if song in shortlist_scores.index and user in shortlist_scores.columns
                    else None
                )
                row[user] = user_score_value
                row[f"{user}_rep"] = (
                    shortlist_idx in representation_sets.get(user, set())
                    if shortlist_idx is not None and user_representation_top_k is not None
                    else False
                )
            rows.append(row)
        return rows

    def _transition_rows(self, queue: list[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for idx in range(1, len(queue)):
            prev_song = queue[idx - 1]
            next_song = queue[idx]
            prev_idx = self.catalog.song_index(prev_song)
            next_idx = self.catalog.song_index(next_song)
            rows.append(
                {
                    "from_song": prev_song,
                    "to_song": next_song,
                    "from_folder": self.catalog.get_folder(prev_song),
                    "to_folder": self.catalog.get_folder(next_song),
                    "segment_transition": float(
                        self.catalog.segment_transition_similarity[prev_idx, next_idx]
                    ),
                    "harmonic_transition": float(
                        self.catalog.harmonic_transition_similarity[prev_idx, next_idx]
                    ),
                    "combined_transition": float(
                        self.catalog.transition_similarity[prev_idx, next_idx]
                    ),
                }
            )
        return rows

    def _user_summary_rows(
        self,
        room: dict[str, list[str]],
        ranked_df: pd.DataFrame,
        queue_affinity_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        affinity_df = pd.DataFrame(queue_affinity_rows)
        for user, liked_songs in room.items():
            top_candidates = []
            if user in ranked_df.columns:
                top_candidates = (
                    ranked_df[["song", "folder", user]]
                    .sort_values(user, ascending=False)
                    .head(5)
                    .rename(columns={user: "user_score"})
                    .to_dict(orient="records")
                )
            covered_queue_songs = []
            if not affinity_df.empty and user in affinity_df.columns:
                covered_queue_songs = (
                    affinity_df[["song", "folder", user]]
                    .sort_values(user, ascending=False)
                    .head(3)
                    .rename(columns={user: "user_score"})
                    .to_dict(orient="records")
                )
            rows.append(
                {
                    "user": user,
                    "liked_songs": liked_songs,
                    "top_candidates": _json_safe(top_candidates),
                    "queue_matches": _json_safe(covered_queue_songs),
                }
            )
        return rows

    def simulate(self, payload: dict[str, Any]) -> dict[str, Any]:
        room = payload.get("room", {})
        queue_len = int(payload.get("queue_len", 5))
        candidate_pool_size = int(payload.get("candidate_pool_size", 50))
        candidate_limit = int(payload.get("candidate_limit", 10))
        method = str(payload.get("method", "ip"))
        transition_weight = float(payload.get("transition_weight", 0.25))
        relative_gap = payload.get("relative_gap")
        relative_gap = None if relative_gap in ("", None) else float(relative_gap)
        same_folder_penalty = payload.get("same_folder_penalty")
        same_folder_penalty = (
            None if same_folder_penalty in ("", None) else float(same_folder_penalty)
        )
        max_songs_per_folder = payload.get("max_songs_per_folder")
        max_songs_per_folder = (
            None if max_songs_per_folder in ("", None) else int(max_songs_per_folder)
        )
        user_representation_top_k = payload.get("user_representation_top_k", 3)
        user_representation_top_k = (
            None
            if user_representation_top_k in ("", None) or int(user_representation_top_k) <= 0
            else int(user_representation_top_k)
        )
        preserve_user_fraction = float(payload.get("preserve_user_fraction", 0.30))
        max_preserved_per_user = int(payload.get("max_preserved_per_user", 2))
        time_limit = int(payload.get("time_limit", 10))

        retrieval_df, ranked_df = rank_room_candidates(
            self.catalog,
            room,
            candidate_pool_size=candidate_pool_size,
        )
        shortlist_df, shortlist_reasons = select_candidate_shortlist_with_details(
            ranked_df,
            shortlist_size=candidate_limit,
            preserve_user_fraction=preserve_user_fraction,
            max_preserved_per_user=max_preserved_per_user,
        )
        queue = build_queue(
            catalog=self.catalog,
            ranked_df=ranked_df,
            queue_len=queue_len,
            candidate_limit=candidate_limit,
            method=method,
            transition_weight=transition_weight,
            same_folder_penalty=same_folder_penalty,
            max_songs_per_folder=max_songs_per_folder,
            user_representation_top_k=user_representation_top_k,
            preserve_user_fraction=preserve_user_fraction,
            max_preserved_per_user=max_preserved_per_user,
            time_limit=time_limit,
            relative_gap=relative_gap,
        )

        room_score_map = dict(zip(shortlist_df["song"], shortlist_df["room_score"]))
        queue_score = score_queue(
            self.catalog,
            queue,
            room_score_map=room_score_map,
            transition_weight=transition_weight,
            same_folder_penalty=0.0 if same_folder_penalty is None else same_folder_penalty,
        )

        queue_rows: list[dict[str, Any]] = []
        for slot, song in enumerate(queue, start=1):
            prev_song = queue[slot - 2] if slot > 1 else None
            queue_rows.append(
                {
                    "slot": slot,
                    "song": song,
                    "folder": self.catalog.get_folder(song),
                    "room_score": room_score_map.get(song),
                    "transition_from_prev": (
                        None if prev_song is None else self.catalog.transition_score(prev_song, song)
                    ),
                    "shortlist_reason": shortlist_reasons.get(song, []),
                }
            )

        shortlist_debug_df = shortlist_df.copy()
        shortlist_debug_df["selection_reason"] = shortlist_debug_df["song"].map(
            lambda song: shortlist_reasons.get(song, ["global_rank"])
        )
        queue_affinity_rows = self._queue_affinity_rows(
            queue=queue,
            shortlist_df=shortlist_df,
            room=room,
            user_representation_top_k=user_representation_top_k,
        )
        transition_rows = self._transition_rows(queue)
        user_summary_rows = self._user_summary_rows(
            room=room,
            ranked_df=ranked_df,
            queue_affinity_rows=queue_affinity_rows,
        )

        return {
            "resolved_room": room,
            "queue": queue,
            "queue_rows": _frame_records(pd.DataFrame(queue_rows)),
            "queue_score": queue_score,
            "queue_affinity_rows": _frame_records(pd.DataFrame(queue_affinity_rows)),
            "transition_rows": _frame_records(pd.DataFrame(transition_rows)),
            "user_summary_rows": _json_safe(user_summary_rows),
            "seed_neighbor_rows": self._user_seed_neighbors(room),
            "retrieval_rows": _frame_records(
                retrieval_df[
                    ["song", "folder", "retrieval_score", "user_coverage", "users_retrieved"]
                ],
                limit=25,
            ),
            "ranked_rows": _frame_records(ranked_df, limit=25),
            "shortlist_rows": _frame_records(shortlist_debug_df),
            "meta": {
                "retrieved_candidates": len(retrieval_df),
                "ranked_candidates": len(ranked_df),
                "shortlist_size": len(shortlist_df),
                "queue_length": len(queue),
                "method": method,
                "candidate_pool_size": candidate_pool_size,
                "candidate_limit": candidate_limit,
            },
        }


class DebugPanelHandler(BaseHTTPRequestHandler):
    app: DebugPanelApp

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(_json_safe(payload)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(
        self,
        body: str,
        content_type: str = "text/plain; charset=utf-8",
        status: int = HTTPStatus.OK,
    ) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            return self._send_file(DEBUG_PANEL_DIR / "index.html", "text/html; charset=utf-8")
        if parsed.path == "/app.js":
            return self._send_file(
                DEBUG_PANEL_DIR / "app.js",
                "application/javascript; charset=utf-8",
            )
        if parsed.path == "/styles.css":
            return self._send_file(DEBUG_PANEL_DIR / "styles.css", "text/css; charset=utf-8")
        if parsed.path == "/plotly.min.js":
            return self._send_text(
                get_plotlyjs(),
                content_type="application/javascript; charset=utf-8",
            )
        if parsed.path == "/api/catalog":
            return self._send_json(self.app.catalog_payload())
        if parsed.path == "/api/sample-room":
            return self._send_json({"room": self.app.sample_room_payload()})
        if parsed.path == "/api/embedding":
            params = parse_qs(parsed.query)
            space = params.get("space", ["normalized"])[0]
            return self._send_json(self.app.embedding_figure(space=space))
        if parsed.path == "/api/song-details":
            params = parse_qs(parsed.query)
            song = params.get("song", [None])[0]
            if not song:
                return self._send_json({"error": "Missing song parameter"}, status=400)
            neighbors = int(params.get("neighbors", [8])[0])
            return self._send_json(self.app.song_details_payload(song, neighbors=neighbors))
        return self._send_json({"error": f"Unknown path: {parsed.path}"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/simulate":
            return self._send_json({"error": f"Unknown path: {parsed.path}"}, status=404)

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
            payload = json.loads(raw_body)
            result = self.app.simulate(payload)
        except Exception as exc:
            return self._send_json({"error": str(exc)}, status=400)

        return self._send_json(result)

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve_debug_panel(
    host: str = "127.0.0.1",
    port: int = 8765,
    artifact_dir: Path | str | None = None,
) -> None:
    catalog = load_catalog() if artifact_dir is None else load_catalog(Path(artifact_dir))
    app = DebugPanelApp(catalog=catalog)
    handler_cls = type(
        "BoundDebugPanelHandler",
        (DebugPanelHandler,),
        {"app": app},
    )
    server = ThreadingHTTPServer((host, port), handler_cls)
    print(f"Debug panel running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
