"""Interactive exploration and frozen preparation over the canonical queue pipeline."""

from dataclasses import dataclass
import time

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from .candidates import build_instance
from .domain import Deadline, Status
from .preferences import parse_request


def bounded_int(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in [{minimum},{maximum}]")
    return value


def explore(catalog, payload):
    if set(payload) - {"space", "family", "clusters", "dimensions"}:
        raise ValueError("Unknown exploration setting")
    space = payload.get("space", "normalized")
    family = payload.get("family", "full")
    if space not in {"normalized", "raw"} or family not in {
        "full",
        "mfcc",
        "chroma",
        "contrast",
    }:
        raise ValueError("Unknown feature coordinates or family")
    k = bounded_int(
        payload.get("clusters", min(6, len(catalog))),
        "clusters",
        1,
        min(20, len(catalog)),
    )
    dimensions = bounded_int(payload.get("dimensions", 2), "dimensions", 2, 3)
    matrix = (
        catalog.normalized_embeddings if space == "normalized" else catalog.embeddings
    )
    slices = catalog.feature_schema["slices"]
    if family != "full":
        start = slices[family + "_mean"][0]
        end = slices[family + "_std"][1]
        matrix = matrix[:, start:end]
    # Duplicate feature vectors cannot define more distinct acoustic groups.
    effective_k = min(k, len(np.unique(matrix, axis=0)))
    fit = KMeans(n_clusters=effective_k, random_state=42, n_init=10).fit(matrix)
    actual_dimensions = min(dimensions, *matrix.shape)
    if len(catalog) == 1 or np.allclose(matrix, matrix[0]):
        coords = np.zeros((len(catalog), dimensions))
        explained = [0.0] * dimensions
    else:
        pca = PCA(n_components=actual_dimensions)
        transformed = pca.fit_transform(matrix)
        coords = np.pad(transformed, ((0, 0), (0, dimensions - actual_dimensions)))
        explained = pca.explained_variance_ratio_.tolist()
    groups = []
    # Stable displayed numbering by lexicographically smallest member ID.
    labels = sorted(
        set(fit.labels_),
        key=lambda label: min(
            catalog.tracks[a].id for a in range(len(catalog)) if fit.labels_[a] == label
        ),
    )
    numbered = {label: i for i, label in enumerate(labels)}
    for label in labels:
        members = np.flatnonzero(fit.labels_ == label)
        nearest = sorted(
            members,
            key=lambda a: (
                np.linalg.norm(matrix[a] - fit.cluster_centers_[label]),
                catalog.tracks[a].id,
            ),
        )
        groups.append(
            {
                "id": numbered[label],
                "name": f"Cluster {numbered[label] + 1}",
                "members": [catalog.tracks[a].id for a in nearest],
            }
        )
    return {
        "model_hash": catalog.model_hash,
        "space": space,
        "family": family,
        "requested_clusters": k,
        "actual_clusters": len(groups),
        "dimensions": dimensions,
        "explained_variance": explained,
        "groups": groups,
        "points": [
            {
                "track_id": t.id,
                "song": t.title,
                "folder": t.folder,
                "cluster": numbered[fit.labels_[a]],
                "coordinates": coords[a].tolist(),
            }
            for a, t in enumerate(catalog.tracks)
        ],
    }


def retrieve(catalog, payload):
    if set(payload) - {"seeds", "limit", "aggregation"}:
        raise ValueError("Unknown retrieval setting")
    seeds = payload.get("seeds", [])
    if (
        not isinstance(seeds, list)
        or not 1 <= len(seeds) <= 100
        or any(not isinstance(s, str) for s in seeds)
    ):
        raise ValueError("Choose 1 to 100 seed tracks")
    ids = sorted({catalog.track_id(s) for s in seeds})
    limit = bounded_int(
        payload.get("limit", min(20, len(catalog))), "limit", 1, len(catalog)
    )
    aggregation = payload.get("aggregation", "maximum")
    if aggregation not in {"maximum", "top_two"}:
        raise ValueError("Unknown neighbor aggregation")
    rows = []
    indices = [catalog.song_index(s) for s in ids]
    for a, track in enumerate(catalog.tracks):
        if track.id in ids:
            continue
        values = catalog.retrieval_similarity[a, indices]
        score = float(
            values.max() if aggregation == "maximum" else np.sort(values)[-2:].mean()
        )
        closest = min(range(len(ids)), key=lambda i: (-values[i], ids[i]))
        rows.append(
            {
                "track_id": track.id,
                "song": track.title,
                "folder": track.folder,
                "score": score,
                "nearest_seed": ids[closest],
                "seed_scores": {id: float(values[i]) for i, id in enumerate(ids)},
            }
        )
    rows.sort(key=lambda row: (-row["score"], row["track_id"]))
    return {
        "seeds": ids,
        "aggregation": aggregation,
        "rows": rows[:limit],
        "eligible_neighbors": len(rows),
        "evidence": "Acoustic neighbors, not acceptance labels",
    }


@dataclass(frozen=True)
class PreparedPipeline:
    request: object
    instance: object
    provenance: dict
    prepared_at: float


def prepare(catalog, payload):
    if payload.get("session_id"):
        raise ValueError(
            "Use session generation for rolling history; frozen preparation is static"
        )
    request = parse_request(catalog, payload)
    instance, provenance = build_instance(
        catalog, request, Deadline(request.time_limit)
    )
    if instance is None:
        return None, provenance.to_dict()
    prepared = PreparedPipeline(request, instance, provenance, time.monotonic())
    return prepared, {
        "status": Status.FEASIBLE_NOT_PROVEN,
        "instance_hash": instance.hash,
        "candidate_scope_hash": instance.candidate_hash,
        "provenance": provenance,
        "listeners": [
            {"id": listener.id, "name": listener.name}
            for listener in instance.listeners
        ],
        "candidates": [t.id for t in instance.tracks],
        "transition_matrix": [list(row) for row in instance.transitions],
    }
