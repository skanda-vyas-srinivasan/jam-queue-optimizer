# Jam Queue Optimizer: independent audit and rebuild plan

Reviewed repository: `skanda-vyas-srinivasan/jam-queue-optimizer`  
Reviewed commit: `e637be5f78567ea24f04cf0734286f357fef7d74`  
Review date: October 8, 2026  
Input report: *Jam Queue Optimizer: Objective model review*, October 7, 2026, 10 pages.

## 1. Verdict and evidence boundary

The supplied review is substantially sound. Its central conclusion is the right one: the repository demonstrates optimization of an explicit acoustic-affinity objective, not independently established improvement in shared listening. Its findings about candidate exclusion, representation rules, cap relaxation, separate transition transforms, inconsistent penalty units, and unused warm-start preparation agree with the inspected code.

There are two important qualifications. First, a negative standardized cosine similarity is not an observed dislike. Second, the six reported solver comparisons and their timings remain the supplied review's results, not independently reproduced benchmark measurements. Its scripts and complete generated room definitions are not supplied in the PDF. A fixed random seed alone does not fully specify an experiment.

For this audit, the core Python package, embedding CLI, and debug-panel code were inspected through the GitHub connector at the pinned commit. Twenty-four synthetic diagnostic checks were executed on isolated source extracts and a catalog adapter preserving the relevant lookup/scoring behavior. These include eight checks of previously reported mechanisms and sixteen additional cases. Ten independently constructed SciPy/HiGHS formulation cases were also compared with exhaustive enumeration. Those tests are not execution of the original PuLP/CBC pipeline. The saved 121-song catalog was not loaded, audio was not regenerated, and there were no listener experiments. Network/dependency availability prevented running the original CBC setup here.

The attached `diagnostics.py` can instead execute actual upstream functions when given a local checkout of the exact reviewed commit. This mode was provided for reproducibility but was not executed here. No repository files were changed or pushed.

A correction to the earlier informal assessment: assigning initial variable values does not itself enable CBC warm-starting. The code prepares beam values but omits `warmStart=True`. Even enabling that option is insufficient without checking that the beam solution satisfies the IP's additional representation rules. [C1, W1]

## 2. Start with the actual listening problem

The following is a proposed initial product policy, not a claim about what users have already requested or validated.

### Who uses it?

Two to five friends sharing a speaker for roughly 30 to 60 minutes, who want less effort managing a playlist. Start with locally playable tracks. This is not initially an autonomous DJ, universal streaming catalog, workplace policy engine, or music-discovery research platform.

### What makes a queue good?

It respects explicit session exclusions, provides each listener with music they have affirmatively accepted, avoids long stretches of unwanted music, and reduces manual queue management. Within those protections, improve broad appeal and then transitions. Discovery is a separate, opt-in objective, not an accidental consequence of acoustic similarity.

### What wins when goals conflict?

Make this a policy contract, not a collection of unexplained weights:

1. Playback eligibility, agreed explicit blocks, locked songs, and mandatory limits are hard rules.
2. Confirmed listener representation is either a hard promise or an explicitly authorized best-effort goal. The interface must say which.
3. Improve the least-served listener, then aggregate preference, subject to the preceding guarantees.
4. Improve transitions within a stated tolerance for preference loss. Discovery has its own agreed budget.

A disliked song is not automatically a global veto. Let the session distinguish ordinary dislikes from explicit do-not-play requests. Conversely, an uncalibrated prediction must not override a confirmed block.

### Why not just take turns?

The proposed advantage is reduced curation effort and better identification of songs several people accept, while retaining each listener's control. Round-robin is a legitimate fallback and a serious product baseline. If automatic generation is not preferable in listening quality, effort, or both, the product hypothesis needs revision. This does not invalidate a separately useful optimization benchmark.

Keep the two claims distinct: mathematical correctness can be established with synthetic instances and proofs; improved listening requires independent listener evidence. Do not require a consumer app to justify every algorithmic experiment, and do not use solver optimality as a substitute for product evidence.

## 3. Assessment of the supplied review

| Report claim | Independent assessment | Required qualification or action |
|---|---|---|
| The problem context and priority order are unspecified. | Valid from the documentation and implemented policy. | Adopt a provisional policy and test it, rather than assuming a road trip or party is already the intended use. |
| Top-two seed similarity is not calibrated preference. | Valid. A synthetic opposite-seed example reproduces the reduction from approximately 1 to 0. | Known positive evidence should not be overwritten by this pooling heuristic. Maximum similarity and clustering are alternatives to evaluate, not automatic fixes. |
| The early retrieval cutoff can exclude a minority listener. | Valid. A counterexample using actual cosine geometry reproduces the mechanism. | Protect confirmed options before any cutoff. The library default is 40 candidates, while the debug panel defaults to 50; the problem is not specific to 40. |
| Top-k representation does not establish acceptance. | Valid. | Negative affinity is not proof of dislike either. The failure is lack of affirmative acceptance evidence. |
| Explicit folder caps can disappear. | Valid from the helper and its call sites. | Separate strict limits from soft preferences and disclose every authorized relaxation. |
| Representation feasibility ignores caps. | Valid. The helper can return true when exhaustive checking of the joint rules finds no feasible selection. | Check the actual combined problem. |
| Infeasible representation can be silently omitted. | Valid from the IP construction branch. | Return an explicit conflict or optimize declared slack. Never silently remove every user's protection. |
| Separate intro/outro standardization can make identical segments incompatible. | Valid. A synthetic identical raw pair scores approximately -1. | Separate transforms are not universally mathematically forbidden, but they are inappropriate for a claimed common-coordinate comparison unless explicitly justified. |
| The adjacency penalty differs between IP and scorer/beam. | Valid algebraically: the IP subtracts lambda times the penalty; the scorer subtracts the penalty itself. | Use one edge-cost definition throughout. |
| Warm-start values are unused. | Valid from solver configuration and official documentation. | Validate the starting queue against all IP constraints, enable warm-start explicitly, and inspect acceptance in solver logs. |
| IP can optimize future transitions and coupled rules. | Valid mathematical capability. | Sorting and finite-width beam do not offer its general certificate, but the strongest small-instance exact baseline has not been exhausted. |
| Six examples show beam matching IP and greedy losing objective. | Plausible and appropriately scoped in the PDF, but not independently reproduced here. | Publish exact instances, scripts, objective components, logs, versions, and repeated measurements. Do not extrapolate six examples to production or listener superiority. |
| The method is not automatically exact under time/gap limits. | Valid. | Distinguish a feasible incumbent, termination reason, proof status, and the candidate universe covered by the certificate. |

The PDF's retrieval-ablation result is not a contradiction of optimization: it changes the selected shortlist, so it need not preserve a nested feasible set. Its reported percentage objective differences are not percentage increases in enjoyment, and percentage comparisons are fragile when an objective can be negative or near zero.

Sources: supplied PDF pages 2 to 7; code [C1-C5]; solver documentation [W1-W2].

## 4. Additional issues and how to fix them

### 4.1 Listener names can corrupt the numerical model

`rank_room_candidates` builds rows containing `song`, `folder`, and `room_score`, then expands `**per_user`. A listener with a reserved name overwrites that field. In the synthetic test, a real group mean of 0 became approximately 1 when a listener was named `room_score`. A listener named `song` replaced track names with numbers. Such listeners are also excluded from representation-column detection.

The frontend creates a room object keyed by display name. Duplicate display names overwrite each other. Users without seeds are silently omitted from a simulation when other users remain. These are consequential for a fairness feature, not merely cosmetic defects. [C1, C6]

**Fix:** separate stable listener IDs from display names. Store user utilities in a dedicated matrix or long-form relation keyed by listener ID and track ID. Validate room membership explicitly. Empty profiles should trigger a clear policy, not silently remove people. Reject malformed profiles, including strings masquerading as sequences of track IDs.

**Acceptance test:** renaming a listener does not change numerical results; two people named Alex remain two people; adding an empty participant cannot silently shrink the room.

### 4.2 Seed duplication changes scores without adding information

With two opposite liked tracks, a candidate's top-two mean is approximately 0. Repeating the favorable seed changes the score to approximately 1. The frontend prevents simple duplicate clicks, but the public Python/API path does not canonicalize and deduplicate inputs. Aliases can represent the same track more than once. More distinct seeds also change the order-statistic distribution of maximum/top-k similarity, so equal room weights are not equivalent to calibrated influence. [C1]

**Fix:** canonicalize track IDs and deduplicate before retrieval or scoring. Represent intentionally stronger preference as an explicit, bounded weight, not repeated rows. Preserve known positive labels separately from predicted affinity. Evaluate profile-size sensitivity.

**Acceptance test:** duplicate and alias-equivalent seed inputs leave results unchanged unless an explicit preference weight changes.

### 4.3 Shortlist preservation spends coverage inefficiently

The preservation routine allocates distinct new songs to successive users without crediting a song already selected for all users it covers. A test with one track accepted by A and B, another redundant A/B track, and one C-only track selected both A/B tracks and excluded C, despite an alternative two-track shortlist covering everyone.

The preserve budget is also `round(shortlist_size * 0.30)`, not a function of the number of listeners needing protection. User priority depends on maximum score, and ties depend on ordering. This can systematically favor already well-supported profiles. [C1]

**Fix:** define coverage over stable affirmative acceptance sets. Preserve a feasible covering selection, allowing one song to count for multiple people. Distinguish indispensable candidates from optional high-score candidates. If the shortlist cannot contain a feasible covering selection, expand it or return a clear resource-policy conflict.

**Acceptance test:** a shared accepted song credits both listeners. Permuting listener input order cannot change achieved fairness, except an explicitly documented tie policy.

### 4.4 Candidate selection ignores sequencing value

A relevance-only cutoff can discard a track that makes the best transition. In a controlled pair-cost example, the best two-track objective rose from 0.76 to 1.25 when a slightly lower-relevance transition endpoint was admitted. This is a synthetic objective example, not an observed listening gain.

Relative top-k representation sets also change when candidates change. Therefore candidate expansion can introduce new restrictions as well as new choices. The solver is not necessarily optimizing the same problem after expansion. [C1]

**Fix:** freeze the scoring transform, objective version, acceptance evidence, and session rules during a solve request. Retain incumbent tracks during expansion. Add transition-relevant candidates or use solver-aware expansion only after a simple full-ranking baseline is measured. Treat relative top-k membership as a diagnostic, not a moving hard promise.

**Acceptance test:** with frozen coefficients and rules, expanding a nested candidate set containing the incumbent cannot reduce the proven optimal objective. Do not apply this test when changing the policy itself.

### 4.5 The prepared beam solution need not be IP-feasible

Beam and greedy do not implement the IP's user-representation constraints. A synthetic beam queue selected A's two best tracks while missing B's required track, even though a jointly representative queue existed. Consequently `warmStart=True` alone does not fix the warm-start path. The defaults also differ: greedy has a nonzero same-folder penalty while IP and beam default to zero. The debug panel can display greedy scores using zero penalty even when greedy selected with 0.10. [C2, C5]

**Fix:** build one immutable problem instance before calling any solver. Implement constraint-matched heuristic construction, feasibility-preserving repair, or a small feasibility solve. Validate all proposed incumbents independently. Use the same score function in the UI and every algorithm.

**Acceptance test:** every warm start and fallback satisfies all hard rules of the exact model being solved. Comparisons use identical candidates, penalties, representation rules, and queue lengths.

### 4.6 A trivial feasibility question can trigger an exponential scan

`user_representation_feasible` scans integers through `2**n_songs`, even though only small subsets are relevant. A 20-song one-slot case requiring the last-indexed track visits 524,289 subset values. Moving the same required track to index zero reduces that to two. The algorithm can block before CBC's time limit even starts. This is much more urgent than optimizing solver search. [C1-C2]

**Fix:** remove the ad hoc exhaustive precheck. Use the actual model, or a selection-only feasibility model with all applicable constraints. For a pure coverage diagnostic with very few users, dynamic programming over user-coverage masks is another option, but it must not pretend to check artist caps or other missing rules. Enforce an end-to-end request budget, including candidate building, modeling, initialization, and validation.

**Acceptance test:** performance cannot depend exponentially on a harmless track-index permutation. Timeout before a feasible solution means unknown/no solution found, not proven infeasible.

### 4.7 Track identity is not robust

Tracks are identified by file stems and case-folded aliases. Equal stems overwrite lookup entries; case-distinct stems can resolve to the first alias rather than the intended track. The supplied report says the saved catalog has unique names, so this is a demonstrated edge-case failure, not a claim that its existing 121 rows are already corrupted. [C3-C4]

**Fix:** introduce stable track IDs, explicit source URI/path, recording-family ID, artist metadata, duration, and optional content hashes. Display names should never be identifiers. Deduplicate exact audio and handle alternate recordings separately from display-name collisions.

**Acceptance test:** two distinct recordings with the same title remain addressable. Reordering the catalog preserves identity and all aligned metadata.

### 4.8 Feature files do not declare their schema

The embedding CLI supports `--n-mfcc`, but transition scoring slices chroma assuming 40 MFCCs. With 20 MFCCs, the embedding has 78 entries and the hardcoded chroma slice starts at 80, causing an empty-feature error. Other dimensions can silently compare the wrong feature block. Intro/outro row counts and matching feature schemas are not checked against the full catalog. A missing single segment array silently changes transition scoring to whole-song similarity. [C3-C4, C7]

**Fix:** use a versioned artifact manifest containing feature names and slices, dimensions, extraction parameters, package versions, track IDs, row order, transform version, and checksums. Validate shapes, finiteness, IDs, and complete artifact sets on load. Write a complete artifact generation to a temporary directory and publish it atomically. A fallback must be explicit and reflected in result metadata.

**Acceptance test:** nondefault supported schemas work; unsupported or inconsistent schemas fail before scoring; mixing generations cannot silently associate one track with another's features.

### 4.9 Catalog-dependent normalization changes old predictions

Means and standard deviations are refitted over the catalog at load time. Adding an unrelated track can change the similarity between two unchanged tracks. In a constructed one-dimensional geometry replicated across features, a fixed pair's cosine flips from approximately -1 to +1 after adding an outlier. This is a stability and calibration problem, not proof that every transductive normalization scheme is invalid. A constant catalog can also produce zero standardized vectors, so a known seed's acoustic self-affinity becomes zero while retrieval injects a seed score of one. [C3]

**Fix:** freeze and version fitted transforms for an evaluation/model generation. Explicitly decide whether catalog-wide transductive adaptation is allowed. Recalibrate and rebenchmark when changing the transform. Define zero-vector handling and keep known preference evidence separate from cosine values.

**Acceptance test:** adding tracks with a frozen transform does not change old pair scores. A transform upgrade is recorded as a model change.

### 4.10 The transition feature does not specify an actual playback transition

A 20-second pooled segment vector says little about the exact audible boundary. There is no explicit policy for hard cuts, gaps, or fixed crossfades, and no representation of loudness jumps, beat alignment, leading/trailing silence, or whether the first queue track follows currently playing audio. Whole-vector cosine already includes chroma, so the additional chroma term is a reweighting of overlapping evidence, not independent confirmation. Standardization equalizes individual feature scales, not feature families: the current vector has 80 MFCC, 24 chroma, and 14 contrast dimensions. [C3-C4]

**Fix:** define the playback operator first. Extract features at its actual audible boundaries, handle silence and loudness, and evaluate transition pairs rendered with that operator. Compare shared-transform cosine, a simple boundary-feature cost, and no sequencing. Add tempo/key features only when the intended playback behavior and independent judgments justify them. Rename harmonic similarity to a description of the measured feature until validation supports a stronger label.

### 4.11 A five-song solution is not a fair listening session

Selection-level representation ignores waiting time, song duration, current playback, previously served listeners, repeat tracks across calls, and membership changes. One short acceptable track can satisfy a count constraint while the rest of the session is strongly unwanted. A queue can put the minority listener's only acceptable track last every time. Optimizing fresh windows can repeatedly reset any apparent fairness. [C2]

**Fix:** add an explicit session state only after the static contract is correct. Track played duration, recent tracks/artists, confirmed acceptable exposure, time since acceptable music, active listeners, and the currently playing track. Reoptimize the unfixed tail with a locked short prefix. Distinguish count-based representation from duration-based exposure. Model a first-edge transition from the current track.

**Acceptance test:** consecutive windows cannot erase service debt. Joining/leaving does not restart existing listeners' histories. An already promised next track is stable unless an explicit override occurs.

### 4.12 Scaling and operational boundaries are undeclared

The catalog eagerly constructs several full pairwise similarity matrices, so storage grows quadratically. Beam repeatedly copies sequences/sets and rescans entire prefixes for scoring. The debug server accepts requests without a production authentication/resource-control layer, although it correctly defaults to loopback. Artifact loading enables pickle for names and folders. NumPy documents the risks of loading untrusted pickled arrays; Python documents that `http.server` is not a production server. [C3-C5, W3-W4]

**Fix:** for the current small catalog, prefer simplicity and measure before adding infrastructure. For growth, compute only needed candidate transition blocks and use vectorized retrieval before considering approximate indexing. Bound request sizes, candidate counts, user counts, horizons, and solver concurrency. Keep the debug panel local. Load string arrays with `allow_pickle=False` or use a non-pickled metadata format. Validate inputs independently of HTML controls.

### 4.13 Reproducibility and distribution need deliberate boundaries

The inspected tree contains real MP3 files alongside code, while the visible project structure has no dependency/solver lockfile or substantive test suite beyond an import smoke check. This audit does not establish who owns redistribution rights to those audio files. PuLP's current migration guide documents breaking changes affecting exactly the solver API used here, including variable creation, solve statuses, and CBC configuration. [C8, W2]

**Fix:** pin a tested environment and solver binary version before comparing methods. Treat a PuLP migration as a separate tested change. Publish synthetic features and appropriately licensed small fixtures for tests. Confirm distribution permissions for all published audio and avoid requiring a large music download for a code checkout. Do not rewrite repository history or remove shared assets without a separate deliberate owner decision. Store listener judgments with explicit consent and minimal identifying information.

## 5. Target architecture

Keep this a small Python package, not a microservice system. Establish a few strong boundaries:

```text
Track catalog + versioned audio artifacts
                 |
Session request + explicit listener evidence
                 |
Candidate builder + feasibility-preserving shortlist
                 |
Immutable QueueInstance
                 |
Beam / exact subset DP / MILP solver
                 |
Independent validator + canonical scorer
                 |
QueueResult + explanation + session-state update
```

Suggested modules:

- `domain.py`: Track, Listener, SessionRequest, PreferenceEvidence, QueueInstance, QueueResult.
- `artifacts.py` and `catalog.py`: extraction, manifests, identity, transforms, candidate feature access.
- `preferences.py`: known likes/dislikes/blocks and separately labeled predictions.
- `candidates.py`: full-ranking baseline, balanced retrieval, feasible shortlist construction.
- `objective.py` and `constraints.py`: canonical scoring terms, hard rules, named soft goals.
- `solvers/beam.py`, `solvers/subset_dp.py`, `solvers/milp.py`: algorithms over an identical instance.
- `validation.py` and `session.py`: post-solve checks, explicit state transitions, explanation.
- `evaluation/` and `tests/`: frozen fixtures, exact oracles, counterexamples, listener-study exports.

`QueueInstance` should contain stable track/user IDs, eligible candidates, fixed utility/acceptance matrices, transition costs, durations, all hard constraints, all authorized soft goals, a locked prefix/current-track anchor, and model/policy/candidate hashes. Algorithms must not recompute different shortlists internally.

`QueueResult` should contain the requested and returned lengths; termination reason; whether a valid incumbent exists; proven-optimal status; candidate-scope hash; objective components; bound/gap when available; per-listener coverage/exposure; every explicit relaxation; violations; fallback reason; and separate preprocessing, construction, solve, and total timings.

Use states such as `INVALID_REQUEST`, `HARD_INFEASIBLE`, `TIMEOUT_NO_SOLUTION`, `FEASIBLE_NOT_PROVEN`, and `OPTIMAL`. Do not use an empty list for all of these outcomes. Null means unavailable metadata, not an invented bound or a zero gap.

The validator must check the decoded queue itself, not merely trust the solver status. Numerical extraction must verify one track per slot, uniqueness, eligibility, all hard constraints, and agreement with the canonical score within declared tolerance. Validate fallback and warm-start queues through the same path.

## 6. Mathematical model and useful optimization improvements

Let `x[a,t]` indicate placement of track `a` at position `t`, and let `z[a] = sum_t x[a,t]`. Keep explicit acceptance `A[u,a]` separate from an acoustic or calibrated utility estimate `p[u,a]`.

A user-specific representation requirement is then:

```text
sum_a A[u,a] * z[a] >= required_count[u]
```

`A` is defined by the session's affirmative evidence or a separately validated acceptance policy. It must not be recomputed as the top three of whatever shortlist remains. Representation goals should account for current history when moving to rolling windows. Strict blocks constrain eligibility, not a large but defeasible negative objective weight.

For the numerical sequencing objective, define each edge once:

```text
edge_value[a,b] = lambda * transition[a,b] - gamma * same_group[a,b]
objective = sum_a room_utility[a] * z[a]
            + sum_(a,b,t) edge_value[a,b] * y[a,b,t]
            + optional current_track_to_first_track term
```

This fixes the current penalty-unit discrepancy. Decide explicitly whether group labels mean artists, recording families, genres, or merely user-created folders. They are not interchangeable.

### Strict versus best-effort feasibility

In strict mode, solve the actual joint problem. Expand the candidate set when the shortlist, rather than the full eligible catalog, caused the conflict. If the full hard problem is infeasible, return an explanation. Do not automatically weaken a promise.

In authorized best-effort mode, introduce nonnegative representation deficits and other named slacks only for rules marked relaxable. A transparent lexicographic order is: minimize maximum normalized representation deficit; minimize total deficit; improve worst-listener utility; improve mean utility; improve transitions within agreed tolerances. Not every prototype needs all these levels; implement the smallest policy chosen for the initial use case.

Each phase must record whether its priority level was solved to proof. If an early phase is time-limited, subsequent optimization cannot claim globally optimal lexicographic fairness. Do not approximate hard priorities with enormous weights without deriving safe bounds and checking numerical consequences.

Infeasibility explanations should identify the relevant users, accepted candidates, and conflicting limits. A bounded diagnostic deletion search on the small model can help; do not assume CBC exposes a particular irreducible-conflict API. A timeout is not an infeasibility certificate.

### Continuous transition variables are sufficient

The current formulation makes both `x` and `y` binary. Keep `x` binary and allow `y >= 0` to be continuous, retaining the outgoing/incoming equalities:

```text
sum_b y[a,b,t] = x[a,t]
sum_a y[a,b,t] = x[b,t+1]
```

With one selected track at each position, every inactive row and column sums to zero. Nonnegativity forces all corresponding transition entries to zero. The sole selected row/column intersection must equal one. Thus integral placement variables already force integral transition variables.

The separate `sum_(a,b) y[a,b,t] = 1` constraint is redundant given one placement per slot and the linking equalities. Removing it does not remove a sequencing rule.

For ten candidates and five slots, the current declarations create 50 placement binaries plus 360 transition binaries. The alternative uses 50 binaries plus 360 continuous variables. It preserves the exact feasible queues under the current linking rules. It does not remove quadratic variable growth and does not guarantee a runtime improvement: presolve may already recognize part of this structure. Benchmark it rather than promising a speedup.

Ten independent five-candidate, three-slot synthetic models, including folder caps and representation, matched exhaustive enumeration with both binary and continuous transition variables. The accompanying mathematical argument is the general justification; these tests are regression evidence, not a proof by sampling.

### Add an exact subset-DP baseline

For the current static rules, use `DP[S,last]`: the best prefix visiting exactly track set `S` and ending at `last`.

```text
DP[S union {b}, b] = max over a in S of
    DP[S,a] + room_utility[b] + edge_value[a,b]
```

Folder counts and representation coverage are functions of `S`. They do not require remembering every ordering. At ten candidates and a five-track horizon, there are only 2,560 possible `(S,last)` states with `1 <= |S| <= 5`, before pruning. This is an especially useful exact comparator for the current problem.

Future temporal exposure, position-specific requirements, or history-dependent transition models can require additional state. That is a real reason to retain MILP flexibility, not a reason to omit DP from today's comparison.

### Strengthen beam before comparing it with MILP

Update the score incrementally, use integer-indexed matrices and masks, and merge prefixes with the same future-relevant state. For the present static problem, a higher-score prefix with the same visited set and last track dominates a lower-score one. Additional future state must be included if the policy changes. Add feasibility look-ahead for outstanding representation needs and remaining capacities.

Keep finite-width beam labeled heuristic. Measure its gap against the exact oracle under the same rules and total compute budget.

## 7. Preference and candidate roadmap

For the current catalog size, score the full eligible catalog as the reference path. This eliminates an unnecessary opaque early cutoff without requiring a full-catalog sequencing MILP. Keep the shortlist as a separate computational decision and measure its opportunity loss. The PDF's few-millisecond full-ranking observations are its measurements, not a new latency guarantee.

Preserve explicit known-positive evidence even when a similarity predictor disagrees. Treat unknown as unknown rather than as a neutral rating or inferred dislike. Keep exploration/discovery separate from representation promises. Support out-of-catalog requests with clear missing-catalog feedback or an explicit local import workflow, not fabricated preference estimates.

Compare maximum seed similarity, top-two pooling, and a small taste-pocket model on held-out labels. Test unequal profile sizes, disjoint taste pockets, sparse catalogs, and repeated/aliased seeds. Do not assume clustering improves a user with only two or three examples. Add a learned embedding only when there is a diagnostic reason the simpler representation fails.

Separate three quantities: retrieval recall of accepted tracks, ranking quality given retrieved tracks, and sequencing quality given the final candidates. Preserve provenance through each cut. When new candidates are added, retain an incumbent and keep the scoring/policy fixed during the comparison.

## 8. Evaluation plan

### Lane A: software and optimization correctness

Convert every supplied-review failure and every additional counterexample into a small committed fixture. Use exhaustive enumeration for very small instances and exact subset DP for somewhat larger current-policy instances. Test nonzero penalties, directed transitions, negative scores, duplicate tracks/users, infeasibility, zero/invalid sizes, partial artifacts, and short time limits.

Add property tests: listener renaming invariance, seed deduplication invariance, catalog-row permutation invariance, score/solver agreement, unchanged results under equivalent aliases, and monotonic optimum under a genuinely nested candidate expansion with frozen coefficients/rules. Test the validator using deliberately invalid decoded queues.

Compare ordinary and continuous-y MILPs, improved beam, exact DP, and a constraint-matched greedy baseline. Measure shortlist sizes, horizon lengths, users, overlap patterns, tightness of caps, and feasibility conflicts independently. Publish instance files, raw logs, random-generation code, versions, and all outcomes including failures. Report absolute objective gaps and bounds; do not rely only on percentages around an arbitrary zero.

### Lane B: preference and transition validity

Acquire judgments independently of the model's score. Ask for session-specific acceptance, ordinary dislike, explicit block, familiarity, and preference strength using a simple instrument. Evaluate non-seed recommendations separately from already supplied favorites.

For transitions, render comparable adjacent excerpts with the actual playback operator. Blind method labels and randomize presentation order. Evaluate order quality on a fixed selected track set before attributing a joint selection-and-ordering improvement to transitions.

Separate tuning and testing by the intended generalization claim. New-listener evaluation needs held-out listeners, not merely new combinations of familiar listeners. New-track evaluation should keep duplicate/remastered versions and relevant recording families from trivially crossing splits. Freeze transformations and weights before testing, or explicitly declare a transductive protocol.

### Lane C: shared-listening usefulness

Compare with round-robin favorites, a simple shared-approval policy, improved constraint-matched beam, and the optimization-based queue. Compare under common eligibility and session rules. Do not make the baseline violate constraints and then count feasibility as a solver victory.

Measure the mean and worst-listener acceptance, strongly unwanted exposure, representation and actual waiting time, familiarity/discovery, transition judgments, skips, manual edits, and time/effort spent curating. Treat groups or sessions as experimental units for group-level conclusions; hundreds of ratings from the same few groups are not hundreds of independent group trials.

Begin with a small usability pilot to debug the task and estimate variability. Determine the later sample size from the meaningful effect and uncertainty, rather than promising statistical significance from an arbitrary number of groups. Randomized crossover can be useful, but counterbalance order, familiarity, and carryover effects.

### Ablations and retirement rules

A retrieval ablation ranks the full catalog. A group-ranking ablation uses an explicit simple aggregation policy. An audio ablation uses seeds or available metadata. An ordering ablation holds song selection fixed. An optimizer ablation retains identical constraints and objective. Test component interactions, not only isolated removals.

Keep a component when it improves independently meaningful outcomes, computation, reliable rule enforcement, or a needed certificate. Its value does not have to be better prediction. A reference solver can earn its place by checking heuristics; a retrieval stage can earn its place by reducing latency at an accepted recall cost. Retire or disable components that provide no demonstrated benefit for the chosen scope.

## 9. Implementation sequence and release gates

| Phase | Work | Exit criterion |
|---|---|---|
| R0: Reproducible audit baseline | Pin environment and solver; save exact fixtures; capture existing behavior; separate private music from public test fixtures. | Clean setup runs deterministic synthetic checks and records versions. No claim depends on an unavailable notebook state. |
| R1: Correctness contract | Stable listener/track IDs; validated requests; artifact schema; single objective; explicit caps; joint feasibility; structured results; post-solve validator; validated warm starts. | No silent constraint removal, membership loss, score overwrite, or unreported truncation. Every returned queue passes independent validation. |
| R2: Policy-grounded candidates | Choose the initial session policy; explicit acceptance/blocks; full-ranking baseline; coverage-aware shortlist; incumbent-preserving expansion. | A confirmed listener option cannot disappear without an explicit eligibility or capacity explanation. Methods consume identical frozen instances. |
| R3: Optimization benchmark | Exact subset DP; incremental/deduplicated beam; continuous-y MILP; end-to-end budgets and certificate reporting. | Exact methods agree on exhaustive fixtures; heuristic gaps and failure rates are published under matched constraints. No guaranteed speedup is asserted without data. |
| R4: Listening evidence | Small pilot; independent song/transition judgments; held-out protocol; round-robin and shared-approval comparisons; ablations. | Claims clearly distinguish internal-objective gains, prediction validity, and user benefit. A disappointing result changes the component/policy rather than the metric. |
| R5: Session-aware use | Current-track anchor; locked prefix; repeats/artist cooldowns; duration-aware service history; membership changes and feedback. | Repeated replanning preserves promises and service history, and never overwrites newer user actions with stale results. |
| R6: Scale only when measured | Candidate-level transitions; bounded concurrency; appropriate retrieval indexing; production service controls if the debug panel becomes shared. | Load tests meet a chosen latency/memory target while maintaining validated rules and observable fallbacks. |

R0 through R3 produce a materially stronger optimization project even before the listening study. R4 tests whether it also delivers the desired experience. R5 and R6 should not delay fixing today's semantics and reproducibility.

Defer neural ranking, online bandits, large distributed infrastructure, complex decomposition, and new constraints invented solely to make the IP seem necessary. Any of those can become justified later by an identified failure or benchmark bottleneck.

## 10. Modeling uncertainty versus solver gap

Once utilities are estimates, optimizing them harder is not automatically the dominant improvement. A useful future diagnostic is perturbation stability: slightly change plausible utility/transition estimates and measure whether the selected queue and worst-listener outcome change drastically.

Under a hypothetical uniform error bound `E` on the entire queue objective, a solution whose estimated-objective suboptimality is at most `g` has true-objective regret at most `2E + g`. This follows by adding the prediction error at the true optimum, the optimization gap, and the prediction error at the selected queue. Such an error bound is not established for this project. The point is to measure model uncertainty alongside solver gap, not assert that exact optimization is worthless.

For a normalized mean-utility plus lambda-times-mean-transition objective, uniform per-term error bounds would give `E <= epsilon_preference + abs(lambda) * epsilon_transition`. Hard eligibility and confirmed blocks remain hard even when scores are uncertain.

## 11. Source map

All repository references below are pinned to the reviewed commit.

- C1: [queueing.py: input, retrieval, scoring, shortlisting, feasibility](https://github.com/skanda-vyas-srinivasan/jam-queue-optimizer/blob/e637be5f78567ea24f04cf0734286f357fef7d74/music_queue/queueing.py#L17-L336).
- C2: [queueing.py: queue algorithms, model, defaults, status handling](https://github.com/skanda-vyas-srinivasan/jam-queue-optimizer/blob/e637be5f78567ea24f04cf0734286f357fef7d74/music_queue/queueing.py#L339-L755).
- C3: [catalog.py](https://github.com/skanda-vyas-srinivasan/jam-queue-optimizer/blob/e637be5f78567ea24f04cf0734286f357fef7d74/music_queue/catalog.py).
- C4: [artifacts.py](https://github.com/skanda-vyas-srinivasan/jam-queue-optimizer/blob/e637be5f78567ea24f04cf0734286f357fef7d74/music_queue/artifacts.py).
- C5: [debug_panel.py](https://github.com/skanda-vyas-srinivasan/jam-queue-optimizer/blob/e637be5f78567ea24f04cf0734286f357fef7d74/music_queue/debug_panel.py).
- C6: [debug_panel/app.js](https://github.com/skanda-vyas-srinivasan/jam-queue-optimizer/blob/e637be5f78567ea24f04cf0734286f357fef7d74/music_queue/debug_panel/app.js).
- C7: [scripts/embed_audio.py](https://github.com/skanda-vyas-srinivasan/jam-queue-optimizer/blob/e637be5f78567ea24f04cf0734286f357fef7d74/scripts/embed_audio.py).
- C8: [repository tree](https://github.com/skanda-vyas-srinivasan/jam-queue-optimizer/tree/e637be5f78567ea24f04cf0734286f357fef7d74).
- W1: [PuLP: activating warm starts](https://coin-or.github.io/pulp/guides/how_to_mip_start.html).
- W2: [PuLP: 3.x to 4.0 migration and solve-status semantics](https://coin-or.github.io/pulp/guides/how_to_migrate_to_v4.html).
- W3: [NumPy: load and pickle safety](https://numpy.org/doc/stable/reference/generated/numpy.load.html).
- W4: [Python: http.server deployment warning](https://docs.python.org/3/library/http.server.html).

## 12. Attached executable evidence

`diagnostics.py` records 24 checks in `diagnostic_results.json`. By default it uses `source_extracts.py`, which is a limited reconstruction, not a complete checkout. Pass `--repo /path/to/exact/reviewed/checkout` to use real upstream functions. Source-mode metadata is written into the results.

`formulation_checks.py` creates ten small independent models using SciPy/HiGHS and compares binary-y and continuous-y formulations to exhaustive enumeration. Results are in `formulation_results.json`. It does not benchmark CBC or the saved music catalog.

These reproduction checks intentionally assert the presence of current failures. They are evidence fixtures, not a post-fix regression suite. Convert them into assertions of desired behavior when implementing repairs. The exact-commit requirement on the upstream mode prevents accidentally labeling a changed repository as the reviewed version.
