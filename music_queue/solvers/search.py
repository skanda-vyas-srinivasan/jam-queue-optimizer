"""Incremental mask search over the static policy with locked prefix and anchor."""

from __future__ import annotations

from ..constraints import can_extend, selection_violations
from ..domain import Deadline, Status
from ..objective import choose_final, components, edge_value, priority_key
from ..validation import conflict_details, result_for


def solve_search(instance, deadline: Deadline, width=None):
    n, k = len(instance.tracks), instance.queue_len
    if width is None and n > 20:
        return result_for(
            instance,
            status=Status.RESOURCE_LIMIT,
            reason="Exact subset DP is limited to 20 candidates; use MILP",
        )
    if k > n:
        return result_for(
            instance,
            status=Status.HARD_INFEASIBLE,
            reason="Insufficient eligible tracks",
            conflicts=conflict_details(instance),
        )
    lookup = {t.id: i for i, t in enumerate(instance.tracks)}
    try:
        prefix = tuple(lookup[t] for t in instance.locked_prefix)
    except KeyError:
        return result_for(
            instance,
            status=Status.HARD_INFEASIBLE,
            reason="Locked track is not eligible",
            conflicts=conflict_details(instance),
        )
    if (
        len(prefix) > k
        or len(set(prefix)) != len(prefix)
        or not can_extend(instance, prefix)
    ):
        return result_for(
            instance,
            status=Status.HARD_INFEASIBLE,
            reason="Locked prefix conflicts with mandatory rules",
            conflicts=conflict_details(instance),
        )
    score = (
        instance.anchor_values[prefix[0]] if prefix and instance.anchor_values else 0.0
    )
    score += sum(edge_value(instance, a, b) for a, b in zip(prefix, prefix[1:]))
    mask = sum(1 << a for a in prefix)
    states = {(mask, prefix[-1] if prefix else -1): (score, prefix)}
    visited = len(states)
    for depth in range(len(prefix), k):
        expanded = {}
        for (mask, last), (score, queue) in states.items():
            if deadline.expired:
                return result_for(
                    instance,
                    status=Status.TIMEOUT_NO_SOLUTION,
                    reason="Request budget expired during search",
                    solver={"states": visited},
                )
            for a in range(n):
                if mask & (1 << a):
                    continue
                new_queue = queue + (a,)
                if not can_extend(instance, new_queue):
                    continue
                if depth + 1 == k and selection_violations(
                    instance, new_queue, complete=True
                ):
                    continue
                added = (
                    edge_value(instance, last, a)
                    if last >= 0
                    else (instance.anchor_values[a] if instance.anchor_values else 0.0)
                )
                value = score + added
                key = (mask | (1 << a), a)
                previous = expanded.get(key)
                # For a fixed visited set and last track, all remaining rules and
                # preference totals are identical. Larger edge sum dominates.
                if (
                    previous is None
                    or value > previous[0] + 1e-10
                    or (abs(value - previous[0]) <= 1e-10 and new_queue < previous[1])
                ):
                    expanded[key] = (value, new_queue)
        visited += len(expanded)
        if not expanded:
            status = (
                Status.HARD_INFEASIBLE if width is None else Status.NO_SOLUTION_FOUND
            )
            return result_for(
                instance,
                status=status,
                reason=(
                    "Joint hard rules are infeasible"
                    if width is None
                    else "Heuristic found no valid queue; infeasibility is not proven"
                ),
                conflicts=conflict_details(instance),
                solver={"states": visited},
            )
        if width is not None and depth + 1 < k:
            ranked = sorted(
                expanded.items(),
                key=lambda item: priority_key(
                    instance,
                    components(instance, [instance.tracks[a].id for a in item[1][1]]),
                ),
                reverse=True,
            )
            expanded = dict(ranked[:width])
        states = expanded
    queues = [tuple(instance.tracks[a].id for a in q) for _, q in states.values()]
    queue = choose_final(instance, queues)
    if queue is None:
        return result_for(
            instance, status=Status.TIMEOUT_NO_SOLUTION, reason="No valid incumbent"
        )
    return result_for(
        instance,
        queue,
        Status.OPTIMAL if width is None else Status.FEASIBLE_NOT_PROVEN,
        (
            "Exhaustive subset DP completed"
            if width is None
            else "Finite-width heuristic completed"
        ),
        solver={
            "states": visited,
            "algorithm": "subset_dp" if width is None else "beam",
            "beam_width": width,
        },
    )
