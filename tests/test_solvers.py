from dataclasses import replace
import itertools

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from music_queue import Track, Listener, Policy, QueueInstance, Status
from music_queue.domain import Deadline
from music_queue.objective import components, choose_final
from music_queue.queueing import solve_instance
from music_queue.solvers.milp import parse_certificate
from music_queue.validation import validate_queue


def instance(n=5, k=3, seed=42, policy=None):
    rng = np.random.default_rng(seed)
    return QueueInstance(
        tuple(
            Track(
                f"t{i }",
                f"Track {i }",
                f"F{i //2 }",
                artist=f"A{i //2 }",
                duration=100 + i * 10,
            )
            for i in range(n)
        ),
        (
            Listener("u0", "Alex", ("t0",)),
            Listener("u1", "Alex", ("t3" if n > 3 else "t1",)),
        ),
        tuple(tuple(float(v) for v in row) for row in rng.uniform(-1, 1, (2, n))),
        tuple(
            tuple(i in options for i in range(n))
            for options in ({0, 1}, {min(3, n - 1), n - 1})
        ),
        tuple(tuple(float(v) for v in row) for row in rng.uniform(-1, 1, (n, n))),
        k,
        policy
        or Policy(
            folder_cap=2,
            discovery_budget=k,
            objective="affinity",
            same_folder_penalty=0.1,
        ),
    )


def oracle(ins):
    queues = [
        q
        for q in itertools.permutations([t.id for t in ins.tracks], ins.queue_len)
        if not validate_queue(ins, q)
    ]
    return choose_final(ins, queues)


@pytest.mark.parametrize("objective", ["fair", "affinity"])
@pytest.mark.parametrize("binary_y", [False, True])
@pytest.mark.parametrize("seed", range(5))
def test_exact_dp_and_both_milps_match_exhaustive(objective, binary_y, seed):
    ins = instance(
        seed=seed,
        policy=Policy(
            folder_cap=2,
            discovery_budget=3,
            objective=objective,
            same_folder_penalty=0.13,
            preference_tolerance=0.04 if objective == "fair" else 0,
        ),
    )
    expected = oracle(ins)
    dp = solve_instance(ins, "dp", Deadline(5))
    milp = solve_instance(ins, "milp", Deadline(5), binary_y=binary_y)
    assert dp.status == milp.status == Status.OPTIMAL, (
        milp.termination_reason,
        milp.phases,
    )
    assert not validate_queue(ins, milp.queue)
    for term in (
        "max_deficit",
        "total_deficit",
        "worst_listener_utility",
        "room_utility",
        "weighted_edges",
        "affinity_objective",
    ):
        assert dp.objective_components[term] == pytest.approx(
            components(ins, expected)[term], abs=1e-6
        )
        # Fair phases with tolerance may select different preference values while
        # preserving identical optimal edge value and the documented budgets.
        if (
            objective == "affinity"
            and term == "affinity_objective"
            or objective == "fair"
            and term == "weighted_edges"
        ):
            assert milp.objective_components[term] == pytest.approx(
                components(ins, expected)[term], abs=1e-6
            )


def test_joint_cap_and_representation_conflict_never_relaxed():
    ins = instance(n=3, k=2, policy=Policy(folder_cap=1, discovery_budget=2))
    ins = replace(ins, acceptance=((True, False, False), (False, True, False)))
    for method in ("dp", "milp"):
        result = solve_instance(ins, method, Deadline(5))
        assert result.status == Status.HARD_INFEASIBLE
        assert not result.queue and not result.relaxations
        assert result.conflicts


def test_strict_disjoint_one_slot_and_authorized_best_effort():
    ins = replace(instance(n=2, k=1), acceptance=((True, False), (False, True)))
    for method in ("dp", "milp"):
        assert solve_instance(ins, method, Deadline(5)).status == Status.HARD_INFEASIBLE
    soft = replace(ins, policy=replace(ins.policy, representation="best_effort"))
    for method in ("dp", "milp"):
        result = solve_instance(soft, method, Deadline(5))
        assert result.status == Status.OPTIMAL
        assert result.objective_components["total_deficit"] == 1
        assert len(result.relaxations) == 1 and result.relaxations[0]["authorized"]


def test_short_supply_is_explicit_not_truncated():
    ins = instance(n=3, k=5)
    for method in ("dp", "milp", "beam", "greedy"):
        result = solve_instance(ins, method, Deadline(5))
        assert result.status == Status.HARD_INFEASIBLE and not result.queue
        assert result.requested_length == 5


def test_validated_warm_start_matches_representation_and_penalty_units():
    ins = instance(seed=3)
    result = solve_instance(ins, "milp", Deadline(5))
    assert result.valid_incumbent and not validate_queue(ins, result.queue)
    assert result.phases[0]["warm_start_accepted"]
    assert result.objective_components["affinity_objective"] == pytest.approx(
        components(ins, result.queue)["affinity_objective"]
    )
    assert "mips" in result.solver["logs"][0]["log"]


def test_validator_rejects_bad_decoding_and_objective_mismatch():
    ins = instance()
    good = oracle(ins)
    assert not validate_queue(ins, good)
    for bad in (good[:-1], (good[0],) * 3, ("unknown",) + good[1:], ("t2", "t2", "t2")):
        assert validate_queue(ins, bad)
    assert validate_queue(ins, good, {"affinity_objective": 999})
    locked = replace(ins, locked_prefix=("t0",))
    assert validate_queue(locked, ("t1", "t3", "t4"))
    blocked = replace(
        ins, listeners=(replace(ins.listeners[0], blocked=(good[0],)), ins.listeners[1])
    )
    assert validate_queue(blocked, good)


def test_locked_prefix_anchor_and_history_are_used_by_every_solver():
    ins = replace(
        instance(),
        locked_prefix=("t0",),
        anchor_values=(0.5, 0, 0, 0, 0),
        service_debt=(1.0, 0.0),
    )
    expected = oracle(ins)
    for method in ("dp", "milp", "beam", "greedy"):
        result = solve_instance(ins, method, Deadline(5))
        if result.valid_incumbent:
            assert result.queue[0] == "t0" and not validate_queue(ins, result.queue)
            assert result.objective_components["anchor_value"] == 0.5
        if method in {"dp", "milp"}:
            assert result.objective_components["affinity_objective"] == pytest.approx(
                components(ins, expected)["affinity_objective"]
            )


def test_timeout_and_gap_certificate_distinguish_pulp_solution_status():
    import pulp

    model = pulp.LpProblem()
    model.status = pulp.LpStatusOptimal
    model.sol_status = pulp.LpSolutionIntegerFeasible
    cert = parse_certificate(model, "Stopped on time limit\nUpper bound: 3.5\nGap: 0.2")
    assert not cert["proven"] and cert["bound"] == 3.5 and cert["gap"] == 0.2
    model.sol_status = pulp.LpSolutionOptimal
    assert not parse_certificate(
        model, "Optimal solution found (within gap tolerance)"
    )["proven"]
    assert parse_certificate(model, "Optimal solution found")["proven"]
    ins = instance()
    for method in ("dp", "milp", "beam"):
        result = solve_instance(ins, method, Deadline(0))
        assert not result.proven_optimal and result.status == Status.TIMEOUT_NO_SOLUTION


@given(st.integers(min_value=0, max_value=1000))
@settings(max_examples=12, deadline=None)
def test_nested_candidates_and_listener_renaming_properties(seed):
    from music_queue.candidates import subset_instance

    full = instance(seed=seed)
    small = subset_instance(full, ("t0", "t1", "t3", "t4"))
    a = solve_instance(small, "dp", Deadline(5))
    b = solve_instance(full, "dp", Deadline(5))
    assert (
        b.objective_components["affinity_objective"]
        >= a.objective_components["affinity_objective"] - 1e-8
    )
    renamed = replace(
        full,
        listeners=tuple(
            replace(listener, name="room_score" if i else "song")
            for i, listener in enumerate(full.listeners)
        ),
    )
    assert solve_instance(renamed, "dp", Deadline(5)).queue == b.queue


def test_instance_is_deeply_immutable_and_rejects_bad_labels():
    ins = instance()
    rows = [list(row) for row in ins.utilities]
    frozen = replace(ins, utilities=rows)
    rows[0][0] = 999
    assert frozen.utilities[0][0] != 999
    with pytest.raises(ValueError):
        replace(ins, acceptance=((1,) * 5, (0,) * 5))


def test_trivial_required_last_track_does_not_scan_powerset():
    n = 20
    base = instance(
        n=n,
        k=1,
        policy=Policy(required_count=1, discovery_budget=1, objective="affinity"),
    )
    for index in (0, 19):
        ins = replace(
            base,
            acceptance=tuple(tuple(i == index for i in range(n)) for _ in range(2)),
        )
        r = solve_instance(ins, "dp", Deadline(1))
        assert r.status == Status.OPTIMAL and r.queue == (f"t{index }",)
        assert r.solver["states"] == 2


def test_transition_endpoint_opportunity_loss_is_an_objective_fixture():
    from music_queue.candidates import subset_instance

    ins = QueueInstance(
        (Track("a", "a", "X"), Track("b", "b", "Y"), Track("bridge", "bridge", "Z")),
        (Listener("u", "U", ("a", "b", "bridge")),),
        ((0.51, 0.5, 0.49),),
        ((True, True, True),),
        ((1.0, -1.0, 1.0), (-1.0, 1.0, -1.0), (1.0, -1.0, 1.0)),
        2,
        Policy(objective="affinity", required_count=0, discovery_budget=2),
    )
    a = solve_instance(subset_instance(ins, ("a", "b")), "dp", Deadline(1))
    b = solve_instance(ins, "dp", Deadline(1))
    assert a.objective_components["affinity_objective"] == pytest.approx(0.76)
    assert b.objective_components["affinity_objective"] == pytest.approx(1.25)


def test_zero_constant_one_slot_objective_with_and_without_warm_start():
    ins = replace(
        instance(n=3, k=1),
        acceptance=((True,) * 3, (True,) * 3),
        utilities=((0.0,) * 3, (0.0,) * 3),
        policy=Policy(objective="affinity", discovery_budget=1, transition_weight=0.0),
    )
    for warm in (False, True):
        r = solve_instance(ins, "milp", Deadline(1), warm_start=warm)
        assert (
            r.status == Status.OPTIMAL
            and r.objective_components["affinity_objective"] == 0.0
        )


def test_optimal_solver_label_cannot_certify_invalid_decoding(monkeypatch):
    from music_queue.solvers import milp

    original = milp._cbc

    def corrupted(model, *args, **kwargs):
        cert, log = original(model, *args, **kwargs)
        next(v for v in model.variables() if v.name.startswith("x_")).varValue = 0.5
        return cert, log

    monkeypatch.setattr(milp, "_cbc", corrupted)
    result = solve_instance(instance(), "milp", Deadline(2))
    assert not result.proven_optimal
    assert result.valid_incumbent and result.status == Status.FEASIBLE_NOT_PROVEN
    assert result.phases[0]["termination"] == "invalid_decoding_or_score"
    assert not result.phases[0]["decoded_queue_valid"]
    assert result.bound is None and result.gap is None
