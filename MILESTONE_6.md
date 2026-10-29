# Milestone 6 — Windows release qualification

Status: Complete; see docs/validation/MILESTONE_6_RESULTS.md. Required for v1. Dependency: [Milestone 5](MILESTONE_5.md).
Requirements: QA-01, ARCH-01 distribution, and integrated acceptance of all required specification IDs.

## Outcome

A Windows desktop build the user can launch directly, with proven generation, live control, selection looping, composition, persistence and MIDI behavior. This milestone closes the end-to-end product scope rather than adding unrelated features.

## Tasks

- [x] M6-T1: build a requirement-to-evidence matrix covering every required ID and all M1–M5 gates. Inspect the implementation and tests, not just prior green reports.
- [x] M6-T2: run the integrated regression/GUI suite and fix lifecycle, data loss and replay correctness failures. Test rapid command sequences, missing devices, save/load during transport, and shutdown.
- [x] M6-T3: exercise an actual Windows app→loopMIDI→Surge route. Capture real MIDI timing and correlate screenshots with playback behavior. Record whether audio was listened to versus inferred from meters/messages.
- [x] M6-T4: measure response and timeline behavior with 10,000 history events, offscreen rendering/virtualization and background saves. Ensure selected history is never silently dropped.
- [x] M6-T5: produce a repeatable packaged Windows build and launcher. Test from a path with spaces, outside the repo, without relying on the repo `.venv`; validate user data paths and prerequisite recovery.
- [x] M6-T6: complete keyboard/selection accessibility, DPI checks, app help, setup guide, session compatibility notes, license/dependency notices and release limitations.
- [x] M6-T7: perform independent final review and user-workflow demonstration. Record build revision/hash and exact commands. Publish artifacts only under the user's active authorization.

## Acceptance criteria and validation

| Gate | Scenario | Required proof |
|---|---|---|
| M6-A1 | Full required specification audit | Matrix: each requirement and milestone gate linked to implementation, meaningful test and observed evidence where applicable |
| M6-A2 | Generate, edit settings, select 4–7, loop, replace selection, pause/next, branch, edit, save/load, export | One repeatable end-to-end GUI procedure; exported MIDI and restored session agree with history |
| M6-A3 | Close/error/Stop/Panic throughout hold/gap/replay | No leaked notes, deadlocked worker or late burst; intentional panic behavior documented |
| M6-A4 | Normal UI activity while sending MIDI | Measured note-on spread ≤20 ms and duration error ≤50 ms target on tested machine; cleanup dispatch ≤100 ms target; record sample count and p50/p95/max |
| M6-A5 | 10,000-event history, repeated loops and save | Usable selection/scroll, no unbounded duplicate-event growth or lost selection, note-off not delayed by saving |
| M6-A6 | Packaged app on Windows without developer runtime | Launch, generate/loop and save/open smoke evidence; missing-prerequisite recovery works |
| M6-A7 | Keyboard-only selection/loop and 100/150/200% DPI | Actual interaction evidence; no inaccessible primary control or clipped critical feedback |
| M6-A8 | Final docs and distribution | Clean build instructions, accurate limitations, schema/version notes and dependency notices; no personal data or runtime caches included |

For timing measurements use timestamped MIDI receipt, define onset/release reference points, and collect at least 100 chord events plus 20 Stop/Panic trials. Virtual MIDI may be used for the longer stress sample. Avoid claiming hard real-time guarantees; if a target is missed, record it and fix or explicitly obtain acceptance of the limitation before calling the gate passed.

## Delegation

Independent QA/review worker owns adversarial test execution and evidence collection. Build/deployment worker owns packaging and clean-environment checks. The orchestrator runs the integrated acceptance audit itself and resolves discrepancies between results. Agent self-reports and screenshots of a nonfunctional mockup are insufficient.

## Completion evidence

Create `docs/validation/MILESTONE_6_RESULTS.md` and the final requirement matrix. Include Windows/dependency versions, build identity, all commands, logs, screenshots, MIDI captures or parsed comparisons, and explicit pass/fail/unverified outcomes. Update roadmap status only after this evidence is inspected.

Exit gate: M1–M6 complete with no unverified required gate. Optional M7 stays separate. A full suite pass alone does not prove packaged behavior or actual Surge integration.
