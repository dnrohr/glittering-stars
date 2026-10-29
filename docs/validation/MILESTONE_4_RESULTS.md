# Milestone 4 results

Baseline: 57c3dc1, local main checkout, uncommitted implementation.
Environment: Windows-11-10.0.26200-SP0, Python 3.12.10.
Owner: orchestrator. Status: Complete.

| Gate | Scenario | Status | Evidence |
|---|---|---|---|
| M4-A1 | Continue from an old event with recorded state/settings | Pass | Independent Continue from old anchor next100 decisions identical, original12 retained; save-before-first-child regression |
| M4-A2 | Explore from the same anchor | Pass | GUI Explore child creation plus Engine effective seed and ancestry; parent futures retained |
| M4-A3 | Edit a chord and audition/continue | Pass | Immutable edited anchor tests with RNG/cooldown copied and timing/config aligned; real dialog/button path; explicit audition |
| M4-A4 | Save/open a multi-branch session while transport has been active | Pass | Session/controller exact roundtrips including mode/cursor/branches/selection/RNG; real MIDI port detached on load (silent) |
| M4-A5 | Interrupted/failed save, corrupt JSON, unknown future schema, legacy file | Pass | Interrupted os.replace and corruption tests; future format replay-only; pending-context validation; legacy/preset default fixtures |
| M4-A6 | Export a mixed-key selection beginning inside a branch | Pass | Parsed MIDI absolute-rounded onset/release/channels/velocities/initial key/key changes/final gap from selection mid-branch |
| M4-A7 | Loop with overrides, export one pass and N passes | Pass | Recorded/override exports one and three passes tested; export leaves events and generator untouched |
| M4-A8 | GUI save/open/edit/branch workflow | Pass | Real Qt save/open/preset/import/export and branch/edit widget/controller tests; asynchronous IO; explicit active-branch export; packaged-workflow.png, packaged-final-loop.png and final native Save/Open verified |

Final qualification: 90 tests pass in full-suite.txt; native Windows GUI mouse/keyboard tests pass; workflow.json is a single native end-to-end session. Final build identity: build-manifest.json. Packaged native Save/Open restored five events silently; repeated final-package loops saved the identical history and complete engine snapshot. See PACKAGING_RESULTS.md.
