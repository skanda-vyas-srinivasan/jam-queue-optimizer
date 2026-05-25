# Multi-User Party Music Queue

This repo started as a notebook experiment. The code is now split so you can keep iterating without burying everything inside the notebook or a flat repo root.

## Project layout

- `artifacts/`: saved embeddings, song metadata arrays, and generated plots.
- `music_queue/artifacts.py`: audio loading and embedding generation.
- `music_queue/catalog.py`: loads saved arrays and exposes similarity lookups.
- `music_queue/paths.py`: central repo paths so file moves do not break the code.
- `music_queue/queueing.py`: candidate retrieval, room scoring, and queue builders.
- `music_queue/plotting.py`: PCA projection and 3D embedding plot generation.
- `notebooks/SimilarityMusicCoder.ipynb`: original notebook prototype.
- `scripts/`: runnable helper scripts for rebuilds, plotting, demos, and smoke tests.

## Local workflow

Build or rebuild artifacts:

```bash
venv/bin/python scripts/embed_audio.py
```

Visualize the embedding space:

```bash
venv/bin/python scripts/visualize_embeddings.py
```

Run the current queue pipeline with a sample room:

```bash
venv/bin/python scripts/run_queue_demo.py
```

## Notes

- The saved `.npy` files are enough for retrieval and queue generation. You only need the raw audio files when rebuilding embeddings.
- Room inputs can use either the saved song stem or a filename like `foo.mp3`; the catalog resolves both to the stored song ID.
- `pulp` is installed in the local venv, and the demo now defaults to the IP solver.
- `beam` and `greedy` are still available as baselines or fast fallbacks: `venv/bin/python scripts/run_queue_demo.py --method beam`
- If you want bounded-latency IP instead of exact-best-effort IP, use `--relative-gap 0.05` or a lower `--time-limit`.
