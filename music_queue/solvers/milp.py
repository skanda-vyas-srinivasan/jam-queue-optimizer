"""Pinned PuLP 3.3/CBC model, validated MIP starts and honest phase certificates."""

from __future__ import annotations

from collections import defaultdict
import math
from pathlib import Path
import re
import tempfile
import time

import pulp

from ..domain import Deadline, Status
from ..objective import components, edge_value
from ..validation import conflict_details, result_for, validate_queue
from .beam import solve as solve_beam


def add_selection_rules(model, instance, selected):
    n = len(instance.tracks)
    p = instance.policy
    for a, track in enumerate(instance.tracks):
        if not track.playable or any(
            track.id in listener.blocked for listener in instance.listeners
        ):
            model += selected[a] == 0, f"eligibility_{a }"
    for field, cap in (
        ("folder", p.folder_cap),
        ("artist", p.artist_cap),
        ("recording_family", p.family_cap),
    ):
        if cap is None:
            continue
        groups = defaultdict(list)
        for a, t in enumerate(instance.tracks):
            group = getattr(t, field)
            if group is not None:
                groups[group].append(a)
        for number, members in enumerate(groups.values()):
            model += (
                pulp.lpSum(selected[a] for a in members) <= cap,
                f"{field }_{number }",
            )
    model += (
        pulp.lpSum(
            selected[a]
            for a in range(n)
            if not any(row[a] for row in instance.acceptance)
        )
        <= p.discovery_budget,
        "discovery",
    )
    deficits = []
    for u, row in enumerate(instance.acceptance):
        count = pulp.lpSum(selected[a] for a in range(n) if row[a])
        if p.representation == "strict":
            model += count >= p.required_count, f"representation_{u }"
        else:
            deficit = pulp.LpVariable(
                f"deficit_{u }", 0, p.required_count, cat="Continuous"
            )
            model += deficit >= p.required_count - count
            deficits.append(deficit)
    return deficits


def parse_certificate(model, log):
    """PuLP's status alone can call a time-limited incumbent 'Optimal'."""
    proof = (
        model.status == pulp.LpStatusOptimal
        and model.sol_status == pulp.LpSolutionOptimal
        and "Stopped on time" not in log
        and "within gap tolerance" not in log
    )
    infeasible = model.status == pulp.LpStatusInfeasible and (
        "infeasible" in log.lower()
    )
    bound_match = re.search(r"(?:Upper bound|Lower bound):\s+([-+0-9.eE]+)", log)
    gap_match = re.search(r"Gap:\s+([-+0-9.eE]+)", log)
    return {
        "proven": proof,
        "infeasible": infeasible,
        "status": pulp.LpStatus.get(model.status, "Unknown"),
        "solution_status": pulp.LpSolution.get(model.sol_status, "Unknown"),
        "bound": (
            -float(bound_match.group(1))
            if bound_match and "Lower bound:" in bound_match.group(0)
            else float(bound_match.group(1)) if bound_match else None
        ),
        "gap": abs(float(gap_match.group(1))) if gap_match else None,
        "warm_start_accepted": "MIPStart provided solution" in log,
        "termination": (
            "optimal"
            if proof
            else (
                "infeasible"
                if infeasible
                else (
                    "gap_limit"
                    if "within gap tolerance" in log
                    else "time_limit" if "Stopped on time" in log else "no_certificate"
                )
            )
        ),
    }


def _cbc(model, deadline, gap, warm, directory, phase):
    if deadline.expired:
        return None, ""
    path = Path(directory) / f"{phase }.log"
    solver = pulp.PULP_CBC_CMD(
        msg=False,
        timeLimit=deadline.remaining,
        gapRel=gap,
        warmStart=warm,
        threads=1,
        options=["randomSeed 42", "randomCbcSeed 42", "timeMode elapsed"],
        logPath=str(path),
    )
    solver.tmpDir = directory
    model.solve(solver)
    log = path.read_text() if path.exists() else ""
    return parse_certificate(model, log), log


def feasible_selection(instance, deadline):
    """Selection-only joint model for candidate protection; no powerset precheck."""
    if deadline.expired:
        return (), Status.TIMEOUT_NO_SOLUTION
    n = len(instance.tracks)
    model = pulp.LpProblem("candidate_cover", pulp.LpMinimize)
    z = [pulp.LpVariable(f"z_{a }", cat="Binary") for a in range(n)]
    model += pulp.lpSum(z) == instance.queue_len
    add_selection_rules(model, instance, z)
    lookup = {t.id: a for a, t in enumerate(instance.tracks)}
    for t in instance.locked_prefix:
        if t not in lookup:
            return (), Status.HARD_INFEASIBLE
        model += z[lookup[t]] == 1
    model += -pulp.lpSum(
        sum(row[a] for row in instance.utilities) * z[a] for a in range(n)
    )
    with tempfile.TemporaryDirectory(prefix="jam-cover-") as directory:
        cert, _ = _cbc(model, deadline, 0, False, directory, "cover")
    if cert and cert["infeasible"]:
        return (), Status.HARD_INFEASIBLE
    chosen = tuple(
        instance.tracks[a].id
        for a in range(n)
        if z[a].value() is not None and abs(z[a].value() - 1) <= 1e-6
    )
    # Order selection with locks first; independent validation includes every rule.
    queue = instance.locked_prefix + tuple(
        t for t in chosen if t not in instance.locked_prefix
    )
    if not validate_queue(instance, queue):
        return queue, Status.FEASIBLE_NOT_PROVEN
    return (), Status.TIMEOUT_NO_SOLUTION


def solve(instance, deadline, relative_gap=0.0, binary_y=False, warm_start=True):
    if pulp.__version__ != "3.3.0":
        return result_for(
            instance, status=Status.SOLVER_ERROR, reason="Use pinned PuLP 3.3.0"
        )
    n, k = len(instance.tracks), instance.queue_len
    if k > n:
        return result_for(
            instance,
            status=Status.HARD_INFEASIBLE,
            reason="Insufficient eligible tracks",
        )
    if deadline.expired:
        return result_for(
            instance,
            status=Status.TIMEOUT_NO_SOLUTION,
            reason="Budget expired before construction",
        )
    started = time.perf_counter()
    # The bundled CBC 2.10.3 can mishandle a negative maximization MIP-start
    # objective. Minimize the negative canonical expression in every phase.
    # Exhaustive fixtures exercise both signs with starts enabled/disabled.
    model = pulp.LpProblem("music_queue_v2", pulp.LpMinimize)
    x = {
        (a, t): pulp.LpVariable(f"x_{a }_{t }", cat="Binary")
        for a in range(n)
        for t in range(k)
    }
    y = {}
    for a in range(n):
        if deadline.expired:
            return result_for(
                instance,
                status=Status.TIMEOUT_NO_SOLUTION,
                reason="Budget expired during construction",
            )
        for b in range(n):
            if a == b:
                continue
            for t in range(k - 1):
                y[a, b, t] = pulp.LpVariable(
                    f"y_{a }_{b }_{t }",
                    0,
                    1,
                    cat="Binary" if binary_y else "Continuous",
                )
    selected = [pulp.lpSum(x[a, t] for t in range(k)) for a in range(n)]
    for t in range(k):
        model += pulp.lpSum(x[a, t] for a in range(n)) == 1
    for a in range(n):
        model += selected[a] <= 1
        for t in range(k - 1):
            model += pulp.lpSum(y[a, b, t] for b in range(n) if b != a) == x[a, t]
    for b in range(n):
        for t in range(k - 1):
            model += pulp.lpSum(y[a, b, t] for a in range(n) if a != b) == x[b, t + 1]
    deficits = add_selection_rules(model, instance, selected)
    lookup = {track.id: a for a, track in enumerate(instance.tracks)}
    if len(instance.locked_prefix) > k or len(set(instance.locked_prefix)) != len(
        instance.locked_prefix
    ):
        return result_for(
            instance, status=Status.HARD_INFEASIBLE, reason="Invalid locked prefix"
        )
    for t, track in enumerate(instance.locked_prefix):
        if track not in lookup:
            return result_for(
                instance,
                status=Status.HARD_INFEASIBLE,
                reason="Locked track is not eligible",
            )
        model += x[lookup[track], t] == 1
    utilities = [
        pulp.lpSum(row[a] * selected[a] for a in range(n)) for row in instance.utilities
    ]
    room = pulp.lpSum(utilities) / len(utilities)
    edges = pulp.lpSum(edge_value(instance, a, b) * v for (a, b, t), v in y.items())
    if instance.anchor_values:
        edges += pulp.lpSum(instance.anchor_values[a] * x[a, 0] for a in range(n))
    phases = []
    maximum_deficit = None
    worst = None
    if deficits:
        maximum_deficit = pulp.LpVariable(
            "maximum_deficit", 0, instance.policy.required_count
        )
        for d in deficits:
            model += maximum_deficit >= d
        phases += [
            ("maximum_representation_deficit", -maximum_deficit, 0.0),
            ("total_representation_deficit", -pulp.lpSum(deficits), 0.0),
        ]
    if instance.policy.objective == "fair":
        worst = pulp.LpVariable("worst_listener", lowBound=None)
        for u, value in enumerate(utilities):
            debt = instance.service_debt[u] if instance.service_debt else 0
            model += worst <= value - debt
        phases += [
            ("worst_listener_utility", worst, instance.policy.preference_tolerance),
            ("room_utility", room, instance.policy.preference_tolerance),
            ("weighted_edges", edges, 0.0),
        ]
    else:
        phases += [("affinity_objective", room + edges, 0.0)]
    construction_seconds = time.perf_counter() - started
    incumbent = ()
    if warm_start and not deadline.expired:
        warm_deadline = Deadline(min(0.25, deadline.remaining * 0.15))
        beam = solve_beam(instance, warm_deadline, width=32)
        if beam.valid_incumbent:
            incumbent = beam.queue

    def initialize(queue):
        positions = {lookup[track]: t for t, track in enumerate(queue)}
        for (a, t), v in x.items():
            v.setInitialValue(int(positions.get(a) == t))
        for (a, b, t), v in y.items():
            v.setInitialValue(int(positions.get(a) == t and positions.get(b) == t + 1))
        c = components(instance, queue)
        for u, d in enumerate(deficits):
            d.setInitialValue(c["deficits"][u])
        if maximum_deficit is not None:
            maximum_deficit.setInitialValue(c["max_deficit"])
        if worst is not None:
            worst.setInitialValue(c["worst_listener_utility"])

    logs, phase_results = [], []
    all_proven = True
    last_cert = None
    invalid_decoding = False
    solve_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="jam-milp-") as directory:
        for phase_name, expression, tolerance in phases:
            if deadline.expired:
                all_proven = False
                break
            model.setObjective(-expression)
            if incumbent:
                initialize(incumbent)
            try:
                cert, log = _cbc(
                    model,
                    deadline,
                    relative_gap,
                    bool(incumbent) and warm_start,
                    directory,
                    phase_name,
                )
            except (pulp.PulpSolverError, OSError) as exc:
                result = result_for(
                    instance,
                    incumbent,
                    Status.FEASIBLE_NOT_PROVEN if incumbent else Status.SOLVER_ERROR,
                    reason=str(exc),
                    fallback_reason=(
                        "Validated heuristic incumbent" if incumbent else None
                    ),
                )
                result.solver = {"logs": logs, "algorithm": "milp"}
                return result
            logs.append({"phase": phase_name, "log": log})
            if cert is None:
                all_proven = False
                break
            last_cert = cert
            # Verify exactly one integral placement per slot before decoding.
            decoded = []
            integral = True
            for t in range(k):
                values = [x[a, t].value() for a in range(n)]
                if any(v is None or min(abs(v), abs(v - 1)) > 1e-6 for v in values):
                    integral = False
                    break
                chosen = [a for a, v in enumerate(values) if v > 0.5]
                if len(chosen) != 1:
                    integral = False
                    break
                decoded.append(instance.tracks[chosen[0]].id)
            decoded_valid = integral and not validate_queue(instance, decoded)
            if decoded_valid:
                incumbent = tuple(decoded)
            if cert["infeasible"]:
                # Only a joint model can certify this; never relax policy here.
                if incumbent:
                    return result_for(
                        instance,
                        incumbent,
                        Status.FEASIBLE_NOT_PROVEN,
                        reason="Priority phase numerical conflict; validated prior incumbent",
                        fallback_reason="Restricted priority model reported infeasible",
                        phases=phase_results,
                        solver={"logs": logs, "algorithm": "milp"},
                    )
                return result_for(
                    instance,
                    status=Status.HARD_INFEASIBLE,
                    reason="Joint mandatory rules are infeasible",
                    conflicts=conflict_details(instance),
                    solver={"logs": logs, "algorithm": "milp"},
                )
            value = pulp.value(expression)
            if value is None and incumbent:
                c = components(instance, incumbent)
                value = {
                    "maximum_representation_deficit": -c["max_deficit"],
                    "total_representation_deficit": -c["total_deficit"],
                    **c,
                }[phase_name]
            if cert["proven"]:
                canonical = components(instance, decoded) if decoded_valid else None
                canonical_value = (
                    {
                        "maximum_representation_deficit": -canonical["max_deficit"],
                        "total_representation_deficit": -canonical["total_deficit"],
                        **canonical,
                    }[phase_name]
                    if canonical
                    else None
                )
                if (
                    canonical_value is None
                    or value is None
                    or not math.isclose(
                        canonical_value, value, rel_tol=1e-7, abs_tol=1e-6
                    )
                ):
                    cert = {
                        **cert,
                        "proven": False,
                        "termination": "invalid_decoding_or_score",
                        "bound": None,
                        "gap": None,
                    }
                    invalid_decoding = True
            last_cert = cert
            phase_results.append(
                {
                    "name": phase_name,
                    "value": value,
                    **cert,
                    "preference_tolerance": tolerance,
                    "decoded_queue_valid": bool(decoded_valid),
                }
            )
            if not cert["proven"] or not incumbent:
                all_proven = False
                break
            model += expression >= value - tolerance - 1e-7, f"freeze_{phase_name }"
    proven = all_proven and len(phase_results) == len(phases) and bool(incumbent)
    status = (
        Status.OPTIMAL
        if proven
        else (
            Status.FEASIBLE_NOT_PROVEN
            if incumbent
            else Status.SOLVER_ERROR if invalid_decoding else Status.TIMEOUT_NO_SOLUTION
        )
    )
    result = result_for(
        instance,
        incumbent,
        status,
        (
            "All priority phases proven"
            if proven
            else (
                "Decoded solver values did not pass validation; no optimality claim"
                if invalid_decoding
                else "Budget/gap limit; no complete optimality proof"
            )
        ),
        phases=phase_results,
        bound=last_cert["bound"] if last_cert else None,
        gap=last_cert["gap"] if last_cert else None,
        solver={
            "algorithm": "milp",
            "pulp": pulp.__version__,
            "binary_y": binary_y,
            "logs": logs,
            "bound_phase": phase_results[-1]["name"] if phase_results else None,
        },
    )
    result.timings = {
        "construction": construction_seconds,
        "solve": time.perf_counter() - solve_started,
    }
    return result
