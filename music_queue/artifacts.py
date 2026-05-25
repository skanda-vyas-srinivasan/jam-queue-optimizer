from __future__ import annotations

from pathlib import Path
import time

import librosa
import numpy as np

AUDIO_EXTS = (".mp3", ".wav", ".flac", ".m4a")
TRANSITION_WINDOW_SECONDS = 20.0


def find_song_paths(song_root: Path) -> list[Path]:
    song_root = Path(song_root)
    return sorted(
        path
        for path in song_root.rglob("*")
        if path.suffix.lower() in AUDIO_EXTS
    )


def embed_signal(y: np.ndarray, sr: int, n_mfcc: int = 40) -> np.ndarray:
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
    n_mfcc: int = 40,
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
    n_mfcc: int = 40,
    verbose: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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
        print(f"Finished embedding {len(song_paths)} songs in {elapsed:.2f}s", flush=True)

    return (
        np.vstack(embeddings),
        np.vstack(intro_embeddings),
        np.vstack(outro_embeddings),
        np.asarray(names, dtype=str),
        np.asarray(folders, dtype=str),
    )


def save_artifact_arrays(
    output_dir: Path,
    embeddings: np.ndarray,
    intro_embeddings: np.ndarray,
    outro_embeddings: np.ndarray,
    names: np.ndarray,
    folders: np.ndarray,
) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    np.save(output_dir / "embeddings.npy", embeddings)
    np.save(output_dir / "intro_embeddings.npy", intro_embeddings)
    np.save(output_dir / "outro_embeddings.npy", outro_embeddings)
    np.save(output_dir / "song_names.npy", names)
    np.save(output_dir / "song_folders.npy", folders)


def build_and_save_artifacts(
    song_root: Path,
    output_dir: Path,
    sample_rate: int = 22050,
    n_mfcc: int = 40,
    verbose: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    embeddings, intro_embeddings, outro_embeddings, names, folders = build_embedding_artifacts(
        song_root=song_root,
        sample_rate=sample_rate,
        n_mfcc=n_mfcc,
        verbose=verbose,
    )
    save_artifact_arrays(
        output_dir=output_dir,
        embeddings=embeddings,
        intro_embeddings=intro_embeddings,
        outro_embeddings=outro_embeddings,
        names=names,
        folders=folders,
    )
    return embeddings, names, folders


def load_artifact_arrays(
    artifact_dir: Path,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None, np.ndarray, np.ndarray]:
    artifact_dir = Path(artifact_dir)
    embeddings = np.load(artifact_dir / "embeddings.npy")
    intro_path = artifact_dir / "intro_embeddings.npy"
    outro_path = artifact_dir / "outro_embeddings.npy"
    intro_embeddings = np.load(intro_path) if intro_path.exists() else None
    outro_embeddings = np.load(outro_path) if outro_path.exists() else None
    names = np.load(artifact_dir / "song_names.npy", allow_pickle=True).astype(str)
    folders = np.load(artifact_dir / "song_folders.npy", allow_pickle=True).astype(str)
    return embeddings, intro_embeddings, outro_embeddings, names, folders
