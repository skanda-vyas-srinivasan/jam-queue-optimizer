"""Request orchestration. Every algorithm receives one validated frozen instance."""

from __future__ import annotations

import time

from .candidates import build_instance
from .domain import Deadline, QueueResult, SessionRequest, Status
from .preferences import normalize_request, parse_request
from .solvers import beam, greedy, milp, subset_dp
from .validation import result_for, validate_queue


def solve_instance(
    instance, method="milp", deadline=None, beam_width=64, relative_gap=0.0, **options
):
    deadline = deadline or Deadline(10.0)
    if deadline.expired:
        return QueueResult(
            Status.TIMEOUT_NO_SOLUTION,
            instance.queue_len,
            termination_reason="Request budget expired",
        )
    if method in {"milp", "ip"}:
        return milp.solve(instance, deadline, relative_gap=relative_gap, **options)
    if method == "dp":
        return subset_dp.solve(instance, deadline)
    if method == "beam":
        return beam.solve(instance, deadline, width=beam_width)
    if method == "greedy":
        return greedy.solve(instance, deadline)
    if method in {"round_robin", "shared_approval"}:
        from .baselines import solve

        return solve(instance, deadline, method)
    raise ValueError("Unknown solver method")


def generate_queue(catalog, request, service_debt=None):
    started = time.perf_counter()
    raw_limit = (
        request.time_limit
        if isinstance(request, SessionRequest)
        else request.get("time_limit", 10.0) if isinstance(request, dict) else 10.0
    )
    requested_length = (
        request.queue_len
        if isinstance(request, SessionRequest)
        else request.get("queue_len", 5) if isinstance(request, dict) else 5
    )
    if type(requested_length) is not int:
        requested_length = None
    try:
        request = (
            normalize_request(catalog, request)
            if isinstance(request, SessionRequest)
            else parse_request(catalog, request)
        )
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        return QueueResult(
            Status.INVALID_REQUEST,
            requested_length,
            termination_reason=str(exc),
            violations=[str(exc)],
            timings={"total": time.perf_counter() - started},
        )
    deadline = Deadline(max(0.0, raw_limit - (time.perf_counter() - started)))
    try:
        instance, provenance = build_instance(catalog, request, deadline, service_debt)
        if instance is None:
            provenance.timings["total"] = time.perf_counter() - started
            return provenance
        solving_started = time.perf_counter()
        result = solve_instance(
            instance, request.method, deadline, request.beam_width, request.relative_gap
        )
        # A heuristic failure cannot prove infeasibility. Retry the exact joint
        # model under the same deadline; any fallback remains constraint matched.
        if (
            not result.valid_incumbent
            and request.method in {"beam", "greedy", "round_robin", "shared_approval"}
            and deadline.remaining > 0.01
        ):
            failed = result.termination_reason
            result = solve_instance(
                instance, "milp", deadline, relative_gap=request.relative_gap
            )
            result.fallback_reason = failed
        if not result.valid_incumbent and result.status in {
            Status.TIMEOUT_NO_SOLUTION,
            Status.NO_SOLUTION_FOUND,
            Status.SOLVER_ERROR,
        }:
            cover = provenance["cover"]
            if not validate_queue(instance, cover):
                result = result_for(
                    instance,
                    cover,
                    Status.FEASIBLE_NOT_PROVEN,
                    reason="Solver did not finish; returned the validated joint-feasibility incumbent",
                    fallback_reason=result.termination_reason,
                    phases=result.phases,
                    solver=result.solver,
                    timings=result.timings,
                )
        result.provenance = provenance
        result.timings["preprocessing"] = provenance["preprocessing_seconds"]
        result.timings.setdefault("construction", 0.0)
        result.timings.setdefault(
            "solve",
            time.perf_counter() - solving_started - result.timings["construction"],
        )
        result.timings["total"] = time.perf_counter() - started
        result.revision = request.revision
        return result
    except (ValueError, KeyError, TypeError) as exc:
        return QueueResult(
            Status.INVALID_REQUEST,
            request.queue_len,
            termination_reason=str(exc),
            violations=[str(exc)],
            timings={"total": time.perf_counter() - started},
        )


# Deliberate v2 boundary: list-only outcomes and score-column user identity were
# removed. These aliases keep common imports discoverable but return QueueResult.
build_queue = generate_queue
solve_queue_ip = milp.solve
solve_queue_beam = beam.solve
build_greedy_queue = greedy.solve
