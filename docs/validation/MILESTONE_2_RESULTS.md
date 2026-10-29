# Milestone 2 results

Baseline: 57c3dc1, local main checkout, uncommitted implementation.
Environment: Windows-11-10.0.26200-SP0, Python 3.12.10.
Owner: orchestrator. Status: Complete.

| Gate | Scenario | Status | Evidence |
|---|---|---|---|
| M2-A1 | Play and Next emit three owned notes; Pause waits through full hold/gap; Stop interrupts promptly | Pass | Fake-clock playback tests + native-gui-tests.txt; three owned notes, Next/Pause full boundaries and prompt Stop |
| M2-A2 | Change hold from 2 to 10 during a held chord | Pass | Independent config/reseed/key boundary test (.2 to .7 hold / .4 to .8 gap); onset snapshots preserve existing gap |
| M2-A3 | Enter malformed, all-zero and then valid weights while playing | Pass | Native GUI test_policy_locks_and_invalid_weights_during_live_hold and invalid Apply sticky-feedback regression |
| M2-A4 | Stop/Panic during a long gap; close during hold; repeated commands | Pass | Playback/adversarial rapid command, long gap, device loss, close tests; midi-receipt-final.json 20 finite Stop/Panic trials |
| M2-A5 | Disconnect/switch output or channel | Pass | Idle output_channel route test (channel 7), active change rejection, original-channel cleanup, failed connect route retention and load detachment |
| M2-A6 | Edit range to exclude a current pitch; change seed/key/mode | Pass | Atomic invalid range/config and impossible New Phrase tests; explicit reseed/key boundary logs; GUI New Phrase path |
| M2-A7 | Missing synth/MIDI prerequisites | Pass | Native Preview opens with no selected output; explicit connection errors/recovery; bundled RtMidi and refreshable picker |
| M2-A8 | Actual Windows app with loopMIDI→Surge | Pass | midi-receipt-final.json actual loopMIDI output Surge Generative 1/input Surge Generative 0; surge-midi-meter.png shows 3 voices and output; user listening confirmed |

Final qualification: 90 tests pass in full-suite.txt; native Windows GUI mouse/keyboard tests pass; workflow.json is a single native end-to-end session. Final build identity: build-manifest.json. Packaged native Save/Open restored five events silently; repeated final-package loops saved the identical history and complete engine snapshot. See PACKAGING_RESULTS.md.
