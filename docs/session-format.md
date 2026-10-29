# Session format 1 / engine snapshot format 1

JSON only; no pickle or executable serialization. Top-level fields include schema_version, config, pending_config, engine, history, branches, active_branch, selection, playback_ids, cursor, mode, override, applied_revision, output_channel, pending_reseed/key, context_log and run/anchor flags. Loading clears playback and detaches real MIDI handles. Device handles and active notes are never serialized. Earlier version1 files default output_channel to config.channel.

Each history event has immutable UUID id, branch_id, voices (IDs 0/1/2 with MIDI pitches), integer tonic key, hold, silence, velocity, zero-based channel, revision, decision and a complete post-event snapshot. Decisions explain initial/repeat/blocked/moved/modulated outcomes and identify the moving voice, sampled step/direction, ordinary destination, modulation result/reason and affected voices.

Snapshots store schema_version, config, voices, current key, start_key, effective_seed, counter, cooldown, revision and rng_state. RNG is the validated Python Random integer state as JSON arrays and a finite optional Gaussian cache. Restoring a seed alone is insufficient; continuation uses the complete snapshot. Reproducibility is scoped to a compatible engine format and the same subsequent boundary commands.

Branches contain id, parent_id, anchor_id and display name. Editing appends an edited anchor and child ancestry; parent events and futures remain. Sessions validate musical event data, references, ancestry, configuration and compatible snapshots before replacing an open session.

Unknown future formats may be inspected/replayed when their stored musical data can be validated; deterministic continuation is disabled with a compatibility warning. Unsupported malformed data is rejected without changing the open session. Legacy presets import missing fields with Config's documented defaults: moving_note policy, no locks/limits/cooldown, min_span 7, min_gap 1, octave doublings allowed, direction .5, channel 0.

Named saves use a temporary file in the destination directory, flush/fsync, and atomic os.replace; failure leaves the previous destination untouched. Autosaves are separate per-user files. All disk I/O runs outside the MIDI timing path on consistent immutable event views.
