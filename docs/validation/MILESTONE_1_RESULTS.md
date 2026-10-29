# Milestone 1 results

Baseline: 57c3dc1, local main checkout, uncommitted implementation.
Environment: Windows-11-10.0.26200-SP0, Python 3.12.10.
Owner: orchestrator. Status: Complete.

| Gate | Scenario | Status | Evidence |
|---|---|---|---|
| M1-A1 | Legacy preview, finite MIDI export, port listing and panic entry points remain available | Pass | CLI adapter original 12 tests + tests.test_cli_adapter; m1-preview.txt, m1-ports.txt; parsed finite MIDI tests |
| M1-A2 | Three pitches, range/span floor, weighted moves and all-octave modulation remain correct | Pass | Original CLI invariant suite + tests.test_domain + tests.test_harmony_acceptance all-key/policy/spacing walks |
| M1-A3 | A voice crosses another pitch and remains the same voice ID | Pass | test_chord_constraints_and_voice_identity_survive_crossing_and_restore; native GUI crossing lane test |
| M1-A4 | Restore a mid-walk snapshot and reproduce 100 subsequent transitions under the same commands | Pass | test_snapshot_restore_reproduces_one_hundred_transitions; independent historical continuation 100 decisions |
| M1-A5 | Invalid PRNG/schema data and all-zero/negative/non-finite weights are rejected | Pass | Bad config/RNG domain fixtures and session adversarial fixtures, relative weights overflow/negative seed tests |
| M1-A6 | Import engine modules on a machine without opening a MIDI device or constructing QApplication | Pass | Independent subprocess domain import: mido/PySide6 absent from sys.modules, no device/UI initialization |
| M1-A7 | Native UI spike launches and closes on Windows; dependency and packaging choice are substantiated | Pass | Native Windows launch/close + repeatable PyInstaller build (ICU shadowing fixed); native-desktop-initial.png, packaging evidence |

Settings preservation: `git diff -- settings.json` empty. New CLI sequences are intentionally versioned; all original assertions remain. Commands executed by orchestrator on local Windows; test log is actual output.

Final qualification: 90 tests pass in full-suite.txt; native Windows GUI mouse/keyboard tests pass; workflow.json is a single native end-to-end session. Final build identity: build-manifest.json. Packaged native Save/Open restored five events silently; repeated final-package loops saved the identical history and complete engine snapshot. See PACKAGING_RESULTS.md.
