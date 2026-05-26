from __future__ import annotations

import argparse
from pathlib import Path
from pprint import pprint
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from music_queue.catalog import load_catalog
from music_queue.queueing import build_queue, rank_room_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local queue-generation demo against the saved artifacts."
    )
    parser.add_argument(
        "--queue-len",
        type=int,
        default=5,
        help="Number of songs to place in the queue.",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        default=10,
        help="How many top ranked candidates the queue builder considers.",
    )
    parser.add_argument(
        "--method",
        choices=["beam", "greedy", "ip"],
        default="ip",
        help="Queue-building strategy.",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=10,
        help="CBC solver time limit in seconds when using method=ip.",
    )
    parser.add_argument(
        "--relative-gap",
        type=float,
        default=None,
        help="Optional relative MIP gap for method=ip, e.g. 0.05 for 5%%.",
    )
    parser.add_argument(
        "--max-songs-per-folder",
        type=int,
        default=None,
        help="Optional hard cap on how many songs from one folder can appear in the queue. Defaults to a mild auto-cap in the solvers.",
    )
    parser.add_argument(
        "--user-representation-top-k",
        type=int,
        default=3,
        help="For method=ip, require each user to be represented by at least one of their top-k shortlist songs when feasible. Use 0 to disable.",
    )
    return parser.parse_args()


def build_sample_room(song_names: list[str]) -> dict[str, list[str]]:
    return {
        "user_A": [song_names[0], song_names[1], song_names[2]],
        "user_B": [song_names[10], song_names[11], song_names[12]],
        "user_C": [song_names[20], song_names[21], song_names[22]],
    }


def main() -> None:
    args = parse_args()
    catalog = load_catalog()
    room = build_sample_room(catalog.names.tolist())

    retrieval_df, ranked_df = rank_room_candidates(catalog, room)
    queue = build_queue(
        catalog=catalog,
        ranked_df=ranked_df,
        queue_len=args.queue_len,
        candidate_limit=args.candidate_limit,
        method=args.method,
        max_songs_per_folder=args.max_songs_per_folder,
        user_representation_top_k=None if args.user_representation_top_k <= 0 else args.user_representation_top_k,
        time_limit=args.time_limit,
        relative_gap=args.relative_gap,
    )

    print("Room:")
    pprint(room)
    print()
    print("Top ranked candidates:")
    print(ranked_df.head(args.candidate_limit).to_string(index=False))
    print()
    print("Method:", args.method)
    if args.method == "ip":
        print("Time limit:", args.time_limit, "seconds")
        print("Relative gap:", args.relative_gap)
        print("Max songs per folder:", args.max_songs_per_folder if args.max_songs_per_folder is not None else "auto")
        print("User representation top-k:", args.user_representation_top_k)
        print()
    print("Queue:")
    for idx, song in enumerate(queue, start=1):
        print(f"{idx}. {song}")
    print()
    print("Retrieved candidates:", len(retrieval_df))


if __name__ == "__main__":
    main()
