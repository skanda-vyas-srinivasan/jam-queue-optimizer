from __future__ import annotations

from pathlib import Path
import time

import librosa
import numpy as np

AUDIO_EXTS = (".mp3", ".wav", ".flac", ".m4a")


def find_song_paths(song_root: Path) -> list[Path]:
    song_root = Path(song_root)
    return sorted(
        path
        for path in song_root.rglob("*")
        if path.suffix.lower() in AUDIO_EXTS
    )


def embed_song(path: Path, sample_rate: int = 22050, n_mfcc: int = 40) -> np.ndarray:
    y, sr = librosa.load(path, sr=sample_rate, mono=True)

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


def build_embedding_artifacts(
    song_root: Path,
    sample_rate: int = 22050,
    n_mfcc: int = 40,
    verbose: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    song_paths = find_song_paths(song_root)
    if not song_paths:
        raise ValueError(f"No audio files found under {song_root}")

    if verbose:
        print(f"Found {len(song_paths)} songs under {song_root}", flush=True)

    embeddings: list[np.ndarray] = []
    names: list[str] = []
    folders: list[str] = []

    start_time = time.perf_counter()

    for idx, path in enumerate(song_paths, start=1):
        if verbose:
            print(f"[{idx}/{len(song_paths)}] Embedding {path}", flush=True)
        embeddings.append(embed_song(path, sample_rate=sample_rate, n_mfcc=n_mfcc))
        names.append(path.stem)
        folders.append(path.parent.name)

    if verbose:
        elapsed = time.perf_counter() - start_time
        print(f"Finished embedding {len(song_paths)} songs in {elapsed:.2f}s", flush=True)

    return (
        np.vstack(embeddings),
        np.asarray(names, dtype=str),
        np.asarray(folders, dtype=str),
    )


def save_artifact_arrays(
    output_dir: Path,
    embeddings: np.ndarray,
    names: np.ndarray,
    folders: np.ndarray,
) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    np.save(output_dir / "embeddings.npy", embeddings)
    np.save(output_dir / "song_names.npy", names)
    np.save(output_dir / "song_folders.npy", folders)


def build_and_save_artifacts(
    song_root: Path,
    output_dir: Path,
    sample_rate: int = 22050,
    n_mfcc: int = 40,
    verbose: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    embeddings, names, folders = build_embedding_artifacts(
        song_root=song_root,
        sample_rate=sample_rate,
        n_mfcc=n_mfcc,
        verbose=verbose,
    )
    save_artifact_arrays(
        output_dir=output_dir,
        embeddings=embeddings,
        names=names,
        folders=folders,
    )
    return embeddings, names, folders


def load_artifact_arrays(
    artifact_dir: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    artifact_dir = Path(artifact_dir)
    embeddings = np.load(artifact_dir / "embeddings.npy")
    names = np.load(artifact_dir / "song_names.npy", allow_pickle=True).astype(str)
    folders = np.load(artifact_dir / "song_folders.npy", allow_pickle=True).astype(str)
    return embeddings, names, folders
