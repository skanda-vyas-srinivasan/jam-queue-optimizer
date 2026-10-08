# Project orientation

The original project was a notebook-first prototype of a multi-user local music queue. Its handcrafted baseline pools MFCC, chroma and spectral contrast. The earlier richer-feature experiment was reverted because its extra preprocessing cost had no established gain.

The 2026-10-08 rebuild follows the supplied independent audit in `evaluation/audit/AUDIT_AND_REBUILD_PLAN.md`. The original PDF and audit distinguish score optimization from independent listening validity. The unchanged audit source extracts remain historical evidence, not regression tests that should continue asserting faults.

Current orientation:

1. Read `README.md` and `docs/POLICY.md` for the provisional policy and API.
2. Trace `music_queue/queueing.py` through preferences, candidates, an immutable instance, solver and validator.
3. Read `docs/ARTIFACTS.md` for identity, schema and transform guarantees.
4. Read `docs/BENCHMARKS.md` for exact experiment scope.
5. Read `docs/SESSIONS.md` and `docs/LISTENING_STUDY.md` for rolling behavior and the independent evidence gate.

Keep acoustic predictions separate from affirmative evidence. Do not silently drop listeners, hard limits or representation; do not equate a feasible incumbent with an optimality certificate. All algorithms consume the same frozen problem and all returned queues pass decoded-queue validation.

The notebook remains a historical record. Streaming integrations, neural predictors, bandits and distributed services remain deferred until an identified failure or measured bottleneck justifies them. Local sessions are in memory; production durability and listener-study outcomes have not been established.
