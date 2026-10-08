from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from music_queue import load_catalog
from music_queue.debug_panel import DebugPanelApp
from music_queue.queueing import generate_queue


def main():
    parser = argparse.ArgumentParser(
        description="Generate a validated queue from a concrete local request."
    )
    parser.add_argument(
        "--request",
        type=Path,
        help="JSON request with explicit stable listener IDs and policy",
    )
    parser.add_argument("--queue-len", type=int, default=5)
    parser.add_argument("--candidate-limit", type=int, default=10)
    parser.add_argument(
        "--method",
        choices=[
            "dp",
            "beam",
            "greedy",
            "milp",
            "ip",
            "round_robin",
            "shared_approval",
        ],
        default="milp",
    )
    parser.add_argument("--time-limit", type=float, default=10.0)
    parser.add_argument("--relative-gap", type=float, default=0.0)
    parser.add_argument("--max-songs-per-folder", type=int)
    parser.add_argument("--discovery-budget", type=int, default=0)
    args = parser.parse_args()
    catalog = load_catalog()
    payload = (
        json.loads(args.request.read_text())
        if args.request
        else {
            **DebugPanelApp(catalog).sample_room_payload(),
            "queue_len": args.queue_len,
            "candidate_limit": args.candidate_limit,
            "method": args.method,
            "time_limit": args.time_limit,
            "relative_gap": args.relative_gap,
            "policy": {
                "folder_cap": args.max_songs_per_folder,
                "discovery_budget": args.discovery_budget,
            },
        }
    )
    result = generate_queue(catalog, payload)
    summary = result.to_dict()
    summary["solver"].pop("logs", None)
    summary["queue_titles"] = [catalog.resolve_song_name(t) for t in result.queue]
    print(json.dumps(summary, indent=2, allow_nan=False))
    if not result.valid_incumbent:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
