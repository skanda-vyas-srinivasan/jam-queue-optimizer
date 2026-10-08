"""Canonical units: acoustic affinity is never an acceptance label."""

from __future__ import annotations

from .domain import QueueInstance


def edge_value(instance: QueueInstance, a: int, b: int) -> float:
    p = instance.policy
    return p.transition_weight * instance.transitions[a][b] - p.same_folder_penalty * (
        instance.tracks[a].folder == instance.tracks[b].folder
    )


def components(instance: QueueInstance, queue) -> dict:
    indices = {t.id: i for i, t in enumerate(instance.tracks)}
    q = [indices[t] for t in queue]
    utilities = [sum(row[a] for a in q) for row in instance.utilities]
    counts = [sum(row[a] for a in q) for row in instance.acceptance]
    deficits = [max(0, instance.policy.required_count - c) for c in counts]
    # Service debt is measured in target-duration units; old service never resets.
    adjusted = [
        v - (instance.service_debt[u] if instance.service_debt else 0)
        for u, v in enumerate(utilities)
    ]
    relevance = sum(utilities) / len(utilities)
    raw_transition = sum(instance.transitions[a][b] for a, b in zip(q, q[1:]))
    penalty = sum(
        instance.policy.same_folder_penalty
        * (instance.tracks[a].folder == instance.tracks[b].folder)
        for a, b in zip(q, q[1:])
    )
    anchor = instance.anchor_values[q[0]] if q and instance.anchor_values else 0.0
    edges = instance.policy.transition_weight * raw_transition - penalty + anchor
    return {
        "room_utility": relevance,
        "worst_listener_utility": min(adjusted),
        "listener_utilities": utilities,
        "accepted_counts": counts,
        "deficits": deficits,
        "max_deficit": max(deficits),
        "total_deficit": sum(deficits),
        "transition_affinity": raw_transition,
        "weighted_edges": edges,
        "folder_penalty": penalty,
        "anchor_value": anchor,
        "affinity_objective": relevance + edges,
    }


def priority_key(instance, c):
    head = (
        (-c["max_deficit"], -c["total_deficit"])
        if instance.policy.representation == "best_effort"
        else ()
    )
    if instance.policy.objective == "affinity":
        return head + (c["affinity_objective"],)
    return head + (c["worst_listener_utility"], c["room_utility"], c["weighted_edges"])


def choose_final(instance, candidates):
    """Apply explicit preference tolerances only at the completed selection stage."""
    rows = [(tuple(q), components(instance, q)) for q in candidates]
    if not rows:
        return None
    if instance.policy.representation == "best_effort":
        for term in ("max_deficit", "total_deficit"):
            best = min(c[term] for _, c in rows)
            rows = [(q, c) for q, c in rows if c[term] == best]
    if instance.policy.objective == "fair":
        for term in ("worst_listener_utility", "room_utility"):
            best = max(c[term] for _, c in rows)
            rows = [
                (q, c)
                for q, c in rows
                if c[term] >= best - instance.policy.preference_tolerance - 1e-8
            ]
        term = "weighted_edges"
    else:
        term = "affinity_objective"
    rows.sort(key=lambda row: (-row[1][term], row[0]))
    return rows[0][0]
