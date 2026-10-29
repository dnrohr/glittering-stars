# Milestone 1 — Engine and state foundation

Status: Complete; see docs/validation/MILESTONE_1_RESULTS.md. Required for v1. Dependency: existing CLI baseline.
Requirements: BASE-01/02/03, ENG-01, ARCH-01 foundation in [SPECIFICATION.md](SPECIFICATION.md).

## Outcome

An independently testable musical engine with stable voice identity, deterministic snapshots and typed boundaries for a desktop player. Existing command-line workflows remain functional. This milestone does not claim the app or looping UI exists.

## Tasks

- [x] M1-T1: inspect the current revision and run the baseline suite. Inventory settings, launchers, modulation/constraint tests and compatibility risks. Preserve the actual current settings.json values.
- [x] M1-T2: create a small Windows PySide6 install/launch/close and packaging-feasibility spike. Record tested versions and choose a deployment path; keep speculative UI code separate from the music engine.
- [x] M1-T3: extract validated settings, pitch/key helpers, chord constraints, transition engine and structured decision data into a package. Keep generate.py as a compatible CLI adapter.
- [x] M1-T4: add stable voice IDs. Preserve IDs when display order changes or pitches cross; the engine must not deduce moving voices using ambiguous sorted-set differences once IDs are available.
- [x] M1-T5: define versioned engine snapshots and PRNG JSON encoding with range/shape validation. Capture effective random seeds and cooldown placeholder state. Restore without executing arbitrary session data.
- [x] M1-T6: define immutable history-event and config-revision types, plus typed command/event contracts for Generate/Replay/Loop, transport phases, acknowledgements, errors and cancellation. Identify the one authoritative state owner.
- [x] M1-T7: document module boundaries, data schema examples and compatibility decisions in `docs/architecture.md`; add fixtures and migrate regression coverage.

## Acceptance criteria and validation

| Gate | Scenario | Required proof |
|---|---|---|
| M1-A1 | Legacy preview, finite MIDI export, port listing and panic entry points remain available | CLI smoke output and parsed MIDI events; panic uses a recorded sink for automated tests |
| M1-A2 | Three pitches, range/span floor, weighted moves and all-octave modulation remain correct | Baseline-equivalent tests plus adversarial constraint fixtures |
| M1-A3 | A voice crosses another pitch and remains the same voice ID | Domain identity test covering snapshot save/restore |
| M1-A4 | Restore a mid-walk snapshot and reproduce 100 subsequent transitions under the same commands | Exact event/state equality, not just the initial seed |
| M1-A5 | Invalid PRNG/schema data and all-zero/negative/non-finite weights are rejected | Negative tests; no state mutation on failure |
| M1-A6 | Import engine modules on a machine without opening a MIDI device or constructing QApplication | Headless import/test command |
| M1-A7 | Native UI spike launches and closes on Windows; dependency and packaging choice are substantiated | Environment/version record, launch evidence and deployment-spike result |

Use the existing `.venv\Scripts\python.exe -m unittest -v test_generate` as baseline until test discovery is migrated. Record the new full-suite command and keep a compatibility command documented. Avoid deleting assertions merely to accommodate refactoring.

## Delegation

Orchestrator owns architecture and command/schema contracts. A strong engine worker owns domain extraction and snapshots; another worker may explore the UI/deployment spike independently. An independent validation worker designs crossing, snapshot and compatibility fixtures. No two workers edit the shared contracts concurrently.

## Completion evidence

Produce `docs/validation/MILESTONE_1_RESULTS.md` with A1–A7 outcomes, commands, revision, tested dependency versions, screenshot location for the spike, and known limitations. Include actual test counts. Record new schemas and the next milestone's stable imports/interfaces.

Exit gate: all criteria proven, baseline behavior preserved, contracts reviewed by the orchestrator, and no untracked experimental runtime assets accidentally included. Commit/push only according to active user authorization.
