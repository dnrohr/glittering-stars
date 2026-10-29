# Milestone 4 — Compose, save and export

Status: Complete; see docs/validation/MILESTONE_4_RESULTS.md. Required for v1. Dependency: [Milestone 3](MILESTONE_3.md).
Requirements: COMP-01, COMP-02 editing, DATA-01/02.

## Outcome

Interesting passages become durable musical material: edit a chord, continue or branch from it, save the complete session, and export a selection as MIDI without regenerating it.

## Tasks

- [x] M4-T1: implement parent/child branch ancestry, active branch and anchor selection. Preserve existing futures when continuing from earlier history.
- [x] M4-T2: implement Continue from Here using post-event snapshots and recorded settings by default. Make Current Settings an explicit alternative; validate it before starting. Do not replay the anchor automatically.
- [x] M4-T3: implement Explore from Here with a fresh recorded seed and current valid settings, retaining the anchor chord/key. Expose branch switching without destructive replacement.
- [x] M4-T4: add chord inspector editing for the three voice pitches, key, hold/gap and velocity. Commit an edited child anchor, validate, audition explicitly, and continue from the new snapshot. Provide undo of an unsaved edit without changing existing history.
- [x] M4-T5: implement versioned session and preset JSON, schema validation, atomic save, open, autosave recovery and legacy settings import. Session load starts silent and stopped.
- [x] M4-T6: export stored selection/branch events as MIDI, with recorded or explicitly overridden timing, key at selection start, markers, channel, final gap and optional finite loop repetitions.
- [x] M4-T7: add consistent snapshots for background saves and clear dirty/saved indicators. Handle malformed/future schemas and unwritable paths without losing the current session.

## Acceptance criteria and validation

| Gate | Scenario | Required proof |
|---|---|---|
| M4-A1 | Continue from an old event with recorded state/settings | Same next 100 decisions as the compatible original branch under the same commands; parent future retained |
| M4-A2 | Explore from the same anchor | Fresh seed recorded; same starting chord/key; new child branch; no overwrite of prior history |
| M4-A3 | Edit a chord and audition/continue | Original event and descendants unchanged; edited anchor has validated voice IDs/state; invalid edit rejected |
| M4-A4 | Save/open a multi-branch session while transport has been active | Exact history, selections, branches, settings, PRNG/cooldown and cursor restored; no notes on load |
| M4-A5 | Interrupted/failed save, corrupt JSON, unknown future schema, legacy file | Last good file/session preserved; explicit migration or unsupported-continuation feedback |
| M4-A6 | Export a mixed-key selection beginning inside a branch | Parse file and compare every onset, release, gap, velocity/channel and key against selected events |
| M4-A7 | Loop with overrides, export one pass and N passes | Explicit timing choice honored; correct duration and wrap/final gaps; generator never called |
| M4-A8 | GUI save/open/edit/branch workflow | Real dialog/model/controller evidence and visible branch ancestry; no GUI-thread file waits on MIDI locks |

Determinism is scoped to compatible engine versions and the same subsequent configuration commands. Future schema replay and continuation capabilities must be described separately; never silently reconstruct RNG progress from a seed alone. Do not accept executable serialization for convenience.

## Delegation

Strong worker for snapshot/branch and schema migration logic; another worker can implement MIDI export against frozen events; UI worker binds the inspector and persistence actions after contracts stabilize. The orchestrator reviews state lineage and independently runs round trips and branch equality tests.

## Completion evidence

Create `docs/validation/MILESTONE_4_RESULTS.md` with A1–A8, schema examples and migration fixtures, actual exported MIDI parse comparison and screenshots of branching/editing. Update session-format documentation and app help.

Exit gate: stored musical material can be restored and resumed without losing lineage; exports prove agreement with replay. Voice locks are added in M5 against the stable IDs already established.
