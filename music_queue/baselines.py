"""Constraint-matched product baselines; no acoustic score defines acceptance."""

from dataclasses import replace

from .domain import Status
from .solvers.milp import feasible_selection
from .validation import result_for


def solve(instance, deadline, method):
    queue = list(instance.locked_prefix)
    ids = {track.id: a for a, track in enumerate(instance.tracks)}
    turn = 0
    while len(queue) < instance.queue_len and not deadline.expired:
        listener = turn % len(instance.listeners)
        if method == "round_robin":
            order = sorted(
                (t for t in instance.tracks if t.id not in queue),
                key=lambda t: (
                    not instance.acceptance[listener][ids[t.id]],
                    t.id not in instance.listeners[listener].liked,
                    t.id,
                ),
            )
        else:
            order = sorted(
                (t for t in instance.tracks if t.id not in queue),
                key=lambda t: (
                    -sum(row[ids[t.id]] for row in instance.acceptance),
                    t.id,
                ),
            )
        added = False
        for track in order:
            trial = replace(instance, locked_prefix=tuple(queue + [track.id]))
            cover, status = feasible_selection(trial, deadline)
            if cover:
                queue.append(track.id)
                added = True
                break
            if status == Status.TIMEOUT_NO_SOLUTION:
                break
        if not added:
            return result_for(
                instance,
                status=(
                    Status.TIMEOUT_NO_SOLUTION
                    if deadline.expired
                    else Status.NO_SOLUTION_FOUND
                ),
                reason="Baseline could not find a joint-feasible extension within budget",
            )
        turn += 1
    if len(queue) != instance.queue_len:
        return result_for(
            instance,
            status=Status.TIMEOUT_NO_SOLUTION,
            reason="Baseline request budget expired",
        )
    return result_for(
        instance,
        queue,
        Status.FEASIBLE_NOT_PROVEN,
        reason="Constraint-matched " + method,
        solver={"algorithm": method},
    )
