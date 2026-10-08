# Interactive listening workbench

Run `.venv/bin/python scripts/run_debug_panel.py` and open **http://127.0.0.1:8765**. The workbench uses the existing versioned catalog and serves audio from this computer. It needs no Node build or external frontend service. For a different catalog, supply `--artifact-dir /path/to/features --songs-dir /path/to/audio`.

## Work through the pipeline

1. **Library & clusters:** choose raw or frozen standardized coordinates, a feature family, group count and 2D/3D. **Form clusters** runs seeded K-means on the chosen feature vectors; PCA is used only for display. Click points to inspect/preview tracks. In 2D, the box/lasso toolbar selects groups. Library checkboxes and cluster-count buttons also select tracks.
2. Rename groups, assign selected tracks to an existing group, or use **New group from selection**. Choose a listener and evidence type below the library and **Add evidence**. These edits organize the workspace; they do not silently change the preference model or declare that acoustic neighbors are accepted songs.
3. **Listener profiles:** add/remove people, rename them, and add likes, acceptance, ordinary dislikes or blocks. Duplicate display names remain separate people. **Load demo profiles** provides artificial example seeds to try the pipeline immediately.
4. **Retrieval & ranking:** choose a listener and use their likes, or retrieve from map selections. Compare closest-seed and top-two acoustic neighbors. Preview a recommendation before explicitly adding it as liked. Set policy and **Prepare candidates** to inspect the full eligible ranking, each listener's score/evidence, shortlist reasons and hard exclusions.
5. **Sequence & play:** choose a method and **Build queue**. Static methods use that exact frozen prepared instance. Profile/policy changes invalidate preparation. Inspect coverage, the directed transition matrix, phase certificates and returned edges; **Play queue** loads the persistent player. Native controls provide pause, seek and volume; previous/next/stop navigate the queue. Individual previews are available throughout.
6. Queue arrows compare a manual order in static mode. The server validates it and removes the optimality claim. Export the result or the entire workspace as JSON.

The browser saves profiles, editable groups, retrieval seeds and settings. It does not restore playing queues, solver snapshots or live sessions across reloads. Import validates stable track IDs and complete group partitions. **Form clusters** explicitly replaces the group assignment; export first to retain alternatives.

## Rolling playback

**Start session** creates in-memory server history. **Build queue** then uses membership, history, cooldowns and the next-track promise directly. Apply profile edits explicitly before replanning. Session transition diagnostics reflect the actual generated order; a static shortlist matrix is not reused as session evidence.

**Play queue** binds playback to a revision. At track end/skip/stop, the client submits observed playing seconds, capped at the track's duration. Pauses and seeking do not manufacture exposure. Previews never count as session service. Media events provide approximate local playback observations; they do not establish that a person listened or liked a song. Rejected stale revisions stop advancement.

Stop the loaded session queue before membership updates, releasing a promise or replanning. A partial stop records partial exposure; a zero-time stop leaves the promise intact. **Release next promise** explicitly permits omitting an unplayed promised song. Previous-track replay and manual ordering are disabled in session mode. **Use static mode** retains existing history in the server and returns to frozen preparation.

Sessions disappear on server restart. Reloading during playback may lose unsubmitted exposure, so the page prompts before leaving a session with observed playback. Full-track endpoints remain the sequencing model; skipping midway changes the actual audible boundary. Playback uses hard cuts with normal browser/request overhead, without crossfades or a gapless-playback guarantee.

## Stage semantics

- Clusters use the chosen family/transform. Manual groups are organizational, not preference evidence or hidden hard constraints.
- Retrieval uses full-song frozen standardized cosine geometry and excludes query seeds. It does not impose an early cutoff on room ranking.
- Ranking uses the predictor while preserving affirmative acceptance and dislikes. Blocks/playability determine eligibility; joint feasibility protects candidates under actual caps.
- Preparation stores an immutable instance: at most eight snapshots, expiring after one hour. All static solver comparisons share its coefficients, evidence, candidates and policy. Further preparation cannot mutate it.
- Audio streams only known catalog sources within the configured music root, with symlink containment checks. HTTP byte ranges support seeking. Local availability/browser format support determine playability.

## Verification

`.venv/bin/python -m pytest` passes **73 tests**. For client development, `npm ci --ignore-scripts` then `npm test` passes **10 tests**; `npm run format:check` checks the frontend. Node dependencies are development-only. CI includes both suites but has not run remotely for this change.

The real 121-track smoke check formed six groups, ranked all tracks, prepared ten candidates, produced a validated optimal queue and served an MP3 byte range. Client tests cover navigation, escaping, group selection/editing, explicit evidence, frozen preparation, manual proof removal, policy invalidation, queue advancement, partial session skips, pauses and seeks. DOM tests simulate media events; they do not render a browser or play audible sound.

Visual browser verification is pending. Automatic approval review denied browser access during the earlier rebuild; permission to reopen this GUI has been requested. No alternate browser route bypassed that denial.
