# Glittering Stars application specification

Status: implemented contract for required v1; qualification evidence is under docs/validation. M7 remains optional.
Prepared: 2026-10-28. Repository baseline inspected: `57c3dc1`.

## 1. Product and scope

Build a local Windows application for exploring three-note generative harmony through a MIDI synthesizer. The user listens, changes musical parameters during playback, selects an interesting passage, loops it exactly, edits it, and continues exploring from it. Surge XT remains the sound engine; loopMIDI remains the local MIDI connection.

The primary user workflow is **Generate → Select → Loop → Edit → Explore → Save/Export**. A native Python desktop app is the planned implementation, retaining the command-line player. This document specifies behavior, not a new synthesis engine or a DAW.

Scope levels:

- **Required v1:** requirements BASE, ENG, LIVE, UI, LOOP, COMP, HARM, DATA, MIDI, and QA below; milestones 1–6.
- **Optional follow-on:** requirement LAB; milestone 7. Audio-tail detection and a Surprise control were suggestions, not prerequisites for the requested app.
- **Outside this plan:** embedded VST hosting, synth preset editing, arbitrary MIDI CC automation lanes, audio recording/mixing, cloud accounts, publishing a hosted website, and non-Windows release qualification. Architecture should not prevent later ports.

The stack and the detailed interaction defaults below are design decisions for implementation. They may be refined through documented decisions without weakening acceptance criteria. Preserve user-authored settings; do not restore original defaults over the current file.

## 2. Evidence from the current repository

| Source | Verified state |
|---|---|
| `generate.py` | Settings, weighted random chord walk, four/seventh modulation, octave-wide alteration, timed MIDI playback, preview, MIDI export |
| `test_generate.py` | 12 passing unittest cases, including timing cleanup, constraint walks, and modulation metadata |
| `settings.json` | C3–C5, hold 2 s, silence 4 s, continuous generation, random seed, velocity 55, C major, 15% modulation each direction, steps 0/1/2 weighted 0.1/0.6/0.3 |
| `Play.cmd`, `Stop Notes.cmd` | Windows launchers for the CLI and emergency MIDI cleanup |
| `requirements.txt` | mido 1.3.3, python-rtmidi 1.5.8 |

The current engine sorts pitches and does not preserve voice identity. It has no GUI, replay history, branches, live parameter transaction model, session format, or audio input. Its blocking playback loop is unsuitable for a responsive UI without separation. Baseline tests are evidence for the CLI only; they do not establish any app acceptance criterion.

## 3. Musical contract

### BASE-01 — Notes and constraints

Exactly three distinct MIDI pitches sound at each chord onset. No added melody, strums, overlapping chords, or hidden voices. Octave doublings are allowed by default. Scientific pitch notation is authoritative: C2=36, C4=60. Inclusive range bounds must remain in MIDI 0–127.

Highest minus lowest pitch must be at least seven semitones: all three fitting within a flat fifth (six semitones) is prohibited. The GUI may impose stricter spacing but cannot relax this floor. Validate initial, generated, edited, and modulated chords.

### BASE-02 — Weighted movement

Select a nonnegative integer step using relative weights. Weights are finite, nonnegative, one per distinct step, with at least one positive weight; they need not sum to one. Display derived percentages without rewriting the user's weights. Default diatonic steps/weights are `[0,1,2]` / `[0.1,0.6,0.3]`; chromatic defaults are `[1]` / `[1]`.

Step zero repeats the chord and never attempts modulation. A positive step moves one eligible voice up or down. At neutral direction bias, legal voice/direction pairs have equal chance. Draw the step once. If no legal move exists, repeat, display why, and do not redraw the step. Preserve the distinction between a requested repeat and a blocked move in history.

Diatonic steps use the current major key; chromatic steps use semitones. A retained pitch outside the current key enters the scale at its nearest pitch strictly in the chosen direction for step one, then continues through scale degrees for larger steps.

### BASE-03 — Existing modulation and octave exception

Default policy is `moving_note`. Only the newly moving note landing on the current key's fourth/seventh can trigger a modulation; initial chords, repeats, unchanged trigger notes, and blocked moves do not.

- Fourth landing: one probability roll, raise the trigger pitch class one semitone, move key up a fifth. C: F→F# and C→G.
- Seventh landing: one probability roll, lower the trigger pitch class one semitone, move key down a fifth. C: B→Bb and C→F.
- All octaves of that trigger pitch class in the candidate chord change together. This explicitly permits multiple voices to change during modulation; ordinary moves still change one voice.
- Check the entire altered chord atomically. Reject the modulation if any changed pitch is out of range, causes a unison/spacing violation, violates a voice lock, or the triggering moving voice returns to its previous pitch. Keep the ordinary move and original key on rejection. Never partially alter octaves.
- Current key persists. Unchanged out-of-key pitches may remain until moved under this policy.

Default chances are 0.15 independently in each direction. These are actual probabilities in [0,1], not relative weights. Chromatic mode suppresses all automatic modulation policies without destroying their saved values.

### ENG-01 — Stable state and reproducibility

Introduce three persistent voice IDs, initially ordered by pitch. Voice identity survives sorting for display and pitch crossings. Locks refer to IDs, not whichever note is currently lowest. Serialize each voice's ID and pitch.

The engine is independent of GUI, MIDI devices, wall time, and file dialogs. A transition takes immutable validated configuration and state, and returns the next state and structured decision metadata. Record sampled step, source voice, direction, ordinary destination, modulation attempt/result/reason, key before/after, and affected voice IDs.

An engine snapshot contains voice state, current key, effective configuration revision, PRNG state, transition counter, cooldown state, and engine-format version. With the same compatible engine version, starting snapshot, and subsequent configuration commands, generation is reproducible. A seed alone is insufficient to resume an arbitrary historical point. Store effective randomly chosen seeds. Encode PRNG state as validated JSON data; never deserialize executable pickle data from sessions.

Refactoring must preserve the CLI defaults and behavior. Require deterministic outcomes within the new engine version; do not promise bit-identical old seeded sequences after changes to voice representation or random-call ordering.

## 4. Live controls and transport

### LIVE-01 — Configuration transactions

All current CLI parameters must be accessible in the app: output port, mode, low/high pitch, hold, silence, chord count, seed, velocity, starting key, both step tables, and both modulation chances. Also expose HARM controls when implemented.

The UI owns draft input. Validate a complete revision before dispatch; the engine owns the applied revision. Show **Applied**, **Pending next chord**, or a specific validation error. A malformed intermediate number must not change playback. Cancel returns the draft to applied values.

| Control | Application point |
|---|---|
| Range, steps/weights, mode, velocity, spacing, locks, direction and harmonic controls | Atomic next generation boundary, before sampling the next chord |
| Hold/silence | Snapshot at onset; edits never shorten a sounding chord or a gap already in progress |
| Starting key | Next New Phrase; separate Set Current Key command changes context at a generation boundary without retuning held voices |
| Seed | Explicit Reseed at next generation boundary; retains current chord, resets PRNG and records a new revision |
| Finite chord count | Counts new history events for the run; replay cycles do not count; stop after final full gap |
| Output port/channel | Stop and release through the old port first; switch only when idle; never redirect notes mid-chord |

Reject generation revisions whose range/spacing invalidates the current chord, or whose key restriction excludes the current key. Offer an explicit **New Phrase with These Settings** action to sample a valid new start. Do not silently clamp pitches, unlock voices, change keys, or reset the seed. Changing mode/key may leave retained notes outside the new scale; use BASE-02 on their next movement.

### LIVE-02 — Transport semantics

Transport mode (`Generate`, `Replay`, `Loop`) and phase (`Idle`, `Holding`, `Gap`, `Paused`, `Error`) are separate fields. An authoritative worker processes commands serially and issues state events. The UI never infers transport truth from button labels.

- **Play:** resume the chosen mode. New empty sessions create an initial chord only on Play/Next.
- **Pause:** finish the current hold and full gap, then pause without sampling another chord. Show a pause-pending indicator immediately. If idle, pause immediately.
- **Next Chord:** when idle/paused, perform one event in the chosen mode, including hold/gap, then return to paused. Disable while an event is running.
- **Stop:** promptly release owned active notes, cancel pending playback actions, retain history/selection/state, and remain idle; allow synth tails to decay.
- **Panic:** immediately send sustain-off, explicit owned note-offs, all-notes-off and all-sound-off on the app's configured channel; cancel pending actions and remain stopped.
- **Close:** stop, release, join the worker, and close the port. A disconnected port enters Error without replaying missed events on reconnection.

For non-panic commands, normal chord boundaries are after hold plus the full measured gap. Stop/Panic and port-error cleanup interrupt waits; they do not wait for a long reverb gap to finish. Pause stores the next event position; Stop preserves the current cursor for explicit resume. Play after Panic starts from the retained cursor/state, never silently opens a new phrase.

Stop/Panic invalidate older queued Play/Next/loop-switch commands so they cannot restart playback after acknowledgement. A later deliberate Play can start it again. Valid pending configuration revisions remain visible while stopped; they are not playback actions. Number commands and acknowledgements so rapid UI interactions cannot resurrect stale state.

### MIDI-01 — Scheduling and resource ownership

Exactly one playback worker owns the MIDI output handle and active-note registry. No playback timing or generation loops on the GUI thread. UI commands wake an interruptible scheduler. Use monotonic deadlines; measure the configured gap after the actual final note-off. Do not catch up late by compressing a gap or firing multiple chords in a burst.

Send three note-ons as closely together as MIDI permits. Normal note-off/stop does not use all-sound-off. Avoid note leaks on interruption, invalid edits, save/load, device loss, or shutdown. Single app instance enforcement, or an equally clear ownership mechanism, must prevent two app workers from fighting over the same output/channel; warn about separately launched CLI players.

Default channel remains 1; expose channels 1–16. Display a refreshable output picker, connection status, and actionable errors. Missing Surge/loopMIDI is recoverable; the app launches and can preview sessions without those programs. Provide synth launch actions with configurable paths, rather than assuming an installed path forever. Do not automatically install drivers or modify synth patches.

## 5. Application surface

### UI-01 — Layout and usability

Use a main window with a persistent transport strip, MIDI connection indicator and current-key display; a live controls panel; a central chord timeline; and an inspector for selected chords, decisions, and branches. Put primary actions in reach without opening a settings file or terminal.

The timeline has three voice lanes and chord cards with note names, key, hold/gap lengths, repeat/blocked/modulation markers, and selection/playhead states. Key changes must be readable without relying on color. Show MIDI note numbers on demand to resolve octave naming differences with synths. Prefer note labels to inferred chord names, which can be ambiguous.

Keyboard focus order, labeled controls, accessible selection range, zoom/scroll, readable text at Windows 100–200% scaling, and keyboard equivalents for selection/looping are required. No unmodified spacebar transport shortcut while editing text/spinboxes. Proposed shortcuts: Ctrl+L loop selection, Escape stop, and clearly labeled Panic; finalize and test non-conflicting shortcuts in M2/M3.

### LOOP-01 — History and selection

Append one immutable history event per generated chord, including intentional/blocked repeats. An event has an ID, branch ID, ordered voice states, key, recorded hold/gap/velocity, configuration revision, decision metadata, and a resumable post-event engine snapshot. The initial event also has a snapshot.

Select a contiguous inclusive range by drag, click plus Shift, or keyboard. Single-event selection is valid. Selection does not itself start playback, alter generation, or consume randomness. Autoscroll may be disabled while selecting. Keep selection by event IDs when new events appear; do not silently shift the range.

### LOOP-02 — Exact replay and selection looping

**Loop Selection** freezes the selected event IDs and their recorded musical data. From Generate, stop creating new events as soon as the command is acknowledged; complete any already-sounding chord and gap, then start at selection start. Do not pre-generate future chords. From paused/idle, enter Loop mode but wait for Play, or use an explicitly labeled Play Loop action.

Replay emits the saved pitches, keys, durations and velocities and does not call the generator, consume PRNG state, or append duplicate history. A one-chord loop retriggers its three notes every cycle with the full gap. The last selected chord has its full gap before wrap. Mixed-key passages retain their recorded key labels; they do not reroll modulation at wrap.

Changing the selection during looping queues a replacement for the next chord boundary, restarting at the new selection start. Empty/invalid selection leaves the current loop intact with an error. Pause and Next apply to loop position without advancing generator state. Turning Loop off enters paused Replay at the next boundary; it does not silently generate.

Default playback uses **Recorded Timing**. An explicit **Live Timing/Velocity Override** toggle applies current hold/silence/velocity at loop/replay onsets, leaving the stored events intact. Musical generator edits remain pending until Generate/Explore resumes. Display overrides, and let export explicitly choose recorded values or the active override. Never rewrite history just because a control changed.

### COMP-01 — Replay, continue, and explore

**Replay Selection** plays once, including final gap, then pauses. **Continue from Here** requires one selected anchor event, restores its post-event snapshot and compatible configuration, and generates a new child branch from that chord/key; it does not replay the anchor. If applied draft settings differ, offer **Recorded Settings** versus **Current Settings**, defaulting to recorded, before starting.

**Explore from Here** uses the same anchor/chord/key and current valid settings but chooses a fresh seed for a different child branch. Record that seed. Existing history and parent futures are retained. The UI makes branch ancestry and the active branch visible; selecting a branch never deletes another one.

### COMP-02 — Edit and lock

Edit a selected historical chord's pitches, key, hold/gap and velocity in an inspector; validate before accepting. Editing creates an explicit child variation rather than mutating an event or invalidating later snapshots. Copy PRNG/cooldown state from the anchor, substitute validated musical state, and store a new edited anchor snapshot. Preview it with one audition; do not auto-play on every keystroke. The variation can be replayed, selected, or used to Explore/Continue.

Lock a voice by stable ID to its current pitch for future generation. All locked means repeats with a clear reason, not an infinite candidate search. Locked voices also veto an octave-wide modulation that would move them: do not alter only the unlocked octave. Locks do not rewrite or suppress saved notes during replay.

## 6. Additional musical controls

### HARM-01 — Modulation policy selector

| Policy | Eligibility and result |
|---|---|
| Off | Retain current key; no automatic key change |
| Moving-note trigger | BASE-03; retained out-of-key voices permitted |
| Whole chord fits | Same landing trigger, roll and octave-wide alteration as BASE-03, plus require every resulting pitch in the destination major scale |
| Pivot chord | After a positive ordinary move, require the whole unaltered candidate to fit both current and adjacent destination major scales; change context without altering pitches |

In Pivot mode, enumerate admissible up/down-fifth destinations after the ordinary move. Exclude zero-probability directions and disallowed destinations, choose uniformly if both remain, then make one roll using that direction's configured modulation chance. No second attempt in the opposite direction after failure. Never run pivot and trigger alteration on the same transition. Initial chords, repeats and blocked steps do not trigger pivot attempts. Whole-chord-fit rejects retain the ordinary move and original key, with a visible reason.

Example for C→G: candidate C#–E–F would become C#–E–F# under the alteration policy, so Whole chord fits rejects it because C# is outside G major. C–E–F# does fit G major. Candidate G–B–D can pivot from C to G unchanged. Unit tests must include these cases. This corrects the original C-natural example, with explicit user confirmation; see docs/decisions.md.

### HARM-02 — Exploration boundaries

Expose allowed destination keys, maximum circle-of-fifths distance from starting key (0–6 or unrestricted), and minimum completed chord events between accepted modulations (default zero). Both key filters apply; reject revisions excluding current key and starting key. Distance uses the shortest path around the twelve-key fifths circle.

On accepted modulation set a cooldown counter to N. Each subsequent new generated event, including repeat/blocked events, consumes one cooldown slot; replay/loop cycles do not. A transition beginning with a positive counter cannot modulate. Rejected attempts do not reset the counter. Manual Set Current Key is an explicit context action, obeys allowed-key constraints, and resets cooldown; log it.

### HARM-03 — Spacing, direction and octave controls

Expose minimum chord span (floor 7), optional maximum span, minimum gap between neighboring pitches (floor 1), octave-doubling allowed (default true), and upward-direction probability (default 0.5).

Apply direction probability as relative weights on the legal voice/direction candidate pairs after the step draw. At probability 0 or 1, a forbidden direction is never used as fallback; repeat if no positive-weight candidates remain. All constraints and locks are applied before choosing candidates. Explain blocked moves in the inspector; do not hide unreachable choices by resampling steps.

## 7. Save, restore and export

### DATA-01 — Sessions and presets

Use versioned, human-readable JSON with validated schemas. A session stores applied and valid pending settings/revisions, effective seeds and engine versions, voice state/locks, full retained history, branches, selection, playback mode/override, cursor, cooldowns, and PRNG snapshots. Record applied context/reseed commands with event-boundary ordering so continuation tests can reproduce their effects. Unsaved invalid UI text is not an applied musical setting. Never store an open port handle or resume sound automatically after load.

Save atomically through a temporary file in the destination directory and replace on success. A failed or malformed load leaves the open session unchanged. Autosave to an app data directory with recoverable last-known-good state; never silently overwrite a user's named session. Schema migrations are explicit and tested. Unknown future schema/engine versions permit safe inspection/replay when possible; disable unsupported deterministic continuation with a clear explanation.

Presets store configuration, not history or PRNG progress. Support legacy `settings.json` import with missing new fields receiving documented defaults. Do not rewrite the user's legacy file on launch. Session save/load occurs off the timing path using a consistent snapshot. Store full retained history on disk; virtualize its rendering. Define a measured capacity target of 10,000 events in M6, with explicit limits/errors rather than silently dropping selected history.

### DATA-02 — MIDI export

Export a selection or branch once as standard MIDI: three note-ons/offs per event, preserved gaps including the final gap, velocity, configured channel, and key-signature/marker changes. Include the first event's key even if it starts mid-branch. Exporting a loop exports one pass unless a finite repetition count is requested. Export operates on stored events, not regenerated seeds. Round absolute timestamps before converting to delta ticks; no negative deltas.

Recorded Timing is the default. If Live Timing/Velocity Override is active, choose explicitly whether to export it. MIDI export preserves note and key events, not Surge's patch or rendered reverb; label this in the export dialog.

## 8. Architecture and delivery

### ARCH-01 — Planned implementation

Use Python 3.12+ with PySide6 Widgets for the Windows UI, reusing mido/python-rtmidi. The orchestrator must run an install/launch/deployment spike in M1 and record tested dependency versions before committing to a packaging tool. Avoid a separate browser server and a second music engine.

Suggested module boundaries, finalized in M1:

```text
glittering_stars/
  domain/       configuration, voices, engine, snapshots, decisions
  playback/     command state machine, scheduler, MIDI adapter
  sessions/     history, branches, schemas, persistence, export
  ui/           Qt models, timeline, controls, inspector, application
generate.py     compatible CLI adapter
tests/          focused unit, integration, GUI and fixture suites
```

One controller/worker owns playback and domain mutations. The UI sends typed commands and receives immutable events. Snapshot IDs and revision numbers establish ordering. File I/O and rendering cannot hold a lock needed for note-off. Thread lifecycle must be explicit; no widget access from the playback worker.

Qt documents the worker-object threading pattern and cross-thread signal delivery in its [QThread reference](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html). Choose and prove a compatible dispatch pattern; do not assume moving a blocking loop into QThread automatically makes queued commands responsive. Qt's [deployment documentation](https://doc.qt.io/qtforpython-6/deployment/index.html) lists packaging approaches; verify a Windows build rather than assuming a tool will work. These links inform the proposed architecture, not a claim that packaging has been tested here.

Keep `Play.cmd` and CLI behavior available. Provide a separate desktop launcher during development, then a packaged Windows app in M6. Runtime app state belongs in per-user app data, not a frozen bundle or source tree. Do not redistribute Surge or loopMIDI installers. Include dependency notices in distributed builds.

### QA-01 — Validation contract

Use a fake monotonic clock, recorded MIDI sink, and deterministic engine fixtures for authoritative logic tests. GUI tests must drive real widgets/models and process actual commands/events. Mock-only screenshots do not establish functionality. Keep engine tests runnable without GUI dependencies when feasible; retain a documented single full-suite command.

Required evidence categories:

1. Musical invariants and weighted sampling across seeds, keys, boundary ranges, locks and policies.
2. Scheduler lifecycle and configuration ordering, including Stop/Panic during hold/gap, rapid commands and device loss.
3. Loop/replay isolation: unchanged PRNG state/history count after many cycles; full tail gap at wrap; exact selection pitches/keys/timing.
4. Branch/edited-anchor deterministic restoration, JSON migration/corruption handling, and MIDI round-trip event checks.
5. Windows GUI interaction evidence with readable controls, drag and keyboard selection, live edits and transport changes.
6. Real loopMIDI→Surge smoke evidence, separate from unit-test claims. A missing device is recorded as an unverified gate, never converted to success.
7. Packaged Windows launch from a folder with spaces and without relying on the developer `.venv`; dependency/prerequisite errors remain recoverable.

Fake-clock timing is exact within timestamp rounding. On the tested Windows machine, record note-on spread and hold/gap error under normal UI activity; target ≤20 ms spread and ≤50 ms duration error without claiming hard real-time guarantees. Stop/Panic should dispatch cleanup within 100 ms under that same test load. Define timestamps and percentile/sample counts in evidence; do not make a hard limit depend on listening alone. Long stress playback can use virtual MIDI without leaving audio sounding unattended.

### LAB-01 — Optional extensions

Audio-tail-aware silence needs an explicit selectable loopback/audio source associated with Surge, an input meter, dBFS threshold, a continuous quiet-window duration, minimum and maximum wait, and fixed-gap fallback. No threshold crossing may suppress the three note-offs. Maximum wait prevents stuck playback; Stop/Panic must bypass analysis. A missing/mismatched source must be visible, not treated as silence. Do not enable microphone capture implicitly.

Surprise is a bounded macro over user-approved step/direction/modulation settings, never pitch range, note cleanup, locks or hard constraints. Define and display the mapping, preserve a reversible base preset, and record effective parameter revisions so replay and sessions remain reproducible. It is an optional control after independent musical controls are validated.

## 9. Traceability and completion

| Requirement IDs | Primary milestone |
|---|---|
| BASE-01, BASE-02, BASE-03, ENG-01, ARCH-01 foundation | [MILESTONE_1.md](MILESTONE_1.md) |
| LIVE-01, LIVE-02, MIDI-01, UI-01 foundation | [MILESTONE_2.md](MILESTONE_2.md) |
| LOOP-01, LOOP-02, UI-01 timeline | [MILESTONE_3.md](MILESTONE_3.md) |
| COMP-01, COMP-02 editing, DATA-01, DATA-02 | [MILESTONE_4.md](MILESTONE_4.md) |
| COMP-02 locks, HARM-01, HARM-02, HARM-03 | [MILESTONE_5.md](MILESTONE_5.md) |
| QA-01, ARCH-01 distribution, integrated requirements above | [MILESTONE_6.md](MILESTONE_6.md) |
| LAB-01 | [MILESTONE_7.md](MILESTONE_7.md), optional |

v1 requires actual evidence for M1–M6. That implementation and qualification evidence is now recorded in docs/validation/ACCEPTANCE.md and the milestone results. M7 remains explicitly optional and is not implemented.
