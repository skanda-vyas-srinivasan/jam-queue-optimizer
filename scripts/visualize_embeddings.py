from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from music_queue.catalog import load_catalog
from music_queue.paths import ARTIFACT_DIR
from music_queue.plotting import save_embedding_plot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a 3D PCA plot from saved song embeddings."
    )
    parser.add_argument(
        "--artifact-dir",
        default=str(ARTIFACT_DIR),
        help="Directory containing embeddings.npy, song_names.npy, and song_folders.npy.",
    )
    parser.add_argument(
        "--output",
        default=str(ARTIFACT_DIR / "song_embedding_plot.html"),
        help="Path for the generated HTML plot.",
    )
    parser.add_argument(
        "--space",
        choices=["raw", "normalized"],
        default="normalized",
        help="Which embedding space to visualize. `normalized` matches the space used for similarity.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_catalog(Path(args.artifact_dir))
    output_path = save_embedding_plot(catalog, Path(args.output), space=args.space)
    print(f"Saved {output_path} using {args.space} embeddings")


if __name__ == "__main__":
    main()
