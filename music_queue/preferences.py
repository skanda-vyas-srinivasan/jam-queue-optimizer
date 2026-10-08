"""Validate membership, canonicalize evidence, and label acoustic predictions separately."""

from __future__ import annotations
from collections.abc import Mapping, Sequence
from dataclasses import replace
import math

import numpy as np

from .domain import Listener, Policy, SessionRequest, validate_policy, fingerprint


def _references(catalog, values, field):
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{field } must be an array of track IDs")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{field } contains an invalid track reference")
    return tuple(sorted({catalog.track_id(value) for value in values}))


def normalize_request(catalog, request):
    validate_policy(request.policy)
    for value, label, maximum in (
        (request.queue_len, "queue_len", 20),
        (request.candidate_limit, "candidate_limit", 30),
        (request.beam_width, "beam_width", 4096),
    ):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"{label } must be an integer from 1 to {maximum }")
    if (
        not isinstance(request.listeners, (tuple, list))
        or not 1 <= len(request.listeners) <= 8
    ):
        raise ValueError("Include 1 to 8 explicit listeners")
    listeners = []
    for listener in request.listeners:
        if (
            not isinstance(listener, Listener)
            or not isinstance(listener.id, str)
            or not listener.id.strip()
        ):
            raise ValueError("Each listener needs a stable, nonempty ID")
        if (
            not isinstance(listener.name, str)
            or not listener.name.strip()
            or len(listener.name) > 100
        ):
            raise ValueError(
                "Each listener needs a display name of at most 100 characters"
            )
        liked = _references(catalog, listener.liked, "liked")
        accepted = tuple(
            sorted(
                set(liked) | set(_references(catalog, listener.accepted, "accepted"))
            )
        )
        disliked = _references(catalog, listener.disliked, "disliked")
        blocked = _references(catalog, listener.blocked, "blocked")
        if not accepted:
            raise ValueError(
                f"Listener {listener .id } has no affirmative profile; membership was retained"
            )
        if set(accepted) & set(disliked):
            raise ValueError(
                f"Listener {listener .id } has contradictory acceptance/dislike evidence"
            )
        listeners.append(
            replace(
                listener,
                liked=liked,
                accepted=accepted,
                disliked=disliked,
                blocked=blocked,
            )
        )
    if len({listener.id for listener in listeners}) != len(listeners):
        raise ValueError("Duplicate listener IDs; duplicate display names are allowed")
    if request.method not in {
        "milp",
        "ip",
        "beam",
        "greedy",
        "dp",
        "round_robin",
        "shared_approval",
    }:
        raise ValueError("Unknown solver method")
    if (
        type(request.time_limit) not in (int, float)
        or not math.isfinite(request.time_limit)
        or not 0 < request.time_limit <= 60
    ):
        raise ValueError("time_limit must be finite and in (0, 60] seconds")
    if (
        type(request.relative_gap) not in (int, float)
        or not math.isfinite(request.relative_gap)
        or not 0 <= request.relative_gap <= 1
    ):
        raise ValueError("relative_gap must be in [0,1]")
    if type(request.revision) is not int or request.revision < 0:
        raise ValueError("Session revision must be a nonnegative integer")
    if isinstance(request.locked_prefix, (str, bytes)) or not isinstance(
        request.locked_prefix, Sequence
    ):
        raise ValueError("locked_prefix must be an array of track IDs")
    locked = tuple(catalog.track_id(t) for t in request.locked_prefix)
    if len(set(locked)) != len(locked) or len(locked) > request.queue_len:
        raise ValueError("Locked prefix repeats a track or exceeds requested length")
    return replace(
        request,
        listeners=tuple(sorted(listeners, key=lambda listener: listener.id)),
        locked_prefix=locked,
        excluded=_references(catalog, request.excluded, "excluded"),
        incumbent=_references(catalog, request.incumbent, "incumbent"),
        current_track=(
            catalog.track_id(request.current_track) if request.current_track else None
        ),
    )


def parse_request(catalog, payload):
    if not isinstance(payload, dict):
        raise ValueError("Request must be a JSON object")
    allowed = {
        "listeners",
        "room",
        "queue_len",
        "candidate_limit",
        "method",
        "policy",
        "max_songs_per_folder",
        "transition_weight",
        "same_folder_penalty",
        "time_limit",
        "relative_gap",
        "beam_width",
        "locked_prefix",
        "current_track",
        "excluded",
        "incumbent",
        "revision",
        "session_id",
        "include_logs",
        "repeat_window",
        "artist_cooldown",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError("Unknown request fields: " + ", ".join(sorted(unknown)))
    if "listeners" in payload and "room" in payload:
        raise ValueError(
            "Specify one membership representation: listeners or legacy room"
        )
    if "listeners" in payload:
        if not isinstance(payload["listeners"], list):
            raise ValueError("listeners must be an array")
        listeners = []
        for row in payload["listeners"]:
            if not isinstance(row, dict) or not {"id", "name"} <= row.keys():
                raise ValueError("Listener objects require id and name")
            listeners.append(
                Listener(
                    row["id"],
                    row["name"],
                    row.get("liked", ()),
                    row.get("accepted", ()),
                    row.get("disliked", ()),
                    row.get("blocked", ()),
                )
            )
    else:
        room = payload.get("room")
        if not isinstance(room, Mapping) or not room:
            raise ValueError("Include listeners with stable IDs")
        listeners = [
            Listener("legacy_" + fingerprint(str(name))[:16], str(name), seeds)
            for name, seeds in room.items()
        ]
    policy_values = payload.get("policy", {})
    if not isinstance(policy_values, dict):
        raise ValueError("policy must be an object")
    policy = Policy(**policy_values)
    # Legacy CLI/UI knobs are explicit overrides; defaults do not invent caps.
    overrides = {}
    for old, new in [
        ("max_songs_per_folder", "folder_cap"),
        ("transition_weight", "transition_weight"),
        ("same_folder_penalty", "same_folder_penalty"),
    ]:
        if payload.get(old) not in (None, ""):
            overrides[new] = payload[old]
    policy = replace(policy, **overrides)
    request = SessionRequest(
        tuple(listeners),
        queue_len=payload.get("queue_len", 5),
        candidate_limit=payload.get("candidate_limit", 10),
        method=payload.get("method", "milp"),
        policy=policy,
        time_limit=payload.get("time_limit", 10.0),
        relative_gap=payload.get("relative_gap") or 0.0,
        beam_width=payload.get("beam_width", 64),
        locked_prefix=payload.get("locked_prefix", ()),
        current_track=payload.get("current_track"),
        excluded=payload.get("excluded", ()),
        incumbent=payload.get("incumbent", ()),
        revision=payload.get("revision", 0),
    )
    return normalize_request(catalog, request)


def predict_affinity(catalog, listener, track_id, predictor="top_two"):
    if track_id in listener.accepted or track_id in listener.liked:
        return 1.0, "explicit_acceptance"
    if track_id in listener.disliked:
        return -1.0, "explicit_dislike"
    seeds = tuple(sorted(set(listener.liked)))
    if not seeds:
        return 0.0, "unknown_no_prediction"
    a = catalog.song_index(track_id)
    indices = [catalog.song_index(t) for t in seeds]
    scores = catalog.retrieval_similarity[a, indices]
    if predictor == "maximum":
        value = float(np.max(scores))
    elif predictor == "pockets":
        # Small baseline: connected components of seeds at cosine >= .5.
        remaining = set(indices)
        pockets = []
        while remaining:
            pocket = {min(remaining)}
            remaining -= pocket
            while True:
                added = {
                    b
                    for b in remaining
                    if any(catalog.retrieval_similarity[b, c] >= 0.5 for c in pocket)
                }
                if not added:
                    break
                pocket |= added
                remaining -= added
            pockets.append(pocket)
        value = max(
            float(np.mean(catalog.retrieval_similarity[a, list(p)])) for p in pockets
        )
    else:
        value = float(np.mean(sorted(scores, reverse=True)[:2]))
    return value, "predicted_acoustic_affinity"
