# Jam Queue Optimizer Notes

## What The Project Originally Was

This project started as a notebook-first prototype for a **multi-user music queue system** over a **local audio catalog**.

The original idea was:

- each user in a room provides a few liked songs
- those liked songs seed retrieval over a catalog of embedded local songs
- the system ranks candidate songs for the room
- a queue optimizer picks an ordered set of songs that balances room preference and smooth transitions

The first working version lived entirely in [notebooks/SimilarityMusicCoder.ipynb](/Users/skandavyassrinivasan/mlproj/notebooks/SimilarityMusicCoder.ipynb).

## What The Notebook Did

The notebook had these stages:

1. **Load songs from a folder**
- iterate through audio files by folder/genre

2. **Build one embedding per song**
- use `librosa`
- extract:
  - MFCC
  - chroma
  - spectral contrast
- summarize each feature by `mean` and `std` over time
- concatenate into one fixed vector per song

3. **Compute song similarity**
- cosine similarity over the full-song embedding vectors

4. **Retrieve room candidates**
- each user seeds retrieval with liked songs
- nearest neighbors are gathered per liked song
- duplicate retrieval from the same user keeps the strongest similarity

5. **Score candidates for the room**
- each candidate is scored against each user's liked songs
- room score is the average of per-user scores

6. **Build a queue**
- first there was a simple greedy queue builder
- then a more serious integer-programming queue solver was added

## What The Original Baseline Embedding Was

The baseline feature vector for each song was:

- MFCC mean/std
- chroma mean/std
- spectral contrast mean/std

This is the embedding currently implemented in [music_queue/artifacts.py](/Users/skandavyassrinivasan/mlproj/music_queue/artifacts.py).

That baseline is simple, interpretable, and reasonably fast to compute for the current catalog.

## Why The Repo Was Refactored

The notebook worked, but it was hard to iterate on because:

- model logic was trapped inside notebook cells
- embedding, retrieval, scoring, and queueing were mixed together
- helper scripts were not reusable

So the repo was reorganized into:

- [music_queue/](/Users/skandavyassrinivasan/mlproj/music_queue): reusable package code
- [scripts/](/Users/skandavyassrinivasan/mlproj/scripts): runnable helpers
- [artifacts/](/Users/skandavyassrinivasan/mlproj/artifacts): saved arrays and plots
- [notebooks/](/Users/skandavyassrinivasan/mlproj/notebooks): original notebook

## Main Structural Changes Made

### 1. Code modularization

The notebook logic was split into:

- [music_queue/artifacts.py](/Users/skandavyassrinivasan/mlproj/music_queue/artifacts.py)
  - audio loading
  - embedding generation

- [music_queue/catalog.py](/Users/skandavyassrinivasan/mlproj/music_queue/catalog.py)
  - artifact loading
  - similarity matrix
  - nearest-neighbor lookup

- [music_queue/queueing.py](/Users/skandavyassrinivasan/mlproj/music_queue/queueing.py)
  - multi-user retrieval
  - room scoring
  - greedy, beam, and IP queue builders

- [music_queue/plotting.py](/Users/skandavyassrinivasan/mlproj/music_queue/plotting.py)
  - PCA plot generation

### 2. Helper scripts

The notebook functionality was given script entrypoints:

- [scripts/embed_audio.py](/Users/skandavyassrinivasan/mlproj/scripts/embed_audio.py)
- [scripts/embed_audop.py](/Users/skandavyassrinivasan/mlproj/scripts/embed_audop.py)
- [scripts/visualize_embeddings.py](/Users/skandavyassrinivasan/mlproj/scripts/visualize_embeddings.py)
- [scripts/run_queue_demo.py](/Users/skandavyassrinivasan/mlproj/scripts/run_queue_demo.py)

### 3. IP queueing path made primary

The queue optimizer in [music_queue/queueing.py](/Users/skandavyassrinivasan/mlproj/music_queue/queueing.py) was cleaned up so integer programming became the main queue-building path, with beam retained as a comparison/fallback.

### 4. Name resolution cleanup

The catalog was updated so song references can resolve both:

- stored song stems
- filename-like inputs such as `foo.mp3`

This makes room dictionaries easier to write.

## Similarity Change That Stayed

One important similarity change was kept:

- the embedding dimensions are **standardized per feature dimension across the catalog**
- cosine similarity is then computed on the standardized embeddings

This lives in [music_queue/catalog.py](/Users/skandavyassrinivasan/mlproj/music_queue/catalog.py).

### Effect

This changed nearest neighbors and room scores noticeably.

The intention was good:

- prevent raw feature scales from dominating cosine similarity
- make dimensions contribute more fairly

This change stayed because it is lightweight and conceptually sound.

## Script Behavior Change

During the refactor, the old embedding script lost its per-song progress output.

That made rebuilds look frozen, even when they were working.

This was fixed by restoring:

- total song count
- per-song progress logging
- final elapsed time

This currently lives in [music_queue/artifacts.py](/Users/skandavyassrinivasan/mlproj/music_queue/artifacts.py) and [scripts/embed_audio.py](/Users/skandavyassrinivasan/mlproj/scripts/embed_audio.py).

## Visualization Change

[scripts/visualize_embeddings.py](/Users/skandavyassrinivasan/mlproj/scripts/visualize_embeddings.py) was extended so you can view:

- raw embedding space
- normalized embedding space

This was added to make the similarity change inspectable.

## Feature-Expansion Experiment That Was Reverted

A later retrieval experiment attempted to replace the simpler baseline with a richer weighted feature design:

- timbre block
- harmony block
- energy block
- blockwise cosine similarity with manual weights

Additional features included ideas like:

- spectral centroid
- spectral bandwidth
- spectral rolloff
- zero crossing rate
- RMS
- onset strength
- tonnetz

### Why It Was Tried

The goal was to make audio similarity more expressive while still staying in `librosa`.

### What Happened

- rebuild time increased dramatically
- preprocessing went from roughly a couple of minutes to roughly **14+ minutes** on the current 121-song catalog
- nearest neighbors changed, but the gain was not obviously worth the extra cost
- clustering already felt acceptable in the simpler baseline

### Decision

This experiment was **reverted**.

The repo was intentionally returned to the earlier simpler embedding:

- MFCC + chroma + spectral contrast
- mean/std pooling
- standardized full-song cosine similarity

That is the current baseline again.

## Current Model State

Right now the model is:

- local audio catalog
- full-song `librosa` embedding
- standardized cosine similarity
- nearest-neighbor candidate retrieval
- multi-user room scoring
- integer-programmed queue optimization

It is still a **baseline model**, not a final polished recommender.

## Why The Project Is Being Treated As Local/Audio-First

There was discussion about linking the project tightly to Spotify.

That direction was deprioritized because the part that is actually interesting here is:

- audio similarity
- local content-based retrieval
- queue optimization

So the project is currently being treated as:

- an **audio similarity project first**
- a **queue optimization project second**

## Recommended Way To Read The Repo

If you want to trace the project quickly, read these files in this order:

1. [scripts/run_queue_demo.py](/Users/skandavyassrinivasan/mlproj/scripts/run_queue_demo.py)
2. [music_queue/catalog.py](/Users/skandavyassrinivasan/mlproj/music_queue/catalog.py)
3. [music_queue/queueing.py](/Users/skandavyassrinivasan/mlproj/music_queue/queueing.py)
4. [music_queue/artifacts.py](/Users/skandavyassrinivasan/mlproj/music_queue/artifacts.py)

## Current Open Modeling Priorities

After the revert, the current likely next steps are:

1. inspect and validate retrieval neighbors under the simpler standardized baseline
2. separate retrieval similarity from transition similarity
3. improve transition modeling
4. later add fairness/diversity constraints

