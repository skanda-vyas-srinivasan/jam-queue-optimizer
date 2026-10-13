# Jam Queue Optimizer

A local Python research workbench with an interactive GUI for shared queues over an audio catalog. It combines explicit listener acceptance, separately labelled acoustic predictions, constrained selection, and directed sequencing. It validates the queue it returns and reports whether an optimum was proved over its shortlist.

The implemented objective is inspectable and tested. Better shared listening is still a hypothesis: this repository has no independent listener judgments establishing preference prediction or product benefit. See [the listening protocol](docs/LISTENING_STUDY.md).

## Setup

Use Python 3.12 (the tested environment is 3.12.14). PuLP is pinned to 3.3.0, with the bundled CBC 2.10.3 binary recorded by hash in the evaluation environment. A PuLP 4 migration is a separate change, not an implicit dependency upgrade.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m pytest
```

Tests use synthetic features and generated tones; they do not need the MP3 catalog, network, or a notebook runtime. Black and Ruff are included in the development lock:

```bash
.venv/bin/black --check music_queue scripts tests evaluation/benchmark.py evaluation/catalog_benchmark.py evaluation/study.py
.venv/bin/ruff check music_queue scripts tests evaluation/benchmark.py evaluation/catalog_benchmark.py evaluation/study.py
```

The historical music remains in this checkout. No redistribution permission was established by the reviews, and no shared assets/history were deleted. To obtain code without downloading music, use a sparse clone:

```bash
git clone --filter=blob:none --sparse https://github.com/skanda-vyas-srinivasan/jam-queue-optimizer.git
cd jam-queue-optimizer
git sparse-checkout set music_queue scripts tests docs evaluation
```

Source archives and wheels exclude the audio and catalog artifacts. Supply your own authorized local catalog for audio-backed demos.

## Local catalog and workbench

The saved baseline arrays predate the schema. If `artifacts/manifest.json` does not exist, migrate them explicitly once. This requires the original local audio files and saved arrays:

```bash
.venv/bin/python scripts/migrate_artifacts.py
.venv/bin/python scripts/test_import.py
.venv/bin/python scripts/run_queue_demo.py --method dp
.venv/bin/python scripts/run_debug_panel.py
```

For later launches, run only `.venv/bin/python scripts/run_debug_panel.py`.

Open the [interactive workbench](http://127.0.0.1:8765). Its four stages let you form and edit clusters on a selectable 2D/3D map, build listener profiles, inspect acoustic retrieval and every room-ranking score, prepare a protected shortlist, then sequence and play the queue. A player available across views supports previews, pause, seeking, volume and queue navigation. Static solver comparisons use the same frozen instance; manual orders are revalidated and lose their optimality certificate. See the [workflow guide](docs/WORKBENCH.md).

For a first queue, leave settings at their defaults: **Load demo profiles → Retrieval & ranking → Prepare candidates → Sequence & play → Build queue → Play queue**. Clusters organize acoustic exploration; assigning a track to a cluster does not automatically mark it accepted by a listener.

Profiles/groups/settings save in the browser and support JSON import/export. Rolling sessions preserve promises and history, recording observed session-queue playback at track end/skip/stop; previews do not count as session service. Empty profiles produce an error instead of losing room members. Sessions are in memory only; restarting clears them. Node is needed only for client development tests (`npm ci --ignore-scripts`, then `npm test`), not to run the GUI.

For new audio, folders are categories, not artist identity:

```bash
.venv/bin/python scripts/embed_audio.py --songs-dir /absolute/path/to/authorized-audio --output-dir /absolute/path/to/artifacts --n-mfcc 40
.venv/bin/python scripts/run_debug_panel.py --artifact-dir /absolute/path/to/artifacts --songs-dir /absolute/path/to/authorized-audio
```

Complete generations are atomically published with stable track IDs, row alignment, checksums, feature slices, extraction parameters, durations and frozen transforms. Unsupported, partial, mixed or nonfinite inputs fail before scoring. New extraction uses two-second hard-cut endpoint features; legacy migration records 20-second windows based on the reviewed extraction defaults, since the original arrays had no extraction metadata. Measured RMS/silence metadata supports an explicitly labelled boundary-cost ablation. No loading fallback silently changes the transition algorithm.

## Queue contract

1. Playback eligibility, explicit blocks, uniqueness, locked prefix and mandatory caps are hard rules.
2. Representation uses affirmative likes/acceptance, not a relative top-k acoustic score. Best effort requires explicit selection and reports every deficit.
3. The fair policy improves the least-served listener, then mean utility, then transitions within a declared preference tolerance. A separate `affinity` policy is the numerical research baseline.
4. Full eligible ranking precedes a joint-feasibility protected shortlist. One shared accepted song can cover several listeners. Candidates may expand with an explanation; rules never disappear.
5. An immutable instance freezes coefficients, evidence, candidate scope, policy and history. DP, beam, greedy, MILP and product baselines consume that same instance.
6. A decoded-queue validator checks every returned incumbent, including warm starts and fallbacks. `OPTIMAL`, `FEASIBLE_NOT_PROVEN`, `HARD_INFEASIBLE`, timeout, invalid request and resource failures are distinct outcomes.

A canonical edge is `transition_weight * transition_value - same_folder_penalty * int(same_folder)`. The folder penalty applies only when adjacent tracks share a folder. All algorithms and the UI use those units. Negative acoustic affinity is not an observed dislike. Unknown is not affirmative acceptance. Artist/family limits use explicit metadata, not folder guesses.

Each listener has a stable ID separate from a display name; two people named Alex remain two participants. Seeds are canonicalized and deduplicated. Explicit acceptance stays positive when another taste pocket is added.

## Python API

```python
from music_queue import Listener, Policy, SessionRequest, load_catalog, generate_queue

catalog = load_catalog()
request = SessionRequest(
    listeners=(
        Listener("listener_1", "Alex", tuple(t.id for t in catalog.tracks[:3])),
        Listener("listener_2", "Alex", tuple(t.id for t in catalog.tracks[20:23])),
    ),
    queue_len=5,
    candidate_limit=10,
    method="milp",
    policy=Policy(representation="strict", discovery_budget=0),
)
result = generate_queue(catalog, request)
print(result.status, result.queue, result.proven_optimal)
print(result.per_listener, result.conflicts, result.relaxations)
```

V2 intentionally replaces list-only solver outcomes and user-named score columns. Use `generate_queue(catalog, request)` for orchestration or `solve_instance(instance, ...)` for matched-rule experiments. The original notebook is a historical prototype and is not the current model/API. Unknown request/rule fields are rejected.

## Reproduce evidence

```bash
.venv/bin/python evaluation/benchmark.py
.venv/bin/python evaluation/catalog_benchmark.py  # requires local saved features
.venv/bin/python evaluation/study.py --output output/study --render-audio
```

The committed [benchmark evidence](docs/BENCHMARKS.md) contains 378 synthetic runs and 96 saved-catalog runs, complete instances and CBC logs. Exact DP and both edge formulations agree on the synthetic optima. These are internal-objective/correctness diagnostics, not listening outcomes or production latency guarantees. The original PDF's six comparisons were not independently reproduced because its exact generator/scripts were unavailable.

The study generator makes blank instruments and randomized local excerpts. No ratings are manufactured. Human judgments, consent, a held-out protocol, and later statistical design remain required for the listening-evidence gate.

## Architecture and limits

- `domain.py`, `preferences.py`: stable identities, validated evidence, policy and immutable instances/results.
- `artifacts.py`, `artifact_store.py`, `catalog.py`, `boundary.py`: extraction, manifests, transforms and candidate-level transition signals.
- `candidates.py`: full-ranking reference and joint-feasible protection.
- `objective.py`, `constraints.py`, `validation.py`: one score definition and independent decoded-queue checks.
- `solvers/`: exact subset DP, incremental merged beam/greedy and phase-based MILP with continuous edges.
- `session.py`: revision checks, promises, current-track anchor, cooldowns and confirmed duration history.
- `workbench.py`, `debug_panel.py`, `debug_panel/`: clustering/retrieval views, frozen preparation, local audio streaming and the interactive GUI.
- `evaluation/`, `tests/`: frozen experiments, original audit provenance, regression/property checks and independent-study instruments.

Requests are bounded to eight listeners, twenty slots, thirty candidates and sixty seconds. Exact DP is capped at twenty candidates. The deadline covers preprocessing and solving, with small measured process/validation overhead; it is not a realtime deadline. The server is loopback-only and serializes solves. Dense retrieval remains appropriate for the current 121-track catalog; candidate transition blocks are computed on demand.

[Policy details](docs/POLICY.md) · [Artifacts](docs/ARTIFACTS.md) · [Sessions](docs/SESSIONS.md) · [Rebuild gates](docs/REBUILD_STATUS.md)
