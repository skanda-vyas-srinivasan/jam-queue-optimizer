from __future__ import annotations

from pathlib import Path
import time

import librosa
import numpy as np

AUDIO_EXTS = (".mp3", ".wav", ".flac", ".m4a")
TRANSITION_WINDOW_SECONDS = 2.0
DEFAULT_N_MFCC = 40
DEFAULT_N_CHROMA = 12
DEFAULT_N_CONTRAST = 7
ArtifactArrays = tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]
SavedArtifactArrays = tuple[np.ndarray, np.ndarray, np.ndarray]


def find_song_paths(song_root: Path) -> list[Path]:
    song_root = Path(song_root)
    return sorted(
        path for path in song_root.rglob("*") if path.suffix.lower() in AUDIO_EXTS
    )


def embedding_feature_slices(
    n_mfcc: int = DEFAULT_N_MFCC,
    n_chroma: int = DEFAULT_N_CHROMA,
    n_contrast: int = DEFAULT_N_CONTRAST,
) -> dict[str, slice]:
    mfcc_mean = slice(0, n_mfcc)
    mfcc_std = slice(mfcc_mean.stop, mfcc_mean.stop + n_mfcc)
    chroma_mean = slice(mfcc_std.stop, mfcc_std.stop + n_chroma)
    chroma_std = slice(chroma_mean.stop, chroma_mean.stop + n_chroma)
    contrast_mean = slice(chroma_std.stop, chroma_std.stop + n_contrast)
    contrast_std = slice(contrast_mean.stop, contrast_mean.stop + n_contrast)
    return {
        "mfcc_mean": mfcc_mean,
        "mfcc_std": mfcc_std,
        "mfcc": slice(mfcc_mean.start, mfcc_std.stop),
        "chroma_mean": chroma_mean,
        "chroma_std": chroma_std,
        "chroma": slice(chroma_mean.start, chroma_std.stop),
        "contrast_mean": contrast_mean,
        "contrast_std": contrast_std,
        "contrast": slice(contrast_mean.start, contrast_std.stop),
        "full": slice(0, contrast_std.stop),
    }


def embed_signal(y: np.ndarray, sr: int, n_mfcc: int = DEFAULT_N_MFCC) -> np.ndarray:
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)

    return np.concatenate(
        [
            mfcc.mean(axis=1),
            mfcc.std(axis=1),
            chroma.mean(axis=1),
            chroma.std(axis=1),
            contrast.mean(axis=1),
            contrast.std(axis=1),
        ]
    )


def slice_signal(
    y: np.ndarray,
    sr: int,
    seconds: float = TRANSITION_WINDOW_SECONDS,
    position: str = "intro",
) -> np.ndarray:
    if position not in {"intro", "outro"}:
        raise ValueError(f"Unknown slice position: {position}")
    if seconds <= 0 or sr <= 0 or not len(y):
        raise ValueError("Audio and segment dimensions must be positive")
    window_samples = max(1, int(seconds * sr))
    if len(y) <= window_samples:
        return y
    if position == "intro":
        return y[:window_samples]
    if position == "outro":
        return y[-window_samples:]
    raise ValueError(f"Unknown slice position: {position}")


def embed_song(
    path: Path,
    sample_rate: int = 22050,
    n_mfcc: int = DEFAULT_N_MFCC,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y, sr = librosa.load(path, sr=sample_rate, mono=True)
    full_embedding = embed_signal(y, sr, n_mfcc=n_mfcc)
    intro_embedding = embed_signal(
        slice_signal(y, sr, position="intro"),
        sr,
        n_mfcc=n_mfcc,
    )
    outro_embedding = embed_signal(
        slice_signal(y, sr, position="outro"),
        sr,
        n_mfcc=n_mfcc,
    )
    return full_embedding, intro_embedding, outro_embedding


def build_embedding_artifacts(
    song_root: Path,
    sample_rate: int = 22050,
    n_mfcc: int = DEFAULT_N_MFCC,
    verbose: bool = False,
) -> ArtifactArrays:
    song_paths = find_song_paths(song_root)
    if not song_paths:
        raise ValueError(f"No audio files found under {song_root}")

    if verbose:
        print(f"Found {len(song_paths)} songs under {song_root}", flush=True)

    embeddings: list[np.ndarray] = []
    intro_embeddings: list[np.ndarray] = []
    outro_embeddings: list[np.ndarray] = []
    names: list[str] = []
    folders: list[str] = []

    start_time = time.perf_counter()

    for idx, path in enumerate(song_paths, start=1):
        if verbose:
            print(f"[{idx}/{len(song_paths)}] Embedding {path}", flush=True)
        full_embedding, intro_embedding, outro_embedding = embed_song(
            path,
            sample_rate=sample_rate,
            n_mfcc=n_mfcc,
        )
        embeddings.append(full_embedding)
        intro_embeddings.append(intro_embedding)
        outro_embeddings.append(outro_embedding)
        names.append(path.stem)
        folders.append(path.parent.name)

    if verbose:
        elapsed = time.perf_counter() - start_time
        print(
            f"Finished embedding {len(song_paths)} songs in {elapsed:.2f}s", flush=True
        )

    return (
        np.vstack(embeddings),
        np.vstack(intro_embeddings),
        np.vstack(outro_embeddings),
        np.asarray(names, dtype=str),
        np.asarray(folders, dtype=str),
    )


def build_and_save_artifacts(
    song_root: Path,
    output_dir: Path,
    sample_rate: int = 22050,
    n_mfcc: int = DEFAULT_N_MFCC,
    verbose: bool = False,
) -> SavedArtifactArrays:
    embeddings, intro_embeddings, outro_embeddings, names, folders = (
        build_embedding_artifacts(
            song_root=song_root,
            sample_rate=sample_rate,
            n_mfcc=n_mfcc,
            verbose=verbose,
        )
    )
    import hashlib
    import soundfile as sf
    from .artifact_store import publish_generation, schema
    from .domain import Track
    from .boundary import track_boundary_metadata

    tracks = []
    for path in find_song_paths(Path(song_root)):
        source = path.relative_to(song_root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        tracks.append(
            Track(
                "trk_" + hashlib.sha256(source.encode()).hexdigest()[:24],
                path.stem,
                path.parent.name,
                source,
                sf.info(path).duration,
                recording_family="audio_" + digest,
                content_hash=digest,
                **track_boundary_metadata(path),
            )
        )
    publish_generation(
        output_dir,
        {
            "embeddings": embeddings,
            "intro_embeddings": intro_embeddings,
            "outro_embeddings": outro_embeddings,
        },
        tracks,
        schema(n_mfcc, sample_rate, TRANSITION_WINDOW_SECONDS),
    )
    return embeddings, names, folders


def load_artifact_arrays(
    artifact_dir: Path,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None, np.ndarray, np.ndarray]:
    from .artifact_store import load_generation

    arrays, tracks, _ = load_generation(artifact_dir)
    return (
        arrays["embeddings"],
        arrays["intro_embeddings"],
        arrays["outro_embeddings"],
        np.array([t.title for t in tracks]),
        np.array([t.folder for t in tracks]),
    )
