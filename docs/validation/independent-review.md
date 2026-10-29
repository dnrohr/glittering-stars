# Independent transport and MIDI review

Review date: 2026-10-28. This is unit-level evidence against the current working tree. It is not the M6 release qualification or a real Surge audio claim.

tests/test_transport_adversarial.py adds eight cases around the real Controller, Worker, and Qt window: queued Play cancellation by Stop and later deliberate Play; persistent device loss during hold; channel change attempts during replay and old-channel release; finite chord count with the complete last gap; config, reseed, and key application at the next onset; edit, continuation, and silent session restore; a 10,000-event worker view; and a real Qt keyboard selection/loop with unchanged RNG and history.

Command: .\.venv\Scripts\python.exe -m unittest -v tests.test_transport_adversarial. Result: 8 passed. The 10,000-event view returned all records within the test's 2-second bound on this Windows environment. The bound checks the controller snapshot path, not timeline paint, scrolling, file save time, or MIDI deadlines during a save.

The persistence/export and domain review was separately checked with .\.venv\Scripts\python.exe -m unittest -v tests.test_sessions tests.test_session_adversarial tests.test_domain: 21 passed. The broader integrated suite remains the orchestrator's responsibility.

The safe inventory command .\.venv\Scripts\python.exe tools/qualify_midi.py --list-ports observed output ports Microsoft GS Wavetable Synth 0 and Surge Generative 1, and input Surge Generative 0. The finite qualification harness opens the real Qt MainWindow, selects events 4–7 through a mouse anchor plus Shift+Down and Ctrl+L, checks three full exact loop passes including the wrap, and then collects 20 Stop/Panic receipt trials. It sends chords at 30 ms hold/gap and velocity 24. Its JSON report includes the raw timestamped MIDI receipt, generated event pitches/keys/timing, loop source and receipt sequences, PRNG snapshots, history counts, and note-on spread, hold/gap, and cleanup percentiles. It requires --run and exact port names and uses a temporary LOCALAPPDATA folder.

The first coordinated run sent 300 finite events through loopMIDI to Surge. The observed Surge window showed three voices, output meter activity, and key lights; the script then failed its keyboard selection check because it did not pump Qt events between Shift+Down presses. Windows also refused temporary-data cleanup while the app's autosave worker was still writing.

The corrected 100-event run passed the harness targets on Windows 11 / Python 3.12.10 / Qt 6.12.0. It received all 300 note-ons and note-offs. Note-on spread was p50 0.062 ms, p95 0.238 ms, max 0.834 ms; absolute hold error was p50 1.913 ms, p95 2.911 ms, max 13.609 ms; absolute gap error was p50 2.136 ms, p95 3.308 ms, max 12.713 ms. Across the 12 observed loop transitions, absolute gap error was max 2.848 ms and the shortest gap was 31.358 ms. Twenty Stop/Panic trials had max dispatch 1.161 ms and max receipt 13.676 ms. The selection loop matched events 4–7 for three passes plus the wrap onset; generator snapshot and history count stayed at 100 throughout the loop. The final history count of 120 includes the 20 one-event cleanup trials after looping.

The report field first_selected_key_displayed was sampled after the 20 cleanup trials and therefore reflects the later generator key, not the event-4 loop onset. The harness now captures and checks that label at the selected loop playhead; the offscreen Qt loop test verifies the same UI key-label behavior. The saved MIDI report remains an unmodified record of the measured run. Its timing and loop assertions passed. The separate Surge screenshot shows the observed three-voice meter/key activity; no audio listening is claimed.

Example after coordinating the real route:

    .\.venv\Scripts\python.exe tools/qualify_midi.py --run --events 100 --output "Surge Generative 1" --input "Surge Generative 0" --report docs/validation/midi-receipt.json

One integration defect was sent to the transport owner: editing with a string key such as G leaves the child event key as a string while the edited engine snapshot stores tonic integer 7; session validation then rejects the session. The focused branch test uses integer 7 and passes. Fix the controller to store the normalized engine.key on edit, then add a string-key regression case.
