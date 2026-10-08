# Versioned catalog artifacts

Run `python scripts/migrate_artifacts.py` once to explicitly import the existing 121 saved rows. This checks unique source mapping, reads durations, hashes audio, and records that the features were migrated, not regenerated. Original MP3s and flat arrays remain untouched. Generated catalogs are local ignored files, so tests and code distribution do not need this music.

New extraction with `python scripts/embed_audio.py` publishes complete generations. A manifest names stable IDs, relative sources, recording hashes, row order, feature slices (including nondefault MFCC counts), extraction parameters, package versions, frozen retrieval and shared intro/outro transforms, and array checksums. An atomic pointer replacement publishes only a complete generation. Loaders reject partial, nonfinite, misaligned or altered generations and never load pickled arrays.

A track's ID derives from its relative source path; catalog reordering preserves it. Moving a source creates a new identity; persist an explicit ID mapping for a deliberate move. Identical audio hashes define a default recording family; alternate recordings need owner-supplied family metadata. Artist identity is unknown unless explicitly supplied; folder names are only folder names.

Transforms are fitted once per generation. Adding tracks with the same transform leaves old similarities unchanged. A refit is a recorded model upgrade. Zero standardized vectors have acoustic cosine zero; explicit acceptance is retained independently. Identical nonzero raw boundary vectors share the same coordinates and cosine one.

The legacy transition signal pools 20-second segments. It remains an unvalidated acoustic baseline; it is not a claim about audible crossfades, tempo, key or listening enjoyment. The study tools will render the chosen hard-cut boundary operator for independent judgment.

New audio extractions use the actual two-second hard-cut endpoints. Legacy feature rows retain their recorded 20-second windows. A migration can additionally measure two-second RMS and leading/trailing silence without regenerating embeddings; the manifest records this separately. The simple boundary-cost ablation uses loudness-jump / 20 dB and intervening silence / 2 seconds as declared diagnostic scales. Neither these scales nor pooled cosine is independently calibrated listening quality.
