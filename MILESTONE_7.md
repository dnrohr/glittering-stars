# Milestone 7 — Listening-aware experiments

Status: Optional / not started. Not required for v1.
Dependency: [Milestone 6](MILESTONE_6.md) plus explicit user go-ahead to implement these experiments.
Requirement: LAB-01. This file preserves discussed ideas without silently expanding the required app delivery.

## Outcome

An optional adaptive gap can wait for the synth's reverb to decay, and an optional Surprise macro can steer a validated range of musical exploration settings. Fixed-gap playback and independent controls remain fully available.

## Tasks

- [ ] M7-T1: evaluate explicit Windows loopback/audio-source capture with Surge. Record source capabilities, device routing, installation footprint and timing behavior; choose a tested dependency rather than assuming loopback availability.
- [ ] M7-T2: implement visible input meter/source selection, dBFS threshold, quiet-window duration, minimum wait, maximum wait and fixed-gap fallback. Audio analysis must be outside the MIDI timing path.
- [ ] M7-T3: define post-note-off adaptive waiting: wait at least minimum duration, require continuous quiet window, and proceed no later than maximum wait. Report whether each gap ended by quiet detection, timeout or fallback.
- [ ] M7-T4: handle absent/mismatched input, hot unplug, analysis stalls, noise and silence without hangs. Never implicitly enable microphone capture. Stop/Panic interrupts the analysis wait.
- [ ] M7-T5: design a bounded Surprise mapping over explicitly chosen step/direction/modulation controls. Show effective settings, restore the base preset, preserve hard constraints/locks and record every applied revision.
- [ ] M7-T6: persist optional settings, define replay/export semantics and add source/timing diagnostics and help. Recorded loop timing remains fixed; adaptive replay is a separately labeled opt-in override whose observed timing must be recorded if exported.

## Acceptance criteria and validation

| Gate | Scenario | Required proof |
|---|---|---|
| M7-A1 | Synthetic decays, transient dips, continuous noise and immediate silence | Known threshold/quiet-window outcomes, minimum/maximum bounds, and no premature transient-triggered onset |
| M7-A2 | Device missing, source unrelated to Surge, hot unplug or stalled analyzer | Visible source/error state and fixed-gap fallback; MIDI remains controllable |
| M7-A3 | Real Surge reverb with explicit source | Source/meter evidence plus observed adaptive wait; no guarantee of literal mathematical silence |
| M7-A4 | Stop/Panic during maximum adaptive wait | Immediate cleanup command path remains within M6 response target |
| M7-A5 | Sweep Surprise, restore base, save/restore and exact replay | Reversible effective mapping, recorded revisions, no hidden RNG/state mutation and no constraint/lock violation |
| M7-A6 | Optional controls disabled | Fixed-gap playback and independent musical controls behave exactly as the qualified v1 contract |

## Delegation

Strong worker for capture/timing design, another for synthetic-signal validation, and UI worker for source/meter/mapping controls after the spike. Orchestrator owns the decision to accept the capture dependency and the distinction between captured silence, timeout and unsupported devices.

## Completion evidence

If authorized, create `docs/validation/MILESTONE_7_RESULTS.md` with A1–A6, the measured audio-source setup and synthetic fixtures. Otherwise leave this milestone explicitly Optional / not started. Do not manufacture a completion state to finish the v1 roadmap.
