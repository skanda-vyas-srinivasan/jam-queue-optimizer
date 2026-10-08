from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from .artifact_store import fit_transform, load_generation, schema, transform
from .domain import Track, fingerprint
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
    tracks: tuple[Track, ...] = ()
    feature_schema: dict | None = None
    transforms: dict | None = None
    model_hash: str = ""
    manifest: dict = field(default_factory=dict)

    def __post_init__(self):
        self.embeddings = np.asarray(self.embeddings, dtype=float)
        self.names = np.asarray(self.names, dtype=str)
        self.folders = np.asarray(self.folders, dtype=str)
        n = len(self.names)
        if (
            len(self.folders) != n
            or self.embeddings.ndim != 2
            or len(self.embeddings) != n
            or n < 1
        ):
            raise ValueError("Embeddings, names and folders must align and be nonempty")
        if self.feature_schema is None:
            if self.embeddings.shape[1] != 118:
                raise ValueError(
                    "Nondefault features require an explicit feature schema"
                )
            self.feature_schema = schema()
        dims = self.feature_schema["dimensions"]
        if self.embeddings.shape != (n, dims) or not np.isfinite(self.embeddings).all():
            raise ValueError("Invalid full-song features")
        if self.intro_embeddings is None or self.outro_embeddings is None:
            raise ValueError(
                "Both segment arrays are required; transition fallback is not implicit"
            )
        self.intro_embeddings = np.asarray(self.intro_embeddings, dtype=float)
        self.outro_embeddings = np.asarray(self.outro_embeddings, dtype=float)
        for array in (self.intro_embeddings, self.outro_embeddings):
            if array.shape != (n, dims) or not np.isfinite(array).all():
                raise ValueError("Invalid segment dimensions or nonfinite values")
        if not self.tracks:
            # Synthetic callers must provide unique names or explicit IDs.
            if len(set(self.names)) != n:
                raise ValueError("Duplicate titles require explicit stable track IDs")
            self.tracks = tuple(
                Track(
                    "synthetic_" + fingerprint(str(name))[:24], str(name), str(folder)
                )
                for name, folder in zip(self.names, self.folders)
            )
        if len(self.tracks) != n or len({t.id for t in self.tracks}) != n:
            raise ValueError("Track metadata or IDs are misaligned")
        if any(
            t.title != name or t.folder != folder
            for t, name, folder in zip(self.tracks, self.names, self.folders)
        ):
            raise ValueError("Track metadata differs from feature row order")
        self.transforms = self.transforms or {
            "retrieval": fit_transform(self.embeddings),
            "transition": fit_transform(
                np.vstack([self.intro_embeddings, self.outro_embeddings])
            ),
        }
        self.normalized_embeddings = transform(
            self.embeddings, self.transforms["retrieval"]
        )
        self.normalized_intro_embeddings = transform(
            self.intro_embeddings, self.transforms["transition"]
        )
        self.normalized_outro_embeddings = transform(
            self.outro_embeddings, self.transforms["transition"]
        )
        self.retrieval_similarity = cosine_similarity(self.normalized_embeddings)
        self.similarity = self.retrieval_similarity  # legacy diagnostic alias
        self.id_to_idx = {t.id: i for i, t in enumerate(self.tracks)}
        self.aliases = {}
        for i, t in enumerate(self.tracks):
            for alias in {t.id, t.title, Path(t.title).stem, t.source}:
                if alias:
                    self.aliases.setdefault(alias.casefold(), set()).add(i)
        self.model_hash = self.model_hash or fingerprint(
            {"schema": self.feature_schema, "transforms": self.transforms}
        )
        self._transition_cache = None
        self._segment_cache = None
        self._chroma_cache = None
        for array in (
            self.embeddings,
            self.intro_embeddings,
            self.outro_embeddings,
            self.normalized_embeddings,
            self.normalized_intro_embeddings,
            self.normalized_outro_embeddings,
            self.retrieval_similarity,
        ):
            array.setflags(write=False)

    def __len__(self):
        return len(self.tracks)

    def song_index(self, reference):
        raw = str(reference).strip()
        if raw in self.id_to_idx:
            return self.id_to_idx[raw]
        for alias in (raw, Path(raw).stem):
            indices = self.aliases.get(alias.casefold(), set())
            if len(indices) > 1:
                raise ValueError(
                    f"Ambiguous song title {reference!r}; use a stable track ID"
                )
            if indices:
                return next(iter(indices))
        raise KeyError(f"Unknown track: {reference}")

    def track_id(self, reference):
        return self.tracks[self.song_index(reference)].id

    def resolve_song_name(self, reference):
        return str(self.names[self.song_index(reference)])

    def has_song(self, reference):
        try:
            self.song_index(reference)
            return True
        except (KeyError, ValueError):
            return False

    def get_folder(self, reference):
        return self.tracks[self.song_index(reference)].folder

    def nearest_neighbors(self, reference, k=10):
        if type(k) is not int or k < 0:
            raise ValueError("Neighbor count must be a nonnegative integer")
        columns = ["track_id", "song", "folder", "score"]
        if k == 0:
            return pd.DataFrame(columns=columns)
        idx = self.song_index(reference)
        order = sorted(
            (i for i in range(len(self)) if i != idx),
            key=lambda i: (-self.retrieval_similarity[idx, i], self.tracks[i].id),
        )[:k]
        return pd.DataFrame(
            [
                {
                    "track_id": self.tracks[i].id,
                    "song": self.tracks[i].title,
                    "folder": self.tracks[i].folder,
                    "score": float(self.retrieval_similarity[idx, i]),
                }
                for i in order
            ],
            columns=columns,
        )

    def transition_block(self, indices, model="pooled"):
        if model not in {"pooled", "boundary_cost", "none"}:
            raise ValueError("Unknown transition model")
        if model == "none":
            matrix = np.zeros((len(indices), len(indices)))
            return matrix, matrix, matrix
        if model == "boundary_cost":
            from .boundary import simple_boundary_cost

            matrix = np.array(
                [
                    [
                        simple_boundary_cost(self.tracks[a], self.tracks[b])
                        for b in indices
                    ]
                    for a in indices
                ]
            )
            return matrix, matrix, matrix
        out = self.normalized_outro_embeddings[indices]
        intro = self.normalized_intro_embeddings[indices]
        start, end = self.feature_schema["slices"]["chroma"]
        segment = cosine_similarity(out, intro)
        chroma = cosine_similarity(out[:, start:end], intro[:, start:end])
        return segment, chroma, 0.85 * segment + 0.15 * chroma

    def transition_score(self, previous, next_track, model="pooled"):
        if model not in {"pooled", "boundary_cost", "none"}:
            raise ValueError("Unknown transition model")
        a, b = self.song_index(previous), self.song_index(next_track)
        if model == "none":
            return 0.0
        if model == "boundary_cost":
            from .boundary import simple_boundary_cost

            return simple_boundary_cost(self.tracks[a], self.tracks[b])
        start, end = self.feature_schema["slices"]["chroma"]
        out = self.normalized_outro_embeddings[a : a + 1]
        intro = self.normalized_intro_embeddings[b : b + 1]
        return float(
            0.85 * cosine_similarity(out, intro)[0, 0]
            + 0.15 * cosine_similarity(out[:, start:end], intro[:, start:end])[0, 0]
        )

    def _all_transitions(self):
        if self._transition_cache is None:
            self._segment_cache, self._chroma_cache, self._transition_cache = (
                self.transition_block(list(range(len(self))))
            )
        return self._transition_cache

    @property
    def transition_similarity(self):
        return self._all_transitions()

    @property
    def segment_transition_similarity(self):
        self._all_transitions()
        return self._segment_cache

    @property
    def harmonic_transition_similarity(self):
        self._all_transitions()
        return self._chroma_cache

    def songs_frame(self):
        return pd.DataFrame(
            {
                "track_id": [t.id for t in self.tracks],
                "song": self.names,
                "folder": self.folders,
            }
        )


def load_catalog(artifact_dir=ARTIFACT_DIR):
    arrays, tracks, manifest = load_generation(artifact_dir)
    return SongCatalog(
        **arrays,
        names=np.array([t.title for t in tracks]),
        folders=np.array([t.folder for t in tracks]),
        tracks=tracks,
        feature_schema=manifest["schema"],
        transforms=manifest["transforms"],
        model_hash=manifest["model_hash"],
        manifest=manifest,
    )
