# Fresh orchestrator handoff

This is a ready-to-submit implementation task for a fresh orchestrator. This planning delivery writes the task; it does not start a new chat or implement the app. Submit the task below with `C:\Users\dnroh\Documents\glittering-stars` as the workspace.

## Task to give the orchestrator

Implement the Glittering Stars local Windows desktop application described in this repository. Read `SPECIFICATION.md`, `ROADMAP.md`, and `MILESTONE_1.md` through `MILESTONE_7.md`. Complete required milestones 1–6 in dependency order. Milestone 7 is optional and requires separate user go-ahead; do not treat it as required v1 work or quietly substitute it for required features.

You are the implementation orchestrator. Delegate bounded work to agents with capabilities appropriate to the task. Own architectural decisions, integration, test strategy, and final test validation yourself. Do not accept a worker's claim of success without inspecting the changes and independently running the applicable integrated checks. Persist through implementation and repair; do not stop at scaffolding, a UI mockup, or a passing legacy suite.

Preserve the current functioning CLI and the user's settings. The most important new workflow is: change parameters live, generate chords, highlight a contiguous selection, stop generating, and loop exactly that passage with full gaps. Then support editing/branching from it, durable sessions and MIDI export, whole-chord-fit/pivot modulation, voice locks and musical limits, and a tested Windows build.

Use the following operating contract and milestone files as the detailed instructions. If repository evidence contradicts this brief's baseline, inspect the current state and update the implementation plan without discarding accepted musical behavior.

## Starting facts to revalidate

- Repository: `C:\Users\dnroh\Documents\glittering-stars`.
- Remote inspected during planning: `https://github.com/dnrohr/glittering-stars.git`; implementation may use a different checked-out branch, so inspect before changing Git state.
- Last inspected implementation commit: `57c3dc1`, `Add generative MIDI chord player with adjacent-key modulation`.
- Python CLI, mido/python-rtmidi, Surge XT standalone and loopMIDI route. No desktop app code or UI dependency has been installed by this planning task.
- Verified baseline: 12 passing cases from `.\.venv\Scripts\python.exe -m unittest -v test_generate` on 2026-10-28.
- Current checked-in settings at planning time: C3–C5, hold 2 s, silence 4 s, steps 0/1/2 with weights 0.1/0.6/0.3, continuous mode, C starting key, 15% trigger modulation each direction. Re-read rather than overwriting later user edits.
- Existing source files: generate.py, test_generate.py, settings.json, requirements.txt, Play.cmd, Stop Notes.cmd, Example.mid and README.md.
- The planning documents describe future requirements. An unchecked box or written acceptance test is not proof the feature exists.

Inspect working-tree status and applicable AGENTS.md/skill instructions before editing. Preserve unrelated and uncommitted user changes. Use the current checkout unless isolation is needed or the user instructs otherwise. Do not create user-owned chats for internal subtasks; use the session's subagent tools.

## First actions

1. Read the planning files and current implementation. Run the baseline suite and short preview; enumerate devices without starting unattended indefinite audio.
2. Create an implementation status/acceptance ledger with requirement IDs, milestone gates, owner, dependencies, tests, evidence paths and pass/fail/unverified status. Mark future app gates unverified.
3. Execute M1's native UI/deployment spike and define domain, command/event, snapshot and history contracts before distributing overlapping implementation work.
4. Dispatch bounded M1 tasks, integrate them and independently validate M1. Continue through M2–M6. Keep the milestone sequence and prioritize selection looping at M3.

Do not make routine implementation choices into repeated permission questions. When a genuine ambiguity affects user-visible behavior, state the proposed default, continue independent work and ask only for the missing decision. If a required Windows/MIDI check cannot run, keep that gate unverified and report the specific missing capability; do not replace it with an easier claim.

## Agent assignment by capability and risk

Choose from models/reasoning levels actually exposed by the active runtime, observing its override restrictions. Do not assume named models in a previous chat remain available. If overrides are not authorized/available, use inherited settings and scope tasks to the worker's verified results. Appropriate intelligence is a responsibility for task routing and review, not a reason to invent a model ID.

| Work type | Capability/reasoning target | Oversight |
|---|---|---|
| Architecture, transport state machine, PRNG restoration, schema/version decisions | Strongest suitable reasoning available | Orchestrator owns contracts and reviews implementation |
| Modulation policies, octave-wide alterations, stable-ID locks, concurrency failures | High reasoning with domain/state understanding | Independent adversarial fixtures; orchestrator adjudicates ambiguous outcomes |
| Timeline selection, branch UX and Qt command/event integration | Strong UI/state implementation capability | Real widget/controller tests and Windows inspection |
| Forms, already-specified widget bindings, fixture plumbing, docs and packaging scripts | Standard capable worker after contracts stabilize | Escalate when a task crosses timing/state boundaries |
| Independent integration/GUI QA and failure investigation | High reasoning; separate from the primary implementation author when possible | Orchestrator still executes final validation |

Use a cheaper/lighter worker only for a bounded task with a settled contract, disjoint files and concrete checks. Escalate after repeated failures, contract uncertainty, nondeterministic behavior, data-loss risk or an unproven test strategy. Reassign or pair on the hard part rather than spending many cycles patching symptoms. Do not have the agent that changed a requirement be its only reviewer.

With four concurrency slots, keep the orchestrator plus at most three workers. Suggested active roles:

- **Engine/domain:** musical engine, snapshots, constraints and harmonic policies.
- **Desktop/interaction:** Qt models, forms, timeline and selection against agreed interfaces.
- **Validation/integration review:** independent fixtures, controller/GUI tests, failure analysis and evidence.

Persistence/export or packaging can take a freed slot later. Keep workers productive on independent tasks; avoid concurrency for its own sake. The orchestrator must retain capacity to read diffs, integrate and validate rather than acting only as a message relay.

## Worker task template

Each assignment must contain:

```text
Task ID and milestone:
Outcome and exact specification/acceptance IDs:
Current base revision and relevant files/contracts:
Owned files/modules; explicitly excluded shared files:
Inputs/dependencies and collaborators:
Required behavior, edge cases and invariants:
Tests/evidence the worker must produce:
Definition of done and known limitations:
Return format: changed files, design decisions, commands/results,
evidence paths, unresolved risks and any requested interface change.
```

The orchestrator owns shared contracts/schema enums unless it assigns that ownership explicitly. In a shared checkout, workers may not reset, discard, overwrite or commit another worker's edits. In isolated worktrees, inspect and integrate the actual patch before acceptance. Do not tell workers to push competing branches or merge remotely without the user's active authorization.

## Invariants workers must receive

- Exactly three distinct pitches; inclusive MIDI range; span at least seven semitones; no hidden melody.
- Relative step weights, single step draw, zero repeats and explained blocked moves.
- Ordinary moves affect one stable voice ID. Accepted trigger modulation alters every octave of the triggering pitch class together, subject to the full set of constraints and locks.
- Initial/repeated/unchanged trigger notes do not roll modulation. Whole-chord-fit and pivot policies are distinct.
- One owner of MIDI notes and the worker handle; normal cleanup preserves reverb tails; Panic is explicitly immediate.
- Edits apply atomically at documented boundaries. Invalid drafts never become applied state.
- Replay and looping never generate, consume randomness or grow history. Wrap includes the final full gap.
- Immutable event IDs and branch snapshots underpin editing/continuation. A seed alone does not resume a historical state.
- Saved sessions load silently and safely. Device errors and unsupported files are explicit recoverable states.

## Orchestrator-owned validation

Before coding a subsystem, derive its observable behavior from the specification and identify tests that would fail if a superficially plausible implementation were wrong. Ask the validation worker for independent boundary cases, not tests that merely repeat internal helpers.

After each worker submission:

1. Inspect changed files and shared-interface differences. Confirm scope and preservation of user changes.
2. Run the worker's focused checks and add missing edge cases. Inspect whether assertions establish the named requirement.
3. Integrate dependent work and run the documented full suite, CLI regression checks and relevant GUI tests yourself.
4. Perform real Windows/MIDI validation at gates that require it. Capture UI state, MIDI receipt and timings separately; do not claim audio was heard if only a meter was observed.
5. Record results in `docs/validation/MILESTONE_<num>_RESULTS.md`, update the acceptance matrix, and repair failures before marking the milestone complete.

Baseline commands, valid for the current repo before refactoring:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_generate
.\.venv\Scripts\python.exe .\generate.py --preview --chords 8 --seed 42
.\.venv\Scripts\python.exe .\generate.py --list-ports
git diff --check
```

If `.venv` is missing, create it with Python and install requirements. The GUI spike adds tested dependencies deliberately; document the resulting environment and update the test commands as the package grows. Do not repeatedly run only these four baseline commands and claim the future app is validated.

Critical adversarial cases:

- Long gap followed by Stop/Panic/Close; rapid Play/Pause/Next/Stop commands; disconnect and reconnect without note bursts.
- Invalid numeric edits, zero weights, structural live edits excluding a current pitch, reseed/key changes and queued revisions.
- Mixed-key and single-event loops; replace selection during hold/gap; repeated cycles with unchanged RNG/history; timing override versus recorded data.
- Restore a non-initial PRNG state; edited child anchors; incompatible engine/schema versions; interrupted save; exact selection MIDI export with final gap.
- Both Fs/Bs altered on modulation; locked octave vetoes the whole change; resulting chord membership in Whole chord fits; Pivot changes key without pitch alteration.
- Voice crossing, all voices locked, impossible direction/spacing, key restrictions and replay-isolated cooldown.
- Ten-thousand-event timeline behavior, keyboard selection and Windows DPI; packaged launch without repo Python dependencies.

Store evidence with the revision, environment, exact commands/procedure, observed result and pass/fail/unverified label. Do not fabricate screenshots, timing reports or hardware checks. A test count is not a substitute for mapping coverage to requirements.

## State and progress reporting

Keep milestones and task statuses honest: Planned, In progress, Validation pending, Complete or a specifically explained blocker. Update the ledger after inspected evidence. Provide concise progress updates centered on working behavior, findings and next validation risk.

At context handoff, record the current branch/revision and dirty files, completed gates, active worker IDs/worktree paths, command/session handles that are actually still running, evidence files and next concrete actions. Revalidate live handles in the next instance; do not assume a background worker is running because a note says so.

## Delivery and completion audit

Delivery means required M1–M6 behavior is implemented and validated, with app launch/build instructions, readable help, a packaged Windows artifact, schema notes, actual test output and known limitations. Optional M7 remains separate unless the user opts in.

Before completion, inspect every required specification ID and milestone gate against the actual code, tests, UI/MIDI evidence and build. Mark uncertain evidence unverified and continue meaningful work. Do not declare completion merely because a plan exists, a worker finishes, or a suite is green. The orchestrator owns the final outcome.

Repository operations follow the user's current authorization. The earlier CLI push is historical context; this handoff does not by itself authorize public releases, destructive operations, or remote publishing. Report a concrete reviewable result when approval is genuinely needed, and identify any actual tool-policy block rather than inventing one.
