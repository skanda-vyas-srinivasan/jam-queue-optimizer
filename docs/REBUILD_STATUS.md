# Rebuild status — October 8, 2026

This records the initial rebuild. The subsequent [interactive workbench](WORKBENCH.md) adds editable clusters, retrieval/ranking views, frozen comparisons and local playback with observed session-time tracking. Its suites pass 73 Python tests and 10 client tests; the initial 69-test evidence below remains historical verification.

The software rebuild follows the supplied `AUDIT_AND_REBUILD_PLAN.md`, with the original ten-page objective-model review as supporting evidence. The audit bundle is preserved byte-for-byte in `evaluation/audit/`; the reviews' proposed policy is explicitly provisional. Historical faults were reproduced against the reviewed checkout before replacement. No reported solver percentage is presented as improved enjoyment.

The software and reproducibility work is complete for the local research workbench. **The full plan's independent listening and production release gates are not complete.** Those require observations and deployment decisions that code cannot supply.

## Phase evidence and exit gates

| Phase | Implemented and verified | Gate status |
|---|---|---|
| R0: reproducible baseline | Python 3.12 and exact dependency lock; PuLP/CBC versions and binary hash; 24 diagnostics rerun on actual reviewed code; ten independent HiGHS formulation checks; synthetic tests/install without music; original audit preserved. | Complete for the recorded local environment. Linux CI is configured but has not run remotely. |
| R1: correctness contract | Stable listener/track IDs; schema and atomic checksummed generations; request validation; immutable matrices; one canonical objective; mandatory caps and joint feasibility; structured statuses; independent decoded-queue validation; validated warm starts and fallbacks. | Complete for the tested contract. Invalid decoded values or mismatched phase scores cannot receive an optimality certificate or a fabricated zero gap. |
| R2: candidates grounded in explicit policy | Likes/session acceptance, ordinary dislike and global blocks remain distinct; full eligible ranking; jointly feasible protected shortlist; shared coverage; incumbent/lock retention; explicit expansion/resource conflicts; opt-in discovery. | Complete for the provisional policy. Acoustic predictions remain uncalibrated and visibly separate from acceptance. |
| R3: matched optimization evidence | Exact subset DP, merged incremental beam/greedy, continuous-edge MILP and binary-edge comparator; budgets and phase certificates; exhaustive oracles; 378 synthetic and 96 saved-catalog benchmark runs, frozen instances, complete logs and versions. Final replay of all 30 frozen instances gives agreement between DP and MILP. | Complete for the documented small-instance scope. No general speedup, catalog-wide optimum from a shortlist, or production latency guarantee is claimed. |
| R4: independent listening evidence | Blank song, transition, fixed-selection order and session instruments; randomized trial IDs/private method key; held-out comparison exports; round-robin/shared-approval baselines; local hard-cut excerpt renderer; protocol separating tuning/testing and group-level experimental units. | **Open: real consenting participants and independent judgments are absent.** A usability pilot must precede statistical design and listener-benefit claims. |
| R5: session-aware use | Current-track transition anchor, explicit next-track promises and override, repeat/artist cooldowns, confirmed duration/service history, preserved membership history, feedback and revision-safe stale-result rejection; API and session tests. | Complete for the in-memory workbench. Durable multi-device state and real playback integration remain future work. Partial playback records actual seconds; sequencing still uses the stored track-outro anchor. |
| R6: scale only when measured | Candidate-level transition blocks, bounded request sizes, serialized solves, loopback/same-origin controls; 96 artificial catalog benchmark runs. Dense retrieval is retained for 121 tracks. | Local safeguards implemented. **Production load/memory gate open:** a shared-service target, load tests, persistence and service controls have not been established. Larger indexing/distributed systems remain deferred. |

## Final verification

- **69 tests pass** in the development environment and in an independent environment installing the built wheel, with only synthetic tests/evaluation scripts available. The clean installation has no source package directory or saved music catalog.
- Generated-tone extraction exercises a nondefault 20-MFCC schema, actual two-second intro/outro slices, checksummed publication, row metadata and loading.
- Exhaustive fixtures and property/regression checks cover negative/directed edges, penalty units, joint infeasibility, short supply, names/aliases/duplicates, protected coverage, frozen transforms, malformed input, timeout/gap semantics, invalid decoding, session promises/history and stale revisions.
- Black, Ruff, JavaScript syntax, dependency consistency and whitespace checks pass. Audio dependencies emit three Python-3.13-removal deprecation warnings on Python 3.12; this release explicitly targets Python 3.12.
- The wheel includes frontend assets and excludes music/feature files. Git source archives exclude `songs/` and `artifacts/` via `.gitattributes`; existing local audio, original feature arrays and Git history are preserved.
- The final frozen-instance replay performs 60 exact solves over 30 instances. Its JSON is `evaluation/results/final-instance-replay.json`; these are correctness checks, not additional listening outcomes or latency measurements.

Detailed benchmark scope and numerical gaps are in [BENCHMARKS.md](BENCHMARKS.md). Final command results and distribution checks are recorded in `evaluation/results/final-verification.json`.

## Prepared human-study handoff

`python evaluation/study.py --output output/study --render-audio` prepares local instruments. The executed preparation produced 24 song trials, 12 adjacent-pair trials and three fixed-selection ordering trials, with 21 rendered WAV excerpts. All judgment fields remain blank. These ignored local outputs contain music and have not been published or sent to participants. The private method key must stay separate from raters.

[LISTENING_STUDY.md](LISTENING_STUDY.md) explains consent, held-out splits, duplicate/recording-family leakage, counterbalancing, the actual hard-cut operator and pilot-first sample planning. Acceptance prediction, perceptual transition quality and reduced curation effort cannot be declared validated until independently collected judgments support them. No participants were contacted or ratings invented.

## Operational limits and remaining verification

The v2 API intentionally replaces list-only results and display-name score columns; the original notebook is historical. Artifact migration is explicit, and missing endpoints never silently change the transition model. The default transition metric is an acoustic diagnostic; the loudness/silence alternative uses stated, unvalidated scales.

The request deadline is cooperative: process startup and post-validation can add overhead. Exact DP is capped at 20 candidates; the general shortlist limit is 30. Sessions vanish when the local server restarts. Infeasibility explanations show the relevant evidence/rules rather than claiming a minimal irreducible conflict set.

Browser approval review rejected opening the local debug panel, reporting that permission was declined. Backend/API integration and JavaScript syntax checks passed, but **visual browser verification remains uncompleted**. No alternative browser path was used to bypass that rejection. CI was added but not pushed or executed remotely.

Implementation was committed incrementally. Inspect `git log --oneline e637be5..HEAD` for the baseline, artifact, policy/solver, session/UI, benchmark, study and final verification changes. No changes were pushed or deployed.
