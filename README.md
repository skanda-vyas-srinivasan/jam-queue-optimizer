# Jam Queue Optimizer

Research-heavy prototype for **audio-based music comparison, multi-user candidate retrieval, and constrained queue construction** over a local song catalog.

This repo is not meant to be read as a polished consumer app. The current focus is the modeling substrate for a future collaborative queueing application:

- can audio embeddings recover meaningful local taste structure?
- when do cross-genre links remain musically defensible?
- how should **preference similarity** differ from **transition similarity**?
- where should heuristics stop and exact optimization begin in a queueing pipeline?

The result is a hybrid system:

1. **Retrieve** candidate songs from a local audio catalog using content-based similarity.
2. **Rank / shortlist** candidates for a multi-user room with lightweight heuristics.
3. **Optimize** the final queue with integer programming over the shortlisted songs.

## Research Framing

The motivating question is not simply “can songs be clustered from audio?” The more interesting problem is whether an audio-only comparison space is rich enough to surface:

- local taste pockets rather than only broad genre buckets
- bridge songs that make sense for multiple listeners
- distinctions between “songs I would like” and “songs that actually flow together in sequence”

This repo treats queue generation as a downstream consequence of those representation and retrieval choices. The long-term application idea is a collaborative listening system, but this repository is intentionally centered on the **retrieval + ranking + optimization core** rather than deployment, streaming integration, or product plumbing.

## Current Pipeline

### 1. Audio Representation

Each song is embedded from local audio using `librosa` in [music_queue/artifacts.py](music_queue/artifacts.py):

- MFCC mean/std
- chroma mean/std
- spectral contrast mean/std

This is a **handcrafted baseline**, not a learned embedding model. The design is intentionally simple, interpretable, and cheap enough to iterate on locally.

The artifact builder produces:

- `embeddings.npy`: full-song embeddings for retrieval
- `intro_embeddings.npy`: first 20s embeddings
- `outro_embeddings.npy`: last 20s embeddings
- `song_names.npy`
- `song_folders.npy`

### 2. Retrieval Similarity

In [music_queue/catalog.py](music_queue/catalog.py), full-song embeddings are standardized per feature dimension across the catalog and then compared with cosine similarity.

This gives the main **retrieval similarity** used for:

- nearest-neighbor lookup
- user-level candidate scoring
- room-level ranking

Retrieval is **song-seeded**, not cluster-seeded:

- each user supplies liked songs
- each liked song retrieves nearest neighbors
- candidate sets are merged across users

That choice preserves multi-modal taste better than collapsing a user into one averaged profile too early.

### 3. Transition Similarity

Queue transitions use a different signal than retrieval.

The current transition score is built from intro/outro embeddings:

- segment term: cosine similarity from `outro(song_a)` to `intro(song_b)`
- harmonic term: chroma-only compatibility between `outro(song_a)` and `intro(song_b)`

The blend is currently:

```text
transition_similarity(a, b)
  = 0.85 * segment_transition(a, b)
  + 0.15 * harmonic_transition(a, b)
```

This split came from a central modeling observation:

> songs that are good **preference matches** are not always songs that are good **next songs**.

### 4. Ranking and Shortlisting

The ranking stage in [music_queue/queueing.py](music_queue/queueing.py) is heuristic by design.

Pipeline:

- retrieve a broad candidate pool from nearest neighbors
- compute per-user scores for each candidate
- aggregate into a room score
- preserve some user-specific candidates
- fill the remaining shortlist by global room score

This is where the system balances:

- broad consensus songs
- user-specific local pockets

without pushing the exact solver to work over the full retrieved set.

### 5. Final Queue Optimization

The last stage is an integer program over the final shortlist.

Decision variables:

```text
x[a,t] = 1 if song a is placed in slot t
y[a,b,t] = 1 if song a is followed by song b between slots t and t+1
```

Objective:

```text
maximize
  sum(room_score[a] * x[a,t])
  + transition_weight * sum(transition[a,b] * y[a,b,t])
```

The current formulation jointly chooses:

- which songs appear in the queue
- where they appear
- how transitions are traded against room relevance

Subject to:

- one song per slot
- each song used at most once
- adjacency consistency through `y`
- optional folder caps
- optional user-representation constraints

Important scope note:

> the IP is exact only over the **final shortlist**, not over the entire catalog.

So the overall system is best described as:

**heuristic retrieval + heuristic ranking + exact final-stage optimization**

not end-to-end global optimization.

## Why Integer Programming?

For the current stripped-down objective, a subset-state DP would also be a plausible exact method. The reason this repo uses IP is extensibility:

- queue-level representation constraints
- diversity / folder caps
- future spacing or structural rules

Those are much easier to express and iterate on in an optimization model than in a custom dynamic program.

## Repo Layout

```text
music_queue/
  artifacts.py      audio loading and embedding generation
  catalog.py        similarity matrices and nearest-neighbor lookup
  queueing.py       retrieval, ranking, shortlist logic, greedy/beam/IP solvers
  plotting.py       PCA embedding visualization
  debug_panel.py    local HTTP debug server
  debug_panel/      frontend for interactive analysis

scripts/
  embed_audio.py        rebuild saved artifacts
  embed_audop.py        compatibility alias
  visualize_embeddings.py
  run_queue_demo.py
  run_debug_panel.py

artifacts/
  *.npy                 saved embeddings and catalog metadata
  system_diagram.svg    pipeline diagram

notebooks/
  SimilarityMusicCoder.ipynb   original notebook prototype
```

## Running the Prototype

There is no packaging layer yet, so run from the repo root.

### Dependencies

The project currently relies on:

- Python
- `librosa`
- `numpy`
- `pandas`
- `scikit-learn`
- `plotly`
- `pulp`

### 1. Rebuild artifacts

Run this when:

- embedding code changes
- songs are added or removed
- intro/outro artifact files need regeneration

```bash
venv/bin/python scripts/embed_audio.py
```

### 2. Visualize the embedding space

```bash
venv/bin/python scripts/visualize_embeddings.py --space normalized
```

You can also plot the raw embedding space:

```bash
venv/bin/python scripts/visualize_embeddings.py --space raw
```

### 3. Run the queue demo

```bash
venv/bin/python scripts/run_queue_demo.py --method ip --queue-len 5 --candidate-limit 10
```

Example variants:

```bash
venv/bin/python scripts/run_queue_demo.py --method beam
venv/bin/python scripts/run_queue_demo.py --method greedy
venv/bin/python scripts/run_queue_demo.py --method ip --time-limit 10 --relative-gap 0.05
```

### 4. Run the local debug panel

```bash
venv/bin/python scripts/run_debug_panel.py
```

Then open:

```text
http://127.0.0.1:8765
```

The debug panel is meant for model inspection, not end-user interaction. It exposes:

- embedding-space visualization
- per-user seed song selection
- retrieval and ranked candidate tables
- shortlist inclusion reasons
- queue/user affinity tables
- transition breakdowns

## What Is Actually Working Right Now

The current prototype is already useful for studying:

- whether local audio neighborhoods look musically sensible
- how shared-candidate ranking changes when multiple users are involved
- how queue structure changes when transition scoring is separated from retrieval scoring
- what constraints matter at the final sequencing stage

It is already enough to support:

- controlled local experiments
- queue generation over a fixed catalog
- introspection of failure modes

Natural next directions:

- compare the handcrafted embedding baseline against a learned / pretrained music embedding
- tighten evaluation around nearest-neighbor quality and queue coherence
- improve the semantics of user representation in the final queue
- introduce stronger queue-level structural rules
- connect this research substrate to a more application-oriented multi-user interface

## Reading Order

If you want to understand the system quickly, read in this order:

1. [scripts/run_queue_demo.py](scripts/run_queue_demo.py)
2. [music_queue/catalog.py](music_queue/catalog.py)
3. [music_queue/queueing.py](music_queue/queueing.py)
4. [music_queue/artifacts.py](music_queue/artifacts.py)

For project history and reasoning behind refactors/reversions, see [instructions.md](instructions.md).
