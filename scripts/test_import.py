from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from music_queue.catalog import load_catalog


def main() -> None:
    catalog = load_catalog()
    print(f"Loaded {len(catalog)} songs with embedding shape {catalog.embeddings.shape}")


if __name__ == "__main__":
    main()
