# Jam Queue Optimizer

This is a research-heavy prototype for audio-based music comparison, candidate retrieval for multi-users with varying overlap, and constrained sequencing over a catalog of songs. The result is a hybrid system ...

This repo isn't really meant to be read as a polished consumer app; its current focus is to be the underlying surface for a future collaborative queueing app.


## Motivation

--To be filled later


## Structure

### 1. Audio Representation

Each song is embedded from local audio using librosa using:

- MFCC mean/std
- chroma mean/std
- spectral contrast mean/std

This is a handcrafted baseline, not a learned embedding model. The design is intentionally simple, interpretable, and cheap enough to iterate on locally.

### 2. Retrieval Similarity

During Retrieval, full-song embeddings are standardized using a frozen, saved per-feature transform and then compared with cosine similarity.

Representing each user as a single vector was something I considered early on, but averaging music taste is usually a bad idea. If I have two strong taste pockets, like rage music and dreamy synth-heavy music, the average can place me somewhere in the middle, near a genre like alt-rock which I don't really care about. You end up with an artificial taste profile that smooths over both sides instead of preserving either one. Because of that, it made more sense to let individual-liked songs drive retrieval rather than collapsing the whole user into a single vector.

This gives the main retrieval similarity used for:

- nearest-neighbor lookup
- user-level candidate scoring
- room-level ranking

Retrieval is song-based, not cluster-based:

That choice preserves multi-modal taste better than collapsing a user into one averaged profile too early.


### 3. Transition Scoring

Queue transitions use a different signal than retrieval.

The current transition score is built from intro/outro embeddings:

- segment term: cosine similarity from `outro(song_a)` to `intro(song_b)`
- chroma term: chroma-only cosine similarity between `outro(song_a)` and `intro(song_b)`

Intro/outro features use a shared frozen transform. These are acoustic-affinity signals, not independently validated transition quality.

### 4. Ranking and Shortlisting

The ranking stage is also heuristic by design.

We compute per-user scores over the full eligible catalog and aggregate them into a room score. We preserve a jointly feasible covering selection based on explicit listener acceptance before filling the remaining shortlist by room score.

As a step-by step process:
- Start with the full eligible catalog
- Compute per-user scores for each candidate
- aggregate these per-user scores into a room score
- preserve a selection covering listeners under the joint session rules
- fill the remaining with top candidates as per the global room score.

At this point in iteration, I'm trying not to push the solver to work over the full retrieved set.

### 5. Final Queue Optimization

The last stage can use a mixed-integer program over the final shortlist, with exact subset DP and heuristic alternatives.

**Decision variables**

- $x_{a,t} \in \{0,1\}$: song $a$ is assigned to queue slot $t$
- $y_{a,b,t} \in [0,1]$: song $a$ is followed by song $b$ between slots $t$ and $t+1$; integral placements and linking equalities force these continuous variables to 0 or 1

**Objective**

The default fair policy improves the least-served listener, then mean utility, then transitions within the agreed preference tolerance. The `affinity` research policy uses the scalar objective below.

Maximize internal affinity:
- total room relevance of selected songs
- plus transition-weighted quality of adjacent song pairs

With the optional same-folder penalty set to zero, equivalently,

- maximize $\sum r_a x_{a,t} + \lambda \sum c_{ab} y_{a,b,t}$

where:
- $r_a$ is the room score of song $a$
- $c_{ab}$ is the transition score from song $a$ to song $b$
- $\lambda$ controls the importance of transitions

**Constraints**

- Exactly one song is placed in each queue slot
- Each song can appear at most once
- Exactly one transition is chosen for each adjacent slot pair
- If song $a$ is placed in slot $t$, it must connect to exactly one song in slot $t+1$
- If song $b$ is placed in slot $t+1$, it must be reached from exactly one song in slot $t$
- Playback blocks, locked songs, mandatory caps and strict acceptance requirements are enforced jointly

with:
- $A$: shortlisted songs
- $T$: queue slots
- $P$: adjacent slot indices

Important scope note:

> an optimality certificate covers only the final shortlist, not the entire catalog. Time-limited feasible queues are reported separately from proven optima.

So the overall system is best described as:

song-based retrieval + policy-grounded shortlisting + validated sequencing, with exact reference methods.

At this point, the methods provide an optimization baseline; preference prediction and better listening still need independent judgments. Machine Learning solutions for retrieval and ranking are potential options.

### Optimization Reasoning

The sequencing idea was loosely inspired by Spotify's own mix feature, where songs are arranged to sound smoother when transitioning.

Other approaches I thought about for the sequencing + room-score problem were beam search and dynamic programming.

Beam Search: Beam search was a great baseline since it's fast and easy to compare against. However, when it comes to optimality, there is no guarantee. It throws away potentially better sequences early due to the pruning.

Dynamic Programming: Fits the current formulation well and is implemented as an exact subset-DP baseline; however, I plan to add more global constraints as development continues. This will be a lot more annoying to extend cleanly with DP.

For the interactive GUI, playback and step-by-step usage, see the [workbench guide](docs/WORKBENCH.md).
