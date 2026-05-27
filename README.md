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

During Retrieval, full-song embeddings are standardized per feature dimension across the catalog and then compared with cosine similarity.

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
- harmonic term: chroma-only compatibility between `outro(song_a)` and `intro(song_b)`

### 4. Ranking and Shortlisting

The ranking stage is also heuristic by design.

After retrieval, we compute per-user scores for each candidate and aggregate them into a room score. We also preserve some user-specific candidates to balance songs with broad appeal while also including some songs with user-specific local pockets.

As a step-by step process:
- Retrieve a broad candidate pool
- Compute per-user scores for each candidate
- aggregate these per-user scores into a room score
- preserve some spots in our shortlist for user-specific candidates
- fill the remaining with top candidates as per the global room score.

At this point in iteration, I'm trying not to push the solver to work over the full retrieved set.

### 5. Final Queue Optimization

The last stage is an integer program over the final shortlist.

**Decision variables**

- $x_{a,t} \in \{0,1\}$: song $a$ is assigned to queue slot $t$
- $y_{a,b,t} \in \{0,1\}$: song $a$ is followed by song $b$ between slots $t$ and $t+1$

**Objective**

Maximize queue quality:
- total room relevance of selected songs
- plus transition-weighted quality of adjacent song pairs

Equivalently,

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

with:
- $A$: shortlisted songs
- $T$: queue slots
- $P$: adjacent slot indices
  
Important scope note:

> the IP is exact only over the final shortlist, not over the entire catalog.

So the overall system is best described as:

heuristic retrieval + heuristic ranking + exact final-stage optimization.

At this point, heuristics deliver strong results for retrieval and ranking, albeit not perfectly. Machine Learning solutions for both are potential options.

### Optimization Reasoning

The sequencing idea was loosely inspired by Spotify's own mix feature, where songs are arranged to sound smoother when transitioning.

Other approaches I thought about for the sequencing + room-score problem were beam search and dynamic programming.

Beam Search: Beam search was a great baseline since it's fast and easy to compare against. However, when it comes to optimality, there is no guarantee. It throws away potentially better sequences early due to the pruning.

Dynamic Programming: Fits the current formulation well; however, I plan to add more global constraints as development continues. This will be a lot more annoying to extend cleanly with DP.


