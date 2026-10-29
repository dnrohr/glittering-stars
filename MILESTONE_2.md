# Milestone 2 — Live desktop player

Status: Complete; see docs/validation/MILESTONE_2_RESULTS.md. Required for v1. Dependency: [Milestone 1](MILESTONE_1.md).
Requirements: LIVE-01/02, MIDI-01, UI-01 foundation.

## Outcome

A usable desktop window controls the existing generator while it plays through local MIDI. Controls are responsive, validated, and explicit about when edits become audible. Chord history selection is the next milestone.

## Tasks

- [x] M2-T1: implement the playback command state machine and one worker-owned MIDI port, active-note registry and interruptible monotonic scheduler.
- [x] M2-T2: build the transport strip and current chord/key display: Play, Pause, Next, Stop, Panic, generation mode and hold/gap progress.
- [x] M2-T3: expose every current parameter through controls, including add/remove step rows, editable relative weights and derived percentages. Distinguish current key from starting key; provide Reseed and Set Current Key actions.
- [x] M2-T4: implement draft/pending/applied config revisions and boundary application. Validate whole transactions; preserve currently applied values on invalid input. Offer New Phrase when new structural settings conflict with the current chord.
- [x] M2-T5: build output/channel selection, refresh, visible disconnected state and recoverable error handling. Provide configurable launch actions for installed Surge/loopMIDI. No implicit driver installation or patch changes.
- [x] M2-T6: implement stop/close/device-error cleanup and single-worker/instance ownership. Add a separate app launcher and keep Play.cmd/CLI support.
- [x] M2-T7: cover keyboard focus, basic accessibility, Windows DPI and validation feedback in the real window.

## Acceptance criteria and validation

| Gate | Scenario | Required proof |
|---|---|---|
| M2-A1 | Play and Next emit three owned notes; Pause waits through full hold/gap; Stop interrupts promptly | Fake-clock/sink tests plus GUI command path |
| M2-A2 | Change hold from 2 to 10 during a held chord | Current hold and existing gap unchanged; next onset uses one new revision |
| M2-A3 | Enter malformed, all-zero and then valid weights while playing | Visible validation; only valid transaction applied; no playback crash |
| M2-A4 | Stop/Panic during a long gap; close during hold; repeated commands | No leaked notes, no post-stop extra onset, worker shuts down without deadlock |
| M2-A5 | Disconnect/switch output or channel | Cleanup attempted on old handle/channel; no burst on reconnect; idle-only switch |
| M2-A6 | Edit range to exclude a current pitch; change seed/key/mode | Explicit rejection/New Phrase path and boundary acknowledgements follow LIVE-01 |
| M2-A7 | Missing synth/MIDI prerequisites | Window still opens, explains problem and permits recovery/preview |
| M2-A8 | Actual Windows app with loopMIDI→Surge | Recorded UI procedure and observed MIDI/synth response; unit mocks are insufficient |

Automation should drive actual Qt widgets and commands, not call a helper that bypasses the controller. Assert thread ownership and that long waits never run on the GUI thread. Measure Stop/Panic timing; record any machine-dependent limits rather than inventing precision.

## Delegation

Strong reasoning for scheduler/ownership work; capable UI worker for forms and transport after M1 contracts. Validation worker tests edge commands, GUI bindings and MIDI errors independently. Orchestrator integrates, runs the full suite, and performs the actual Windows MIDI smoke check.

## Completion evidence

Create `docs/validation/MILESTONE_2_RESULTS.md` with A1–A8 evidence, dependency versions, screenshots of applied/pending/error states and MIDI-port information. Document the app launch command and failure recovery. Missing external hardware evidence is unverified, not a pass.

Exit gate: responsive live control over existing parameters, safe transport/resource lifecycle, CLI regression coverage and actual Windows/MIDI evidence. No requirement to build looping early just to bypass unfinished transport semantics.
