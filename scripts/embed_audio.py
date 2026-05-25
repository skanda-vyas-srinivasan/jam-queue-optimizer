from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from music_queue.artifacts import build_and_save_artifacts
from music_queue.paths import ARTIFACT_DIR, SONGS_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build song embeddings and save artifact arrays."
    )
    parser.add_argument(
        "--songs-dir",
        default=str(SONGS_DIR),
        help="Directory containing audio files grouped into folders.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ARTIFACT_DIR),
        help="Directory where embeddings.npy and metadata arrays are written.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=22050,
        help="Sample rate used when loading audio.",
    )
    parser.add_argument(
        "--n-mfcc",
        type=int,
        default=40,
        help="Number of MFCC coefficients to extract.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    embeddings, names, _ = build_and_save_artifacts(
        song_root=Path(args.songs_dir),
        output_dir=Path(args.output_dir),
        sample_rate=args.sample_rate,
        n_mfcc=args.n_mfcc,
        verbose=True,
    )
    print(f"Saved {len(names)} songs with embedding shape {embeddings.shape}")
    print("Saved full-song retrieval embeddings plus intro/outro transition embeddings.")
    print("Standardization is applied later in SongCatalog.")


if __name__ == "__main__":
    main()
