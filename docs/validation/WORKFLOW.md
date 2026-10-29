# Repeatable native end-to-end procedure

Use the development launcher or the whole packaged application folder. Do not run the CLI simultaneously on the same output/channel. Test harnesses isolate LOCALAPPDATA.

1. Launch in Preview, or refresh outputs and Connect MIDI to Surge Generative. Confirm actual port/channel in the connection label. Use12 chords and short hold/gap for a finite test, Apply, and Generate.
2. During hold, enter all-zero weights and Apply: the error stays visible and applied settings remain intact. Restore valid weights, change timing/policy/locks, Apply. The current hold/full gap stay intact; the next onset uses the complete revision.
3. Drag events4–7 or click event4 then Shift+Down three times. Ctrl+L prepares Loop Selection. From Generate, finish the active full event/gap then start event4; from idle press Play. History must stop growing.
4. Compare the four stored pitches/keys/timing/velocity through several cycles. Full final gap precedes wrap. Replace selection during hold/gap; Pause/Next/Loop Off must not Generate. Stop releases; Panic additionally silences.
5. Stop, select one anchor and open Inspector. Continue with Recorded Settings (default), retaining parent futures. Switch branches. Explore records a new seed. Edit creates a child anchor; audition explicitly, without changing generator RNG/history.
6. Save Session to a temporary named path. Change state, Open it, and verify silent/idle restore of history, branches, selection, cursor and settings. MIDI is disconnected until explicit reconnect. A corrupt file must leave the session intact. Save/load a separate preset with no history.
7. Export Selection MIDI once or a finite number of passes; explicitly choose recorded/override timing. Export Active Branch is separate and includes ancestors only through anchors. Parse all on/off/key/velocity/channel events and final gap against stored events.
8. Close during hold/gap/replay; repeat with missing output. Reopen the packaged executable from a folder with spaces without repo Python. Check keyboard selection and controls at effective100/150/200% scaling.

Commands: `python -m unittest discover -v`; native Qt `QT_QPA_PLATFORM=windows python -m unittest -v tests.test_gui_acceptance`; real finite MIDI `python tools/qualify_midi.py --run --output "Surge Generative 1" --input "Surge Generative 0" --report docs/validation/midi-receipt.json`; capacity `python tools/qualify_capacity.py`. The real MIDI script records receipt, not sound. `tools/audition_passage.py` is the finite audible demonstration; user confirmation is separate.
