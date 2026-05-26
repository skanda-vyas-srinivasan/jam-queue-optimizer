from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from .artifacts import DEFAULT_N_MFCC, embedding_feature_slices, load_artifact_arrays
from .paths import ARTIFACT_DIR

TRANSITION_SEGMENT_WEIGHT = 0.85
TRANSITION_HARMONIC_WEIGHT = 0.15


@dataclass
class SongCatalog:
    embeddings: np.ndarray
    intro_embeddings: np.ndarray | None
    outro_embeddings: np.ndarray | None
    names: np.ndarray
    folders: np.ndarray
    normalized_embeddings: np.ndarray = field(init=False)
    normalized_intro_embeddings: np.ndarray | None = field(init=False)
    normalized_outro_embeddings: np.ndarray | None = field(init=False)
    retrieval_similarity: np.ndarray = field(init=False)
    segment_transition_similarity: np.ndarray = field(init=False)
    harmonic_transition_similarity: np.ndarray = field(init=False)
    transition_similarity: np.ndarray = field(init=False)
    similarity: np.ndarray = field(init=False)
    song_to_idx: dict[str, int] = field(init=False)
    name_aliases: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        if len(self.embeddings) != len(self.names) or len(self.names) != len(self.folders):
            raise ValueError("Embeddings, names, and folders must have the same length")

        self.embeddings = np.asarray(self.embeddings)
        self.intro_embeddings = (
            None if self.intro_embeddings is None else np.asarray(self.intro_embeddings)
        )
        self.outro_embeddings = (
            None if self.outro_embeddings is None else np.asarray(self.outro_embeddings)
        )
        self.names = np.asarray(self.names, dtype=str)
        self.folders = np.asarray(self.folders, dtype=str)
        self.normalized_embeddings = self._standardize_matrix(self.embeddings)
        self.retrieval_similarity = cosine_similarity(self.normalized_embeddings)

        if self.intro_embeddings is not None and self.outro_embeddings is not None:
            self.normalized_intro_embeddings = self._standardize_matrix(self.intro_embeddings)
            self.normalized_outro_embeddings = self._standardize_matrix(self.outro_embeddings)
            self.segment_transition_similarity = cosine_similarity(
                self.normalized_outro_embeddings,
                self.normalized_intro_embeddings,
            )
            chroma_slice = embedding_feature_slices(n_mfcc=DEFAULT_N_MFCC)["chroma"]
            self.harmonic_transition_similarity = cosine_similarity(
                self.normalized_outro_embeddings[:, chroma_slice],
                self.normalized_intro_embeddings[:, chroma_slice],
            )
            self.transition_similarity = (
                TRANSITION_SEGMENT_WEIGHT * self.segment_transition_similarity
                + TRANSITION_HARMONIC_WEIGHT * self.harmonic_transition_similarity
            )
        else:
            self.normalized_intro_embeddings = None
            self.normalized_outro_embeddings = None
            self.segment_transition_similarity = self.retrieval_similarity
            self.harmonic_transition_similarity = self.retrieval_similarity
            self.transition_similarity = self.retrieval_similarity

        # Keep this alias for compatibility with code that still expects one matrix.
        self.similarity = self.retrieval_similarity
        self.song_to_idx = {name: idx for idx, name in enumerate(self.names)}
        self.name_aliases = {}
        for name in self.names:
            for alias in {name, Path(name).stem}:
                self.name_aliases.setdefault(alias.casefold(), name)

    @staticmethod
    def _standardize_matrix(matrix: np.ndarray) -> np.ndarray:
        feature_means = matrix.mean(axis=0)
        feature_stds = matrix.std(axis=0)
        feature_stds[feature_stds == 0.0] = 1.0
        return (matrix - feature_means) / feature_stds

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
        scores = self.retrieval_similarity[idx]
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
        return float(self.transition_similarity[prev_idx, next_idx])

    def songs_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"song": self.names.astype(str), "folder": self.folders.astype(str)}
        )


def load_catalog(artifact_dir: Path | str = ARTIFACT_DIR) -> SongCatalog:
    embeddings, intro_embeddings, outro_embeddings, names, folders = load_artifact_arrays(
        Path(artifact_dir)
    )
    return SongCatalog(
        embeddings=embeddings,
        intro_embeddings=intro_embeddings,
        outro_embeddings=outro_embeddings,
        names=names,
        folders=folders,
    )
