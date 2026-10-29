# Acceptance ledger

Latest user-requested follow-up: **Regenerate (clear history)** is implemented. Current suite94/94 and rebuilt package validation are in [Regenerate results](REGENERATE_RESULTS.md). Original milestone qualification evidence is retained below.

Baseline 57c3dc177c4dbab06ea3eaed56d565f9dab95302, local main with uncommitted implementation and preserved handoff inputs. Owner: orchestrator. Windows 11 build 26200, Python 3.12.10, PySide6 6.12.0, PyInstaller 6.22.3, mido 1.3.3, python-rtmidi1.5.8. M7 remains optional/not authorized; no remote publishing.

| Milestone | Requirements | Dependency | Owner | Status | Evidence |
|---|---|---|---|---|---|
| M1 | BASE-01/02/03, ENG-01, ARCH-01 foundation | CLI | engine + orchestrator | Complete | [M1 results](MILESTONE_1_RESULTS.md) |
| M2 | LIVE-01/02, MIDI-01, UI-01 | M1 | transport + UI + orchestrator | Complete | [M2 results](MILESTONE_2_RESULTS.md) |
| M3 | LOOP-01/02, UI-01 | M2 | transport + UI + orchestrator | Complete | [M3 results](MILESTONE_3_RESULTS.md) |
| M4 | COMP-01/02 editing, DATA-01/02 | M3 | sessions + orchestrator | Complete | [M4 results](MILESTONE_4_RESULTS.md) |
| M5 | HARM-01/02/03, COMP-02 locks | M4 | engine + orchestrator | Complete | [M5 results](MILESTONE_5_RESULTS.md) |
| M6 | QA-01, ARCH-01 distribution, complete audit | M5 | independent QA + orchestrator | Complete | [M6 results](MILESTONE_6_RESULTS.md) |

Each A-number is individually labeled in its results file. Baseline12 CLI tests passed before implementation; all original assertions remain. settings.json and CLI launchers remain unchanged. CLI now wraps the shared engine; compatible snapshots restore exact future decisions, with no promise of bit-identical old seeded sequences.

## Requirement-to-evidence matrix

| Required ID | Implementation | Verification |
|---|---|---|
| BASE-01 | domain Config/validate_chord/initial sampling | Original invariants; all-key/policy/spacing walks; canonical complete candidate-set comparison |
| BASE-02 | Engine.advance / weighted legal pairs | CLI relative-weight/distribution tests; zero/blocked/direction0/1 fixtures |
| BASE-03 | Engine atomic octave-wide trigger policy | Original fourth/seventh/octave cases; locked-octave veto; no initial/repeat/unchanged roll |
| ENG-01 | Stable Voice IDs, JSON PRNG snapshot/restore | Crossing tests; exact mid-walk next100 decisions; negative-schema/RNG fixtures; headless import |
| LIVE-01 | Controller pending revisions, draft controls | Native invalid/valid edits during hold, config/reseed/key boundary tests, transactional impossible New Phrase |
| LIVE-02 | Mode/phase state machine and Worker barriers | Fake-clock lifecycle/rapid commands; immediate queued Replay/Loop then Play; finite restart; close/error cleanup |
| MIDI-01 | Worker MidiSink, registry, output_channel | Idle/active channel and failed-port-switch tests; single-instance lock; actual receipt timing and synth meter |
| UI-01 | Native controls, voice-lane model, Inspector tabs | native-gui-tests.txt; keyboard/drag/growth/validation; effective100/150/200 DPI captures; packaged workflow |
| LOOP-01 | Immutable UUID event records, ID ranges | Native drag/Shift/keyboard selection and retention; invalid/empty selection errors; inspector metadata |
| LOOP-02 | Frozen playback and separate cursor | 400-event isolation; actual MIDI3 passes+wrap; single-event/full-gap/override/replacement cases; user listening |
| COMP-01 | Continue/Explore child branches | Independent100-decision child comparison, fresh seed, parent future retained, save-before-first-child regression |
| COMP-02 | Edited anchors, stable locks, audition | Edited RNG/cooldown/timing consistency; invalid edit; locked-octave/all-locked fixtures; real widget actions |
| HARM-01 | Off/trigger/whole_chord/pivot | All-key policy walks; corrected C-sharp rejection/C-natural acceptance; one pivot roll/no retry |
| HARM-02 | Key/fifths/cooldown restrictions | Destination/current/start restrictions; nonzero cooldown session/100 loop cycles/child restoration; context log |
| HARM-03 | Span/gap/octave/direction constraints | Property walks across12 keys/4 policies; initial-set equivalence; no forbidden-direction fallback |
| DATA-01 | Schema1 atomic storage + async UI IO | Full state roundtrip; interrupted replace; corrupt/future/legacy/pending-context tests; silent port-detached load;10000 events |
| DATA-02 | Stored-event selection/branch MIDI | Parsed absolute-rounded on/off/channel/velocity/keys/final gap; repeated passes and overrides; branch anchor prefix |
| ARCH-01 | Shared CLI/domain; Python worker/Qt signals; package | Original12 assertions; pure imports; native launch; one-folder build/licenses; LOCALAPPDATA runtime state |
| QA-01 | Independent fixtures + real native validation | full-suite.txt; native-gui-tests.txt; midi-receipt-final.json; audible-demo.json; capacity.json; packaging evidence |

Implementation paths above are under glittering_stars except desktop.py; tests are under tests/ plus test_generate.py. [Repeatable workflow](WORKFLOW.md) gives the end-to-end procedure. [Independent review](independent-review.md) records separate QA and report limitations.

## Observed and corrected failures

- First frozen launch loaded incompatible Git ICU. Excluding its DLLs fixed native Qt launch; clean packaging evidence records this.
- First10000-event background save delayed note-off136ms. Removing nested copies and encoding one event at a time fixed it: latest capacity.json has maximum hold error14.510ms, save2.22s, exact10000-event restore, retained selection and unchanged RNG/history.
- Stale UI mode could turn queued Replay followed immediately by Play into Generate. Play now always delegates to the worker; Generate is separate. Both race regressions pass.
- Keyboard event pumping and two report-only NameErrors were corrected before accepting the successful real MIDI run. Its stale post-cleanup key-label field is explicitly documented in independent-review.md; corrected label capture and actual widget checks pass.
- Actual MIDI evidence:100 onset groups,300 held notes,99 gap samples,20 Stop/Panic trials. Max spread1.585ms, hold error14.557ms, gap error13.917ms, cleanup dispatch1.028ms. Raw receipt and loop source comparisons are in midi-receipt-final.json.
- surge-midi-meter.png shows actual3 voices/lit keys/output meter. The user explicitly confirmed the finite four-chord passage repeated twice with gaps; audible-demo.json records that separate listening evidence.
- The user approved correct major-scale membership: C natural belongs to G major. The erroneous planning example is corrected to C-sharp.

No remote publication, driver installation, synth patch changes, or optional audio capture/Surprise work was performed.

Final rerun: stale selection acknowledgements were found to roll back a newer keyboard gesture. UI selection drafts now retain their command sequence until the authoritative matching/newer acknowledgment; model resets cannot dispatch unintended selections. clear_selection leaves frozen playback intact. Worker command numbering is serialized across UI/I/O submitters. The final real MIDI rerun passes, including the correct first-key widget label (G major), and the native stale-view regression passes.
