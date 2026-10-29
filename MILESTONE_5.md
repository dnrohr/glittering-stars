# Milestone 5 — Musical exploration controls

Status: Complete; see docs/validation/MILESTONE_5_RESULTS.md. Required for v1. Dependency: [Milestone 4](MILESTONE_4.md).
Requirements: HARM-01/02/03 and COMP-02 locks, while preserving BASE and LOOP invariants.

## Outcome

The user can choose how keys change, hold individual voices, constrain harmonic travel and spacing, and bias movement. Every choice is live, inspectable, saved and replay-safe.

## Tasks

- [x] M5-T1: implement the mutually exclusive Off, Moving-note trigger, Whole chord fits and Pivot chord policies. Keep Moving-note trigger as the compatibility default.
- [x] M5-T2: add pitch-class membership tests, admissible adjacent-key enumeration and exactly-one-roll decision records. Whole chord fits checks the complete altered chord; Pivot changes context without retuning notes.
- [x] M5-T3: implement stable-ID voice locks and UI lock controls. All locked produces an explained repeat. Locked octave doublings veto an entire modulation; never change only the unlocked octave.
- [x] M5-T4: add allowed keys, maximum fifths distance and cooldown. Persist counters and reasons; no cooldown advancement during replay.
- [x] M5-T5: add min/max span, neighboring pitch gap, octave-doubling permission and upward-direction probability. Preserve the non-negotiable span floor of seven semitones and distinct pitches.
- [x] M5-T6: integrate controls into atomic live revisions, session/preset schemas, edited-anchor validation, history inspector and continuation behavior. Add migration from earlier session schemas with documented defaults.
- [x] M5-T7: update help, fixtures, state restoration tests and UI examples for each policy and blocked outcome.

## Acceptance criteria and validation

| Gate | Scenario | Required proof |
|---|---|---|
| M5-A1 | Moving-note fourth/seventh landing with forced success/failure | Existing pitch-class-wide transformations preserved; one roll per event; unchanged triggers and step-zero do nothing |
| M5-A2 | C→G proposal from voiced C#3–E4–F4 (corrected with user confirmation) | Whole chord fits rejects C#3–E4–F#4 because C# is outside G; ordinary move and C key retained. C-natural belongs to G major and passes membership. |
| M5-A3 | G–B–D candidate in C | Pivot can change to G without altering notes; ineligible chords do not pivot |
| M5-A4 | Pivot candidate fits both adjacent keys; one direction disabled; roll fails | Defined one-direction-choice/one-roll semantics; no second attempt or probability normalization of chances |
| M5-A5 | Locked voice crosses display order; locked F octave during F→F# modulation | Same voice ID remains locked; entire illegal modulation rejected; ordinary move allowed only if lock-safe |
| M5-A6 | All voices locked; no legal candidates; boundary direction probability 0/1 | Explained repeats; no hangs, hidden retries or movement in forbidden direction |
| M5-A7 | Allowed-key/fifths limits and cooldown N, including repeats | Legal destinations only; exactly N subsequent generated events suppressed; replay does not decrement counter |
| M5-A8 | Spacing/range/octave controls across all keys and policies | Constraint property tests and targeted edge cases; no invalid initial/edited/modulated chord |
| M5-A9 | Save, load, loop and branch with new settings | Schema migration, locks and cooldown restored; exact replay ignores new generation rules until resumed |
| M5-A10 | Change policies and locks during playback in the app | Pending/applied boundary feedback, inspector decisions and MIDI notes agree |

Cover key context explicitly, not only C. Tests should compare transition distributions and invariants, with deterministic fixtures for probability 0 and 1. Whole chord fits and Pivot are separate contracts; renaming the existing mode is not an implementation.

## Delegation

Assign policy/constraint work and independent musical test design to strong reasoning workers. UI binding can proceed in parallel after enums and config fields stabilize. The orchestrator owns algorithm ambiguity, schema integration, and the acceptance run; it must review octave-lock behavior and replay isolation directly.

## Completion evidence

Create `docs/validation/MILESTONE_5_RESULTS.md` with A1–A10 and a policy comparison fixture set. Include screenshots showing policy controls and rejected-modulation reasons, and event-level evidence matching UI decisions to pitches.

Exit gate: all advanced controls are implemented, live, persisted and independently validated; no regressions to selection looping or note cleanup.
