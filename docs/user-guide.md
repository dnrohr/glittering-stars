# Glittering Stars desktop guide

Install Python 3.12+ on Windows, then install requirements.txt and requirements-desktop.txt into `.venv`. Launch Desktop.cmd or run `.venv\Scripts\python.exe desktop.py`. Play.cmd continues to launch the CLI. Do not run CLI playback at the same time as desktop playback on the same port/channel.

## Connect and generate

Start loopMIDI and create Surge Generative. In Surge XT, enable that MIDI input, channel 1, and use Poly mode. The desktop output picker refreshes available ports; connect explicitly. Preview mode permits inspecting/generating history without MIDI. Missing drivers/synth do not prevent opening sessions.

Enter a complete valid draft and Apply. Invalid input leaves applied values unchanged. Applied and Pending next chord distinguish the audible revision from your draft. Cancel restores applied fields. Hold, silence and velocity are captured at each onset; a change cannot shorten the current hold or its following gap. Structural changes that exclude a held pitch require New Phrase with These Settings. Starting key belongs to the next new phrase. Reseed and Set Current Key are explicit boundary commands; changing current key does not retune held voices.

Play resumes the chosen mode. Pause completes the current hold and full gap. Next plays one event then pauses. Stop interrupts and releases notes while preserving release/reverb tails. Panic additionally sends sustain-off, all-notes-off and all-sound-off. Escape stops; no unmodified spacebar shortcut interferes with numeric text editing.

**Regenerate (clear history)** is near the top of the controls panel. It releases current notes, picks and displays a fresh seed, clears all previous events, branches and selection, and immediately starts a new sequence with your current valid settings and MIDI connection. Previously saved session files remain available. Use Generate to continue existing history instead.

## Capture a passage

Select a contiguous range in the timeline by dragging, Shift-clicking, or Shift with keyboard arrows. A single event is valid. Loop Selection (Ctrl+L) freezes that passage. During generation it finishes the active event/gap and then loops from the first selected event; from idle press Play to start the chosen loop. Every wrap includes the final full silence. Changing selection while looping takes effect at the next complete boundary.

Replay Selection plays once. Loop Off pauses Replay at the boundary. Recorded Timing uses the stored hold, silence and velocity. The explicit live override changes only replay onset timing/velocity; stored events stay unchanged. Musical edits remain pending until generation resumes. Replay never generates, consumes PRNG state or appends history.

## Edit, branch and save

Continue from a single selected event restores its full post-event state and creates a child branch without replaying the anchor. Recorded Settings is the default; Current Settings is an explicit alternative. Explore retains the anchor chord/key and uses current valid settings with a fresh recorded seed. Parent futures remain available.

Inspector edits create a child variation. Validate all three pitches, key, hold, silence and velocity, then audition explicitly. Stable voice IDs stay with the same voice even when pitches cross. Locks constrain future generation and veto any octave-wide modulation that would alter a locked voice; saved replay is unchanged.

Save Session retains history, branches, selection, compatible PRNG snapshots and transport cursor. Open always starts silently. Failed saves use atomic replacement to preserve the last good file; autosave recovery uses LOCALAPPDATA/GlitteringStars and does not overwrite named sessions. Presets contain settings only. Legacy settings.json can be imported without rewriting the original file.

MIDI export uses the stored selection or branch. Choose recorded timing or explicitly choose the active override and a finite repetition count. It includes the initial key, key/marker changes, velocity/channel and final full gap. It stores notes and key events, not Surge's patch or rendered reverb.

## Musical choices

Exactly three distinct pitches stay in the inclusive range, with a span of at least seven semitones. Relative step weights need not sum to one; zero means an intentional repeat. A blocked sampled step repeats with an explanation rather than drawing a different step. Direction weights apply only to legal voice/direction pairs.

Moving-note trigger raises every octave of a newly landed fourth or lowers every octave of a newly landed seventh after one successful probability roll. Whole chord fits also requires every resulting pitch in the destination major scale. Pivot changes key context without altering the candidate chord. C-E-F# does fit G major: the planning example claiming otherwise is corrected in decisions.md. Chromatic mode suppresses automatic modulation but retains its settings. Allowed keys, fifths distance and cooldown apply to generated events; loops never consume cooldown.

## Validation and scope

Run `.venv\Scripts\python.exe -m unittest discover -v`. Validation evidence and any unresolved gates are in docs/validation. Required scope is M1–M6; adaptive audio-tail capture and Surprise (M7) are optional and are not enabled. Windows scheduling is measured, not hard real-time. Hearing/audio verification is distinct from MIDI receipt and synth meters.
