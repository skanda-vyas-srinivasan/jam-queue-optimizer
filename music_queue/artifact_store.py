"""Atomic, checksummed feature generations with frozen, common-coordinate transforms."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import uuid

import numpy as np

from .domain import Track, fingerprint


ARRAY_NAMES = ("embeddings", "intro_embeddings", "outro_embeddings")


def fit_transform(matrix):
    mean, scale = matrix.mean(axis=0), matrix.std(axis=0)
    scale[scale == 0] = 1.
    return {"mean": mean.tolist(), "scale": scale.tolist(), "version": "zscore-v1"}


def transform(matrix, spec):
    mean, scale = np.asarray(spec["mean"]), np.asarray(spec["scale"])
    if mean.shape != (matrix.shape[1],) or scale.shape != mean.shape:
        raise ValueError("Transform dimensions do not match feature schema")
    if not np.isfinite(mean).all() or not np.isfinite(scale).all() or (scale <= 0).any():
        raise ValueError("Invalid frozen transform")
    return (matrix - mean) / scale


def schema(n_mfcc=40, sample_rate=22050, window_seconds=20.):
    cursor, slices = 0, {}
    for name, size in (("mfcc_mean", n_mfcc), ("mfcc_std", n_mfcc),
                       ("chroma_mean",12), ("chroma_std",12),
                       ("contrast_mean",7), ("contrast_std",7)):
        slices[name] = [cursor, cursor+size]
        cursor += size
    slices["chroma"] = [2*n_mfcc, 2*n_mfcc+24]
    return {"version": "pooled-librosa-v1", "dimensions": cursor, "slices": slices,
            "n_mfcc": n_mfcc, "sample_rate": sample_rate, "segment_seconds": window_seconds,
            "playback": "hard_cut", "zero_vector_similarity": 0.,
            "transition_signal": "shared-transform pooled boundary affinity; not validated smoothness"}


def validate_arrays(arrays, tracks, feature_schema):
    dims = feature_schema["dimensions"]
    for name in ARRAY_NAMES:
        array = arrays[name]
        if array.shape != (len(tracks), dims) or not np.isfinite(array).all():
            raise ValueError(f"Invalid shape or nonfinite values in {name}")
    if not tracks or len({t.id for t in tracks}) != len(tracks):
        raise ValueError("Artifact track IDs must be unique and nonempty")
    if any(t.duration <= 0 or not np.isfinite(t.duration) for t in tracks):
        raise ValueError("Invalid track duration")
    expected = schema(feature_schema["n_mfcc"], feature_schema["sample_rate"], feature_schema["segment_seconds"])
    if expected["dimensions"] != dims or expected["slices"] != feature_schema["slices"]:
        raise ValueError("Unsupported or inconsistent feature schema")


def publish_generation(output_dir, arrays, tracks, feature_schema, transforms=None, provenance=None):
    output_dir = Path(output_dir)
    validate_arrays(arrays, tracks, feature_schema)
    transforms = transforms or {
        "retrieval": fit_transform(arrays["embeddings"]),
        "transition": fit_transform(np.vstack([arrays["intro_embeddings"], arrays["outro_embeddings"]]))}
    for name in ARRAY_NAMES:
        transform(arrays[name], transforms["retrieval" if name == "embeddings" else "transition"])
    generations = output_dir / "generations"
    generations.mkdir(parents=True, exist_ok=True)
    generation = uuid.uuid4().hex
    temporary = generations / f".tmp-{generation}"
    final = generations / generation
    temporary.mkdir()
    checksums = {}
    try:
        for name, array in arrays.items():
            path = temporary / f"{name}.npy"
            np.save(path, array, allow_pickle=False)
            checksums[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        versions = {name: importlib.metadata.version(name) for name in ("numpy", "librosa", "soundfile")}
        manifest = {"format_version": 1, "generation": generation, "schema": feature_schema,
                    "tracks": [asdict(t) for t in tracks], "row_order": [t.id for t in tracks],
                    "transforms": transforms, "checksums": checksums, "package_versions": versions,
                    "provenance": provenance or {"origin": "fresh_audio_extraction"}}
        manifest["model_hash"] = fingerprint({"schema": feature_schema, "transforms": transforms,
                                              "checksums": checksums})
        manifest["manifest_hash"] = fingerprint(manifest)
        text = json.dumps(manifest, indent=2, allow_nan=False) + '\n'
        (temporary / "manifest.json").write_text(text)
        os.replace(temporary, final)
        pointer = output_dir / f".manifest-{generation}.json"
        pointer.write_text(text)
        os.replace(pointer, output_dir / "manifest.json")
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def load_generation(artifact_dir):
    artifact_dir = Path(artifact_dir)
    pointer = artifact_dir / "manifest.json"
    if not pointer.exists():
        raise ValueError("Legacy artifacts need an explicit migration: python scripts/migrate_artifacts.py")
    manifest = json.loads(pointer.read_text())
    claimed = manifest.pop("manifest_hash", None)
    if fingerprint(manifest) != claimed:
        raise ValueError("Artifact manifest checksum mismatch")
    manifest["manifest_hash"] = claimed
    if manifest["format_version"] != 1:
        raise ValueError("Unsupported artifact format")
    generation = manifest["generation"]
    if not isinstance(generation,str) or len(generation) != 32 or any(c not in '0123456789abcdef' for c in generation):
        raise ValueError("Invalid artifact generation identifier")
    directory = artifact_dir / "generations" / generation
    if json.loads((directory / "manifest.json").read_text()) != manifest:
        raise ValueError("Artifact pointer and generation disagree")
    arrays = {}
    for name in ARRAY_NAMES:
        path = directory / f"{name}.npy"
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["checksums"][path.name]:
            raise ValueError(f"Checksum mismatch: {path.name}")
        arrays[name] = np.load(path, allow_pickle=False)
    tracks = tuple(Track(**row) for row in manifest["tracks"])
    if [t.id for t in tracks] != manifest["row_order"]:
        raise ValueError("Artifact row order mismatch")
    validate_arrays(arrays, tracks, manifest["schema"])
    return arrays, tracks, manifest
