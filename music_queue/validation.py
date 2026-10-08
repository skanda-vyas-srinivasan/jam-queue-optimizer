"""Independent decoded-queue checks used for incumbents, heuristics, and results."""
from __future__ import annotations

from dataclasses import asdict
import math

from .constraints import selection_violations
from .domain import QueueResult, Status, fingerprint
from .objective import components


def validate_queue(instance, queue, expected_components=None):
    violations = []
    ids = {t.id: i for i, t in enumerate(instance.tracks)}
    if len(queue) != instance.queue_len:
        violations.append(f"Requested {instance.queue_len} tracks, decoded {len(queue)}")
    if len(set(queue)) != len(queue):
        violations.append("Repeated track")
    if any(t not in ids for t in queue):
        violations.append("Track outside eligible candidate scope")
        return violations
    q = [ids[t] for t in queue]
    if any(not instance.tracks[a].playable for a in q):
        violations.append("Unplayable track")
    if tuple(queue[:len(instance.locked_prefix)]) != instance.locked_prefix:
        violations.append("Locked prefix changed")
    for t in queue:
        if any(t in l.blocked for l in instance.listeners):
            violations.append(f"Explicit block violated for {t}")
    violations += selection_violations(instance, q, complete=True)
    if expected_components is not None:
        actual = components(instance, queue)
        for term, expected in expected_components.items():
            if isinstance(expected, (float, int)) and term in actual:
                if not math.isclose(actual[term], expected, rel_tol=1e-7, abs_tol=1e-6):
                    violations.append(f"Canonical score mismatch: {term}")
    return violations


def result_for(instance, queue=(), status=Status.FEASIBLE_NOT_PROVEN, reason="", **kwargs):
    violations = validate_queue(instance, queue) if queue else []
    if queue and violations:
        return QueueResult(Status.SOLVER_ERROR, instance.queue_len,
                           termination_reason="Decoded incumbent failed validation",
                           violations=violations, instance_hash=instance.hash,
                           candidate_hash=instance.candidate_hash)
    valid = bool(queue)
    c = components(instance, queue) if valid else {}
    per_listener = {}
    relaxations = []
    if valid:
        for u, listener in enumerate(instance.listeners):
            accepted = [t for t in queue if instance.acceptance[u][next(i for i, x in enumerate(instance.tracks) if x.id == t)]]
            tracks = {t.id: t for t in instance.tracks}
            elapsed = 0.0
            wait = None
            for t in queue:
                if t in accepted:
                    wait = elapsed
                    break
                elapsed += tracks[t].duration
            per_listener[listener.id] = {
                "display_name": listener.name, "accepted_count": c["accepted_counts"][u],
                "accepted_seconds": sum(tracks[t].duration for t in accepted),
                "first_acceptable_wait_seconds": wait,
                "affinity_sum": c["listener_utilities"][u], "representation_deficit": c["deficits"][u]}
            if c["deficits"][u]:
                relaxations.append({"rule": "representation", "listener_id": listener.id,
                                    "deficit": c["deficits"][u], "authorized": True})
    return QueueResult(status, instance.queue_len, tuple(queue), reason, valid,
                       status == Status.OPTIMAL and valid, instance.candidate_hash,
                       instance.hash, instance.model_hash, fingerprint(asdict(instance.policy)),
                       c, per_listener, relaxations, revision=instance.revision, **kwargs)


def conflict_details(instance):
    return [{"listener_id": l.id, "accepted_candidates": [t.id for i, t in enumerate(instance.tracks)
             if instance.acceptance[u][i]], "required_count": instance.policy.required_count}
            for u, l in enumerate(instance.listeners)] + [{"mandatory_rules": asdict(instance.policy),
                                                           "locked_prefix": instance.locked_prefix}]
