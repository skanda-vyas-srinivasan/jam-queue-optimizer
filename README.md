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

Also, the song
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


