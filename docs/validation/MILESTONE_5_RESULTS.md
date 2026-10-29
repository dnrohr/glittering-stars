# Milestone 5 results

Baseline: 57c3dc1, local main checkout, uncommitted implementation.
Environment: Windows-11-10.0.26200-SP0, Python 3.12.10.
Owner: orchestrator. Status: Complete.

| Gate | Scenario | Status | Evidence |
|---|---|---|---|
| M5-A1 | Moving-note fourth/seventh landing with forced success/failure | Pass | Original octave-wide fourth/seventh fixtures plus domain one-roll/zero/initial/blocked eligibility and locked octave veto |
| M5-A2 | C→G proposal from voiced C3–E4–F4 | Pass | Corrected C-sharp foreign-tone rejection; independent C-natural acceptance fixture. User explicitly confirmed scale-membership correction |
| M5-A3 | G–B–D candidate in C | Pass | Pivot candidate changes context without altering pitches; all-key policy walks check resulting membership |
| M5-A4 | Pivot candidate fits both adjacent keys; one direction disabled; roll fails | Pass | Independent fake-RNG fixture: two eligible directions, one chosen roll, failed roll has no opposite retry; disabled direction excluded |
| M5-A5 | Locked voice crosses display order; locked F octave during F→F# modulation | Pass | Stable crossing ID/snapshot tests and octave lock veto atomic tests; replay unaffected by locks |
| M5-A6 | All voices locked; no legal candidates; boundary direction probability 0/1 | Pass | All-locked and direction extremes independent fixtures explain repeat/no fallback; finite candidate enumeration |
| M5-A7 | Allowed-key/fifths limits and cooldown N, including repeats | Pass | Destination/fifths/cooldown tests including repeats; independent nonzero cooldown save/load + 100 replay cycles + child continuation |
| M5-A8 | Spacing/range/octave controls across all keys and policies | Pass | All twelve keys/four policies/spacing/octave property walks plus canonical initial-candidate-set equivalence |
| M5-A9 | Save, load, loop and branch with new settings | Pass | Locks/cooldown session roundtrip, preserved replay engine state, child continuation consumes exactly one cooldown slot |
| M5-A10 | Change policies and locks during playback in the app | Pass | Native GUI policy/locks/invalid-weight changes during hold; boundary snapshot reflects selected policy/locks; inspector reasons persist |

Final qualification: 90 tests pass in full-suite.txt; native Windows GUI mouse/keyboard tests pass; workflow.json is a single native end-to-end session. Final build identity: build-manifest.json. Packaged native Save/Open restored five events silently; repeated final-package loops saved the identical history and complete engine snapshot. See PACKAGING_RESULTS.md.
