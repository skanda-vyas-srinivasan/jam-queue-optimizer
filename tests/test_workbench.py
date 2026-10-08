from dataclasses import replace
from http.client import HTTPConnection
import json

import numpy as np
import pytest

from music_queue import workbench
from tests.test_artifacts import catalog

pytest_plugins = ["tests.test_debug_panel"]


def call(server, path, body):
    connection = HTTPConnection("127.0.0.1", server[0], timeout=10)
    connection.request(
        "POST", path, json.dumps(body), {"Content-Type": "application/json"}
    )
    response = connection.getresponse()
    data = json.loads(response.read())
    connection.close()
    return response.status, data


def test_clusters_are_complete_repeatable_and_do_not_modify_features():
    c = catalog()
    before = c.normalized_embeddings.copy()
    a = workbench.explore(c, {"clusters": 2, "family": "chroma", "dimensions": 3})
    assert a == workbench.explore(
        c, {"clusters": 2, "family": "chroma", "dimensions": 3}
    )
    assert sorted(t for g in a["groups"] for t in g["members"]) == sorted(
        t.id for t in c.tracks
    )
    assert all(len(p["coordinates"]) == 3 for p in a["points"])
    assert np.array_equal(before, c.normalized_embeddings)
    zero = catalog(np.zeros((1, 118)))
    assert workbench.explore(zero, {})["points"][0]["coordinates"] == [0, 0]
    with pytest.raises(ValueError):
        workbench.explore(c, {"clusters": True})


def test_retrieval_uses_frozen_geometry_and_deduplicates_aliases():
    c = catalog()
    a = workbench.retrieve(c, {"seeds": ["t0", "s0", "t0"], "limit": 3})
    assert a == workbench.retrieve(c, {"seeds": ["t0"], "limit": 3})
    assert "t0" not in {r["track_id"] for r in a["rows"]}
    assert a["rows"][0]["score"] == pytest.approx(
        c.nearest_neighbors("t0", 2).iloc[0].score
    )
    assert "not acceptance" in a["evidence"]


def test_prepared_ranking_and_sequence_share_exact_instance(server):
    request = {
        "listeners": [{"id": "u", "name": "Alex", "liked": ["t0", "t2"]}],
        "queue_len": 2,
        "candidate_limit": 2,
        "method": "dp",
    }
    status, prepared = call(server, "/api/pipeline", request)
    assert status == 200 and prepared["snapshot_token"]
    assert len(prepared["provenance"]["ranked_rows"]) == 3
    original = prepared["instance_hash"]
    # A second request cannot mutate the first frozen snapshot.
    call(server, "/api/pipeline", {**request, "policy": {"transition_weight": 0}})
    status, result = call(
        server,
        "/api/sequence",
        {"snapshot_token": prepared["snapshot_token"], "method": "dp"},
    )
    assert (
        status == 200
        and result["valid_incumbent"]
        and result["instance_hash"] == original
    )
    assert result["candidate_hash"] == prepared["candidate_scope_hash"]
    status, manual = call(
        server,
        "/api/order",
        {
            "snapshot_token": prepared["snapshot_token"],
            "queue": list(reversed(result["queue"])),
        },
    )
    assert status == 200 and manual["valid_incumbent"] and not manual["proven_optimal"]
    assert manual["status"] == "FEASIBLE_NOT_PROVEN"
    assert (
        call(
            server,
            "/api/order",
            {"snapshot_token": prepared["snapshot_token"], "queue": ["t0", "t0"]},
        )[0]
        == 400
    )
    assert (
        call(
            server,
            "/api/sequence",
            {"snapshot_token": prepared["snapshot_token"], "policy": {}},
        )[0]
        == 400
    )
    assert call(server, "/api/sequence", {"snapshot_token": "expired"})[0] == 400


def test_audio_ranges_head_missing_and_path_containment(server, tmp_path):
    root = tmp_path / "audio"
    root.mkdir()
    data = bytes(range(256)) * 4
    (root / "test.mp3").write_bytes(data)
    _, app = server
    app.song_root = root
    app.catalog.tracks = (
        replace(app.catalog.tracks[0], source="test.mp3"),
        *app.catalog.tracks[1:],
    )

    def read(method="GET", headers=None):
        conn = HTTPConnection("127.0.0.1", server[0], timeout=5)
        conn.request(method, "/api/audio?track_id=t0", headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        values = response.status, dict(response.getheaders()), body
        conn.close()
        return values

    assert read()[2] == data
    status, headers, body = read(headers={"Range": "bytes=8-31"})
    assert status == 206 and body == data[8:32]
    assert headers["Content-Range"] == "bytes 8-31/1024"
    assert read(headers={"Range": "bytes=-10"})[2] == data[-10:]
    assert read("HEAD")[2] == b""
    assert read(headers={"Range": "bytes=99999-"})[0] == 416
    assert read(headers={"Range": "bytes=0-2,4-6"})[0] == 416
    assert read(headers={"Origin": "https://unrelated.example"})[0] == 403
    app.catalog.tracks = (
        replace(app.catalog.tracks[0], source="../private.mp3"),
        *app.catalog.tracks[1:],
    )
    (tmp_path / "private.mp3").write_bytes(b"private")
    assert read()[0] == 400
    (root / "escape.mp3").symlink_to(tmp_path / "private.mp3")
    app.catalog.tracks = (
        replace(app.catalog.tracks[0], source="escape.mp3"),
        *app.catalog.tracks[1:],
    )
    assert read()[0] == 400
    app.catalog.tracks = (
        replace(app.catalog.tracks[0], source="missing.mp3"),
        *app.catalog.tracks[1:],
    )
    assert read()[0] == 404
