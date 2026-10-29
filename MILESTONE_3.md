# Milestone 3 — Select, replay and loop

Status: Complete; see docs/validation/MILESTONE_3_RESULTS.md. Required for v1 and the highest-priority creative workflow.
Dependency: [Milestone 2](MILESTONE_2.md). Requirements: LOOP-01/02, UI-01 timeline.

## Outcome

The user can highlight any contiguous passage in generated history, stop further generation, and repeat exactly those chords with their reverb gaps. This is the first selection-looping preview.

## Tasks

- [x] M3-T1: append immutable history events with IDs, notes/voice IDs, key, timing/velocity, config revision, decision and post-event engine snapshot.
- [x] M3-T2: implement a model-backed three-lane timeline with chord cards, key/modulation markers, playhead, zoom/scroll and inspectable blocked/repeat reasons.
- [x] M3-T3: add contiguous mouse drag, Shift range and keyboard selection. Single-event selection works. Retain selection IDs during incoming events and scrolling.
- [x] M3-T4: implement Replay Selection once and Loop Selection indefinitely. Freeze source event data; stop generation immediately after acknowledgement while letting the already-started event finish.
- [x] M3-T5: support replacing a playing loop's selection at the next boundary. Preserve the old loop if the proposed selection is invalid. Turning Loop off pauses replay rather than starting generation.
- [x] M3-T6: add Recorded Timing and explicit Live Timing/Velocity Override; never mutate event snapshots or stored durations. Stage generation edits while replaying.
- [x] M3-T7: implement Pause/Next/Stop/Panic across replay and loop modes. Use the same tested scheduler/MIDI owner as generation.

## Acceptance criteria and validation

| Gate | Scenario | Required proof |
|---|---|---|
| M3-A1 | Generate 12 events; select events 4–7 while another chord is sounding; loop | Finish active event/gap, then play only 4–7 in order; no new generation afterward |
| M3-A2 | Loop a mixed-key passage 100 times | PRNG snapshot, generator transition count and history count unchanged; sink pitches/keys/velocities match frozen events |
| M3-A3 | Loop one chord | Three retriggered notes per cycle, full gap including wrap, no held-note accumulation |
| M3-A4 | Change selection mid-hold and mid-gap | Old event completes safely; new range starts at next boundary; no partial chord or duplicate onset |
| M3-A5 | Change live controls during exact replay | Generator settings remain pending; recorded notes/timing unchanged unless timing override explicitly enabled |
| M3-A6 | Toggle timing override, Pause/Next, disable Loop and Stop | Stored events unchanged, cursor semantics correct and no unintended generation |
| M3-A7 | Select via drag and keyboard while history grows | Same event IDs remain selected; labels and key changes readable at tested DPI |
| M3-A8 | Real app loop through Surge | Evidence of no extra melody, exact selected pattern and audible configured gaps; correlate with MIDI events |

A timer-driven carousel or a loop indicator alone does not satisfy M3. A fresh seed/regeneration that happens to resemble the selected sequence does not satisfy exact replay. Prove that replay bypasses the generator.

## Delegation

One worker owns history/replay controller logic, one owns timeline/selection interaction, and QA owns independent sink/PRNG-isolation and GUI cases. The orchestrator owns event-ID and cursor contracts and validates cross-module command ordering.

## Completion evidence

Create `docs/validation/MILESTONE_3_RESULTS.md` with A1–A8, screenshots showing a highlighted range and playhead, captured MIDI event comparison, and snapshots before/after repeated loops. Include a repeatable selection/loop demonstration procedure.

Exit gate: all loop invariants proven in real UI/controller paths and a local MIDI pass. Do not label v1 complete: branching, durability, advanced music controls and packaging remain.
