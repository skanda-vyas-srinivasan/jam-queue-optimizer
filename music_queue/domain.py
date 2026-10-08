"""Versioned, immutable inputs and explicit outcomes shared by every algorithm."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import hashlib
import json
import math
import time


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    folder: str
    source: str = ""
    duration: float = 180.0
    artist: str | None = None
    recording_family: str | None = None
    content_hash: str | None = None
    playable: bool = True
    intro_rms_dbfs: float | None = None
    outro_rms_dbfs: float | None = None
    leading_silence_seconds: float = 0.0
    trailing_silence_seconds: float = 0.0


@dataclass(frozen=True)
class Listener:
    id: str
    name: str
    liked: tuple[str, ...]
    accepted: tuple[str, ...] = ()
    disliked: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("liked", "accepted", "disliked", "blocked"):
            value = getattr(self, name)
            if isinstance(value, list):
                object.__setattr__(self, name, tuple(value))


@dataclass(frozen=True)
class Policy:
    version: str = "shared-speaker-v1"
    representation: str = "strict"  # best_effort must be explicitly selected
    required_count: int = 1
    folder_cap: int | None = None
    artist_cap: int | None = None
    family_cap: int | None = 1
    transition_weight: float = 0.25
    same_folder_penalty: float = 0.0
    preference_tolerance: float = 0.0
    discovery_budget: int = 0
    objective: str = "fair"  # affinity is a separately labelled research baseline
    predictor: str = "top_two"
    playback: str = "hard_cut"
    transition_model: str = "pooled"


@dataclass(frozen=True)
class SessionRequest:
    listeners: tuple[Listener, ...]
    queue_len: int = 5
    candidate_limit: int = 10
    method: str = "milp"
    policy: Policy = field(default_factory=Policy)
    locked_prefix: tuple[str, ...] = ()
    current_track: str | None = None
    excluded: tuple[str, ...] = ()
    incumbent: tuple[str, ...] = ()
    time_limit: float = 10.0
    relative_gap: float = 0.0
    beam_width: int = 64
    revision: int = 0


@dataclass(frozen=True)
class QueueInstance:
    tracks: tuple[Track, ...]
    listeners: tuple[Listener, ...]
    utilities: tuple[tuple[float, ...], ...]
    acceptance: tuple[tuple[bool, ...], ...]
    transitions: tuple[tuple[float, ...], ...]
    queue_len: int
    policy: Policy = field(default_factory=Policy)
    locked_prefix: tuple[str, ...] = ()
    anchor_values: tuple[float, ...] = ()
    service_debt: tuple[float, ...] = ()
    model_hash: str = "synthetic-v1"
    evidence_hash: str = ""
    candidate_provenance: tuple[tuple[str, tuple[str, ...]], ...] = ()
    revision: int = 0

    def __post_init__(self):
        for name in (
            "tracks",
            "listeners",
            "locked_prefix",
            "anchor_values",
            "service_debt",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        for name in ("utilities", "transitions"):
            object.__setattr__(
                self,
                name,
                tuple(tuple(float(v) for v in row) for row in getattr(self, name)),
            )
        if any(type(value) is not bool for row in self.acceptance for value in row):
            raise ValueError("Acceptance must contain explicit boolean labels")
        object.__setattr__(
            self, "acceptance", tuple(tuple(row) for row in self.acceptance)
        )
        object.__setattr__(
            self,
            "candidate_provenance",
            tuple((t, tuple(r)) for t, r in self.candidate_provenance),
        )
        n, u = len(self.tracks), len(self.listeners)
        if (
            len({t.id for t in self.tracks}) != n
            or len({listener.id for listener in self.listeners}) != u
        ):
            raise ValueError("Duplicate track or listener ID")
        if not u or type(self.queue_len) is not int or self.queue_len <= 0 or not n:
            raise ValueError(
                "An instance needs listeners, candidates, and a positive horizon"
            )
        if len(self.utilities) != u or len(self.acceptance) != u:
            raise ValueError("Listener matrices are misaligned")
        if any(len(r) != n for r in self.utilities + self.acceptance):
            raise ValueError("Candidate matrices are misaligned")
        if len(self.transitions) != n or any(len(r) != n for r in self.transitions):
            raise ValueError("Transition matrix is misaligned")
        values = [v for r in self.utilities + self.transitions for v in r]
        values += list(self.anchor_values) + list(self.service_debt)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Non-finite score")
        if self.anchor_values and len(self.anchor_values) != n:
            raise ValueError("Current-track edges are misaligned")
        if self.service_debt and len(self.service_debt) != u:
            raise ValueError("Service history is misaligned")
        if any(not math.isfinite(t.duration) or t.duration <= 0 for t in self.tracks):
            raise ValueError("Durations must be finite and positive")
        validate_policy(self.policy)

    @property
    def candidate_hash(self):
        return fingerprint([t.id for t in self.tracks])

    @property
    def hash(self):
        return fingerprint(asdict(self))


class Status(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    HARD_INFEASIBLE = "HARD_INFEASIBLE"
    TIMEOUT_NO_SOLUTION = "TIMEOUT_NO_SOLUTION"
    NO_SOLUTION_FOUND = "NO_SOLUTION_FOUND"
    FEASIBLE_NOT_PROVEN = "FEASIBLE_NOT_PROVEN"
    OPTIMAL = "OPTIMAL"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    SOLVER_ERROR = "SOLVER_ERROR"
    STALE_RESULT = "STALE_RESULT"


@dataclass
class QueueResult:
    status: Status
    requested_length: int | None
    queue: tuple[str, ...] = ()
    termination_reason: str = ""
    valid_incumbent: bool = False
    proven_optimal: bool = False
    candidate_hash: str | None = None
    instance_hash: str | None = None
    model_hash: str | None = None
    policy_hash: str | None = None
    objective_components: dict = field(default_factory=dict)
    per_listener: dict = field(default_factory=dict)
    relaxations: list = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    phases: list = field(default_factory=list)
    bound: float | None = None
    gap: float | None = None
    fallback_reason: str | None = None
    timings: dict = field(default_factory=dict)
    solver: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    revision: int = 0

    def to_dict(self):
        return {**asdict(self), "returned_length": len(self.queue)}


def validate_policy(p: Policy):
    if p.representation not in {"strict", "best_effort"}:
        raise ValueError("Representation must be strict or explicitly best_effort")
    if p.objective not in {"fair", "affinity"} or p.predictor not in {
        "top_two",
        "maximum",
        "pockets",
    }:
        raise ValueError("Unknown objective or predictor")
    if p.playback != "hard_cut":
        raise ValueError("Only hard_cut playback is implemented")
    if p.transition_model not in {"pooled", "boundary_cost", "none"}:
        raise ValueError("Unknown transition model")
    for value in (p.required_count, p.discovery_budget):
        if type(value) is not int or not 0 <= value <= 20:
            raise ValueError("Counts must be integers from 0 to 20")
    for value in (p.folder_cap, p.artist_cap, p.family_cap):
        if value is not None and (type(value) is not int or value <= 0):
            raise ValueError("Mandatory caps must be positive integers or null")
    for value in (p.transition_weight, p.same_folder_penalty, p.preference_tolerance):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Weights and tolerance must be finite and nonnegative")


class Deadline:
    def __init__(self, seconds: float):
        self.started = time.perf_counter()
        self.ends = self.started + seconds

    @property
    def remaining(self):
        return max(0.0, self.ends - time.perf_counter())

    @property
    def expired(self):
        return self.remaining <= 0

    @property
    def elapsed(self):
        return time.perf_counter() - self.started
