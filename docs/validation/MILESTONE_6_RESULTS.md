# Milestone 6 results

Baseline: 57c3dc1, local main checkout, uncommitted implementation.
Environment: Windows-11-10.0.26200-SP0, Python 3.12.10.
Owner: orchestrator. Status: Complete.

| Gate | Scenario | Status | Evidence |
|---|---|---|---|
| M6-A1 | Full required specification audit | Pass | ACCEPTANCE.md links every required ID and all milestone A gates to actual code, tests and observed evidence |
| M6-A2 | Generate, edit settings, select 4–7, loop, replace selection, pause/next, branch, edit, save/load, export | Pass | Native Qt end-to-end paths, exact MIDI comparison and user listening confirmation; workflow.json (one native session), packaged-final-loop.png and native Save/Open comparison |
| M6-A3 | Close/error/Stop/Panic throughout hold/gap/replay | Pass | Lifecycle, rapid commands, long gaps, device failures and shutdown suite; channel-aware active registry and panic ordering |
| M6-A4 | Normal UI activity while sending MIDI | Pass | midi-receipt-final.json: 100 chord onsets/300 notes, hold/gap samples, p50/p95/max and20 cleanup trials. Max spread 1.585ms / hold14.557ms / gap13.917ms / dispatch1.028ms |
| M6-A5 | 10,000-event history, repeated loops and save | Pass | capacity.json + capacity-window.png: real10000 events, native render/scroll, background save and exact restore; no RNG/history growth or lost selection; max hold error14.510ms |
| M6-A6 | Packaged app on Windows without developer runtime | Pass | Final clean PyInstaller folder, external path with spaces and no developer runtime; packaged-external.json exit0 with no developer Python on PATH; packaged-final-loop.png and final saved engine/history equality |
| M6-A7 | Keyboard-only selection/loop and 100/150/200% DPI | Pass | native-gui-tests.txt real Windows QPA keyboard/mouse and shortcuts; spike/dpi effective100/150/200% screenshots with tabbed Inspector |
| M6-A8 | Final docs and distribution | Pass | User guide, schema/architecture/decisions, packaging instructions, full dependency licenses, source/build manifests; no remote publication |

Final qualification: 90 tests pass in full-suite.txt; native Windows GUI mouse/keyboard tests pass; workflow.json is a single native end-to-end session. Final build identity: build-manifest.json. Packaged native Save/Open restored five events silently; repeated final-package loops saved the identical history and complete engine snapshot. See PACKAGING_RESULTS.md.
