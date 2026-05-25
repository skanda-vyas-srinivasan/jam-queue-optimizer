from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import inf

import numpy as np
import pandas as pd

from .catalog import SongCatalog

Room = Mapping[str, Sequence[str]]


def validate_room(catalog: SongCatalog, room: Room) -> None:
    if not room:
        raise ValueError("Room must include at least one user")

    for user, liked_songs in room.items():
        if not liked_songs:
            raise ValueError(f"User {user!r} must have at least one liked song")
        for song in liked_songs:
            if not catalog.has_song(song):
                raise ValueError(f"Unknown song in room for {user!r}: {song}")


def retrieve_candidates(
    catalog: SongCatalog,
    room: Room,
    neighbors_per_seed: int = 10,
) -> dict[str, dict[str, float]]:
    validate_room(catalog, room)
    candidates: dict[str, dict[str, float]] = {}

    for user, liked_songs in room.items():
        for song in liked_songs:
            song = catalog.resolve_song_name(song)
            neighbors = catalog.nearest_neighbors(song, k=neighbors_per_seed)

            for _, row in neighbors.iterrows():
                candidate = row["song"]
                similarity = float(row["score"])
                if candidate not in candidates:
                    candidates[candidate] = {}
                previous = candidates[candidate].get(user, -1.0)
                candidates[candidate][user] = max(previous, similarity)

            if song not in candidates:
                candidates[song] = {}
            candidates[song][user] = max(candidates[song].get(user, -1.0), 1.0)

    return candidates


def build_retrieval_frame(
    catalog: SongCatalog,
    retrieved: dict[str, dict[str, float]],
) -> pd.DataFrame:
    rows = []
    for song, user_sims in retrieved.items():
        rows.append(
            {
                "song": song,
                "folder": catalog.get_folder(song),
                "retrieval_score": float(sum(user_sims.values())),
                "user_coverage": len(user_sims),
                "users_retrieved": list(user_sims.keys()),
                "retrieval_details": user_sims,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "song",
                "folder",
                "retrieval_score",
                "user_coverage",
                "users_retrieved",
                "retrieval_details",
            ]
        )

    return pd.DataFrame(rows).sort_values("retrieval_score", ascending=False)


def user_score(
    catalog: SongCatalog,
    user_liked_songs: Sequence[str],
    candidate_song: str,
    top_k: int = 2,
) -> float:
    candidate_idx = catalog.song_index(candidate_song)
    scores = []
    for liked_song in user_liked_songs:
        liked_idx = catalog.song_index(liked_song)
        scores.append(float(catalog.similarity[candidate_idx, liked_idx]))

    scores.sort(reverse=True)
    limit = max(1, min(top_k, len(scores)))
    return float(np.mean(scores[:limit]))


def room_score(
    catalog: SongCatalog,
    room: Room,
    candidate_song: str,
    top_k: int = 2,
) -> tuple[float, dict[str, float]]:
    per_user = {}
    for user, liked_songs in room.items():
        per_user[user] = user_score(
            catalog=catalog,
            user_liked_songs=liked_songs,
            candidate_song=candidate_song,
            top_k=top_k,
        )

    average_score = float(np.mean(list(per_user.values())))
    return average_score, per_user


def rank_room_candidates(
    catalog: SongCatalog,
    room: Room,
    neighbors_per_seed: int = 10,
    top_k: int = 2,
    candidate_pool_size: int = 40,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    retrieved = retrieve_candidates(
        catalog=catalog,
        room=room,
        neighbors_per_seed=neighbors_per_seed,
    )
    retrieval_df = build_retrieval_frame(catalog, retrieved)

    top_candidates = retrieval_df.head(candidate_pool_size)["song"].tolist()
    rows = []
    for song in top_candidates:
        score, per_user = room_score(
            catalog=catalog,
            room=room,
            candidate_song=song,
            top_k=top_k,
        )
        rows.append(
            {
                "song": song,
                "folder": catalog.get_folder(song),
                "room_score": score,
                **per_user,
            }
        )

    ranked_df = (
        pd.DataFrame(rows)
        .sort_values("room_score", ascending=False)
        .reset_index(drop=True)
        if rows
        else pd.DataFrame(columns=["song", "folder", "room_score"])
    )
    return retrieval_df.reset_index(drop=True), ranked_df


def next_song_score(
    catalog: SongCatalog,
    prev_song: str,
    candidate_song: str,
    room_score_value: float,
    transition_weight: float = 0.25,
) -> float:
    transition = catalog.transition_score(prev_song, candidate_song)
    return room_score_value + (transition_weight * transition)


def build_greedy_queue(
    catalog: SongCatalog,
    ranked_df: pd.DataFrame,
    queue_len: int = 5,
    transition_weight: float = 0.25,
    same_folder_penalty: float = 0.10,
) -> list[str]:
    if ranked_df.empty or queue_len <= 0:
        return []

    queue: list[str] = []
    used: set[str] = set()
    target_len = min(queue_len, len(ranked_df))

    for _ in range(target_len):
        best_song = None
        best_score = -inf

        for _, row in ranked_df.iterrows():
            song = row["song"]
            if song in used:
                continue

            score = float(row["room_score"])
            if queue:
                prev_song = queue[-1]
                score = next_song_score(
                    catalog=catalog,
                    prev_song=prev_song,
                    candidate_song=song,
                    room_score_value=score,
                    transition_weight=transition_weight,
                )
                if row["folder"] == catalog.get_folder(prev_song):
                    score -= same_folder_penalty

            if score > best_score:
                best_score = score
                best_song = song

        if best_song is None:
            break

        queue.append(best_song)
        used.add(best_song)

    return queue


def score_queue(
    catalog: SongCatalog,
    queue: Sequence[str],
    room_score_map: Mapping[str, float],
    transition_weight: float = 0.25,
    same_folder_penalty: float = 0.0,
) -> float:
    total = 0.0
    for idx, song in enumerate(queue):
        total += float(room_score_map[song])
        if idx == 0:
            continue

        prev_song = queue[idx - 1]
        total += transition_weight * catalog.transition_score(prev_song, song)
        if catalog.get_folder(prev_song) == catalog.get_folder(song):
            total -= same_folder_penalty

    return total


def solve_queue_beam(
    catalog: SongCatalog,
    ranked_df: pd.DataFrame,
    queue_len: int = 5,
    candidate_limit: int = 10,
    transition_weight: float = 0.25,
    same_folder_penalty: float = 0.0,
    beam_width: int = 64,
) -> list[str]:
    candidate_df = ranked_df.head(candidate_limit).copy().reset_index(drop=True)
    if candidate_df.empty or queue_len <= 0:
        return []

    songs = candidate_df["song"].tolist()
    room_score_map = dict(zip(candidate_df["song"], candidate_df["room_score"]))
    target_len = min(queue_len, len(songs))

    states: list[tuple[float, list[str], set[str]]] = [(0.0, [], set())]
    for _ in range(target_len):
        expanded: list[tuple[float, list[str], set[str]]] = []
        for _, queue, used in states:
            for song in songs:
                if song in used:
                    continue

                new_queue = queue + [song]
                new_used = set(used)
                new_used.add(song)
                new_score = score_queue(
                    catalog=catalog,
                    queue=new_queue,
                    room_score_map=room_score_map,
                    transition_weight=transition_weight,
                    same_folder_penalty=same_folder_penalty,
                )
                expanded.append((new_score, new_queue, new_used))

        if not expanded:
            break
        expanded.sort(key=lambda item: item[0], reverse=True)
        states = expanded[:beam_width]

    return states[0][1] if states else []


def solve_queue_ip(
    catalog: SongCatalog,
    ranked_df: pd.DataFrame,
    queue_len: int = 5,
    candidate_limit: int = 10,
    transition_weight: float = 0.25,
    same_folder_penalty: float = 0.0,
    time_limit: int = 10,
    relative_gap: float | None = None,
) -> list[str]:
    try:
        import pulp
    except ImportError as exc:
        raise ImportError(
            "pulp is not installed. Use solve_queue_beam for now or install pulp later."
        ) from exc

    candidate_df = ranked_df.head(candidate_limit).copy().reset_index(drop=True)
    if candidate_df.empty or queue_len <= 0:
        return []

    songs = candidate_df["song"].tolist()
    n = len(songs)
    target_len = min(queue_len, n)
    slots = list(range(target_len))
    room_scores = candidate_df["room_score"].to_numpy()

    transitions: dict[tuple[int, int], float] = {}
    for a in range(n):
        for b in range(n):
            if a == b:
                continue
            score = catalog.transition_score(songs[a], songs[b])
            if catalog.get_folder(songs[a]) == catalog.get_folder(songs[b]):
                score -= same_folder_penalty
            transitions[(a, b)] = score

    model = pulp.LpProblem("music_queue", pulp.LpMaximize)
    x = pulp.LpVariable.dicts(
        "x",
        ((a, t) for a in range(n) for t in slots),
        cat="Binary",
    )
    y = pulp.LpVariable.dicts(
        "y",
        ((a, b, t) for a in range(n) for b in range(n) for t in slots[:-1] if a != b),
        cat="Binary",
    )

    # Give CBC a high-quality incumbent from the faster beam heuristic.
    warm_start_queue = solve_queue_beam(
        catalog=catalog,
        ranked_df=candidate_df,
        queue_len=target_len,
        candidate_limit=n,
        transition_weight=transition_weight,
        same_folder_penalty=same_folder_penalty,
        beam_width=min(128, max(32, n * target_len)),
    )
    warm_start_positions = {song: slot for slot, song in enumerate(warm_start_queue)}
    for a, song in enumerate(songs):
        for t in slots:
            x[(a, t)].setInitialValue(1 if warm_start_positions.get(song) == t else 0)
    for a, song_a in enumerate(songs):
        for b, song_b in enumerate(songs):
            if a == b:
                continue
            for t in slots[:-1]:
                value = int(
                    warm_start_positions.get(song_a) == t
                    and warm_start_positions.get(song_b) == t + 1
                )
                y[(a, b, t)].setInitialValue(value)

    model += (
        pulp.lpSum(room_scores[a] * x[(a, t)] for a in range(n) for t in slots)
        + transition_weight
        * pulp.lpSum(
            transitions[(a, b)] * y[(a, b, t)]
            for a in range(n)
            for b in range(n)
            for t in slots[:-1]
            if a != b
        )
    )

    for t in slots:
        model += pulp.lpSum(x[(a, t)] for a in range(n)) == 1

    for a in range(n):
        model += pulp.lpSum(x[(a, t)] for t in slots) <= 1

    for t in slots[:-1]:
        model += pulp.lpSum(y[(a, b, t)] for a in range(n) for b in range(n) if a != b) == 1

    for a in range(n):
        for t in slots[:-1]:
            model += pulp.lpSum(y[(a, b, t)] for b in range(n) if a != b) == x[(a, t)]

    for b in range(n):
        for t in slots[:-1]:
            model += pulp.lpSum(y[(a, b, t)] for a in range(n) if a != b) == x[(b, t + 1)]

    solver_kwargs: dict[str, int | float | bool] = {"msg": False, "timeLimit": time_limit}
    if relative_gap is not None:
        solver_kwargs["gapRel"] = relative_gap

    status = model.solve(pulp.PULP_CBC_CMD(**solver_kwargs))
    if pulp.LpStatus[status] not in {"Optimal", "Feasible"}:
        return []

    queue = []
    for t in slots:
        for a in range(n):
            value = pulp.value(x[(a, t)])
            if value is not None and value > 0.5:
                queue.append(songs[a])
    return queue


def build_queue(
    catalog: SongCatalog,
    ranked_df: pd.DataFrame,
    queue_len: int = 5,
    candidate_limit: int = 10,
    method: str = "ip",
    transition_weight: float = 0.25,
    same_folder_penalty: float | None = None,
    beam_width: int = 64,
    time_limit: int = 10,
    relative_gap: float | None = None,
) -> list[str]:
    if method == "greedy":
        return build_greedy_queue(
            catalog=catalog,
            ranked_df=ranked_df,
            queue_len=queue_len,
            transition_weight=transition_weight,
            same_folder_penalty=0.10 if same_folder_penalty is None else same_folder_penalty,
        )
    if method == "ip":
        return solve_queue_ip(
            catalog=catalog,
            ranked_df=ranked_df,
            queue_len=queue_len,
            candidate_limit=candidate_limit,
            transition_weight=transition_weight,
            same_folder_penalty=0.0 if same_folder_penalty is None else same_folder_penalty,
            time_limit=time_limit,
            relative_gap=relative_gap,
        )
    if method == "beam":
        return solve_queue_beam(
            catalog=catalog,
            ranked_df=ranked_df,
            queue_len=queue_len,
            candidate_limit=candidate_limit,
            transition_weight=transition_weight,
            same_folder_penalty=0.0 if same_folder_penalty is None else same_folder_penalty,
            beam_width=beam_width,
        )
    raise ValueError(f"Unknown queue method: {method}")
