# Desktop architecture and contracts

Implementation baseline: 57c3dc1, Windows, Python 3.12+. The legacy CLI and settings.json remain compatible; new engine sequences are deterministic within engine version 1, not promised identical to legacy seeds.

One playback worker owns domain mutations, history, transport, port and active notes. UI submits numbered immutable commands; snapshots delivered to UI are detached data. Scheduler deadlines use monotonic time; gap starts after actual final note-off. Stop/Panic cancel older queued playback requests. File operations use detached snapshots outside timing work.

## Stable Python interfaces (version 1)

`glittering_stars.domain`: frozen `Config` with legacy Settings fields plus channel (0 based), policy (`off`, `moving_note`, `whole_chord`, `pivot`), locks (tuple voice IDs), allowed_keys (tuple tonic integers), max_fifths (None or 0..6), cooldown_events, min_span=7, max_span=None, min_gap=1, octave_doubling=True, upward_probability=.5. `Config.validate()`, `Config.from_dict(dict)`, `to_dict()`. `Voice(id:int,pitch:int)`; engine stores voices in ID order, display can sort.

`Engine(config, seed=None)` creates a valid initial state but no history. Properties `config`, `voices`, `key` (tonic int), `effective_seed`, `counter`, `cooldown`. `initial()` returns decision dict without advancing; `advance()` returns decision dict and updates state. `snapshot()` returns validated JSON-safe complete state including config and RNG; `Engine.restore(snapshot)` restores exactly; `apply_config(config, revision)` validates existing voices and keys atomically; `reseed(seed)` retains voices; `set_key(tonic)` validates restrictions/reset cooldown. `validate_chord(voices, config)` raises ValueError. Helpers note_number/note_name/key_number/KEY_NAMES remain available. Decisions include status, step, voice_id, direction, ordinary_destination, modulation result/reason and affected IDs.

`glittering_stars.sessions`: history events and branches are immutable JSON-safe dict records, event IDs UUID strings. Event fields: id, branch_id, voices (list of id/pitch), key integer, hold, silence, velocity, channel, revision, decision, snapshot. Snapshot is post-event state. Branch fields id, parent_id, anchor_id, name. No event is edited in place. Session schema version 1.

`glittering_stars.playback`: `Controller(config, sink=None, clock=time.monotonic)` is the serial core, with `command(name, **payload)`, `tick()`, `view()` (detached complete state). Commands play/pause/next/stop/panic, config (config dictionary), new_phrase, reseed, set_key, select (event_ids), loop/replay, loop_off, override (enabled), continue/explore (anchor_id, current_settings=False), edit (anchor_id, values), load (session). Port switching is idle only; optional sink injection makes timing tests independent of MIDI. `Worker` wraps controller in a Python thread with a wakeable command queue, serializes commands, emits detached view callbacks, and supports close/join. UI does not touch core while worker is active. Preview sink is explicit and sends no MIDI.

Config applies only at generation boundaries. Replay bypasses engine and freezes event records; only explicit timing override reads current timing. Selection replacement waits until full gap. Branch continuation restores post-anchor RNG and config; edit creates a child with substituted validated state. Save/load never starts playback.

## Acceptance and delivery

Use `python -m unittest discover -v` for all tests. GUI tests use real PySide6 widgets. Distribution uses PyInstaller only after the Windows spike proves launch. Runtime data uses LOCALAPPDATA/GlitteringStars. Missing hardware/audio observations remain unverified even when fake-sink tests pass.
