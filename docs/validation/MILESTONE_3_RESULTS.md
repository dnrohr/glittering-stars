# Milestone 3 results

Baseline: 57c3dc1, local main checkout, uncommitted implementation.
Environment: Windows-11-10.0.26200-SP0, Python 3.12.10.
Owner: orchestrator. Status: Complete.

| Gate | Scenario | Status | Evidence |
|---|---|---|---|
| M3-A1 | Generate 12 events; select events 4–7 while another chord is sounding; loop | Pass | Independent generation-to-loop fixture selects 4-7 during hold; first selected event begins after active full gap |
| M3-A2 | Loop a mixed-key passage 100 times | Pass | 400 replayed events in integration + 100 cycles fake-sink playback preserve exact engine snapshot/history; actual MIDI 3 passes + wrap |
| M3-A3 | Loop one chord | Pass | Single-event fake-clock loop retriggers three notes/full gap; no active-note accumulation in playback suite |
| M3-A4 | Change selection mid-hold and mid-gap | Pass | Boundary replacement tests during gap/hold; source mode/first selected event frozen; invalid and empty selections preserve existing playback |
| M3-A5 | Change live controls during exact replay | Pass | Live revision replay isolation/override integration; generator remains pending until Generate; stored history unchanged |
| M3-A6 | Toggle timing override, Pause/Next, disable Loop and Stop | Pass | Loop Off/Pause/Next/Stop same controller; immediate queued replay/loop then Play regression; recorded data unchanged |
| M3-A7 | Select via drag and keyboard while history grows | Pass | native-gui-tests.txt mouse drag + Shift/keyboard selection and growth retention; native DPI 100/150/200 captures |
| M3-A8 | Real app loop through Surge | Pass | Actual MIDI frozen source comparison/raw capture, audible-demo.json 4 events two passes, user explicitly confirmed repeated passage and gaps |

Final qualification: 90 tests pass in full-suite.txt; native Windows GUI mouse/keyboard tests pass; workflow.json is a single native end-to-end session. Final build identity: build-manifest.json. Packaged native Save/Open restored five events silently; repeated final-package loops saved the identical history and complete engine snapshot. See PACKAGING_RESULTS.md.
