"""Constraint-matched greedy with look-ahead. Failure never proves infeasibility."""

from .search import solve_search


def solve(instance, deadline):
    return solve_search(instance, deadline, width=1)
