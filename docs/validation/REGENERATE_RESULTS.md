# Regenerate follow-up

Implemented the user's requested fresh-start action. **Regenerate (clear history)** is near the top of the controls panel. It uses the current valid controls, picks a fresh seed different from the prior/configured seed, displays it, releases owned notes normally, clears all events/branches/selection and pending playback/context actions, and immediately generates a new initial event. The active MIDI connection/channel remain selected. Named session files are untouched.

Invalid settings leave existing data/state intact. A later queued Stop/Panic cancels an unacknowledged Regenerate so it cannot restart playback after Stop. Generate retains its existing continuation behavior.

Validation:94/94 full-suite tests pass in regenerate-tests.txt; the native Windows button test passes in regenerate-native-gui.txt. New fixtures cover active-loop cleanup ordering, fresh seed and initial event, cleared branches/history/selection/context, invalid drafts and stale command cancellation. The UI test confirms the timeline resets and the fresh seed is visible.

An existing asynchronous export test briefly observed a newly created empty file before export completed. Its wait now uses the actual export-complete UI acknowledgment; the product export behavior was unchanged.

The Windows executable was rebuilt (regenerate-build.txt), launched/closed with exit0, and its native window inspected (regenerate-window.png). Current executable and source hashes are in build-manifest.json. Initial M1–M6 qualification evidence remains historical in the milestone reports; this follow-up adds the authorized destructive reset without changing normal immutable-history/branch workflows.
