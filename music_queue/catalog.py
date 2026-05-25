from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from .artifacts import load_artifact_arrays
from .paths import ARTIFACT_DIR


@dataclass
class SongCatalog:
    embeddings: np.ndarray
    names: np.ndarray
    folders: np.ndarray
    normalized_embeddings: np.ndarray = field(init=False)
    similarity: np.ndarray = field(init=False)
    song_to_idx: dict[str, int] = field(init=False)
    name_aliases: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        if len(self.embeddings) != len(self.names) or len(self.names) != len(self.folders):
            raise ValueError("Embeddings, names, and folders must have the same length")

        self.embeddings = np.asarray(self.embeddings)
        self.names = np.asarray(self.names, dtype=str)
        self.folders = np.asarray(self.folders, dtype=str)
        feature_means = self.embeddings.mean(axis=0)
        feature_stds = self.embeddings.std(axis=0)
        feature_stds[feature_stds == 0.0] = 1.0
        self.normalized_embeddings = (self.embeddings - feature_means) / feature_stds
        self.similarity = cosine_similarity(self.normalized_embeddings)
        self.song_to_idx = {name: idx for idx, name in enumerate(self.names)}
        self.name_aliases = {}
        for name in self.names:
            for alias in {name, Path(name).stem}:
                self.name_aliases.setdefault(alias.casefold(), name)

    def __len__(self) -> int:
        return len(self.names)

    def resolve_song_name(self, song_name: str) -> str:
        raw_name = str(song_name).strip()
        for alias in (raw_name, Path(raw_name).stem):
            resolved = self.name_aliases.get(alias.casefold())
            if resolved is not None:
                return str(resolved)
        raise KeyError(f"Unknown song: {song_name}")

    def has_song(self, song_name: str) -> bool:
        try:
            self.resolve_song_name(song_name)
        except KeyError:
            return False
        return True

    def song_index(self, song_name: str) -> int:
        resolved_name = self.resolve_song_name(song_name)
        return self.song_to_idx[resolved_name]

    def get_folder(self, song_name: str) -> str:
        return str(self.folders[self.song_index(song_name)])

    def nearest_neighbors(self, song_name: str, k: int = 10) -> pd.DataFrame:
        resolved_name = self.resolve_song_name(song_name)
        idx = self.song_index(resolved_name)
        scores = self.similarity[idx]
        order = np.argsort(scores)[::-1]

        rows: list[dict[str, str | float]] = []
        for neighbor_idx in order:
            if neighbor_idx == idx:
                continue
            rows.append(
                {
                    "song": str(self.names[neighbor_idx]),
                    "folder": str(self.folders[neighbor_idx]),
                    "score": float(scores[neighbor_idx]),
                }
            )
            if len(rows) >= k:
                break

        return pd.DataFrame(rows)

    def transition_score(self, prev_song: str, next_song: str) -> float:
        prev_idx = self.song_index(prev_song)
        next_idx = self.song_index(next_song)
        return float(self.similarity[prev_idx, next_idx])

    def songs_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"song": self.names.astype(str), "folder": self.folders.astype(str)}
        )


def load_catalog(artifact_dir: Path | str = ARTIFACT_DIR) -> SongCatalog:
    embeddings, names, folders = load_artifact_arrays(Path(artifact_dir))
    return SongCatalog(embeddings=embeddings, names=names, folders=folders)
