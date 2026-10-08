from .search import solve_search


def solve(instance, deadline, width=64):
    return solve_search(instance, deadline, width=width)
