from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from music_queue.debug_panel import serve_debug_panel
from music_queue.paths import ARTIFACT_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local music-queue debug panel."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to bind.",
    )
    parser.add_argument(
        "--artifact-dir",
        default=str(ARTIFACT_DIR),
        help="Directory containing saved artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    serve_debug_panel(
        host=args.host,
        port=args.port,
        artifact_dir=Path(args.artifact_dir),
    )


if __name__ == "__main__":
    main()
