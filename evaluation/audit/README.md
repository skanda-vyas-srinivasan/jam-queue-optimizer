# Jam Queue Optimizer audit bundle

Start with `AUDIT_AND_REBUILD_PLAN.md`.

The repository and original PDF were not changed. This bundle contains no music, saved catalog artifacts, model weights, or original CBC benchmark logs.

## Executed here

- `python diagnostics.py`: 24 small synthetic checks using isolated source extracts.
- `python formulation_checks.py`: 10 independent equivalent-formulation checks against exhaustive enumeration, using SciPy/HiGHS.

Environment: Python 3.13.5, NumPy 2.3.5, pandas 2.2.3, scikit-learn 1.8.0, SciPy 1.17.0.

## Rerun against the actual repository

From this directory, using an environment that can import the repository:

```bash
python diagnostics.py --repo /absolute/path/to/reviewed-checkout
```

The checkout must already be at commit `e637be5f78567ea24f04cf0734286f357fef7d74`. The script only reads it and checks the commit; it does not switch branches, modify files, or push anything. The upstream mode was not executed in this audit environment. It still runs synthetic inputs, not the original music benchmark or CBC solves.

The checks intentionally reproduce the current faulty behavior. After a repair they should be converted into desired-behavior regression tests, not kept as assertions that the faults still occur.

The JSON files explicitly distinguish the executed source-extract mode from actual-upstream mode. Timing values are single-run diagnostics and must not be used as production latency claims.
