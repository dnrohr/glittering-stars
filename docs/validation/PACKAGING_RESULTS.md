# Final Windows package qualification

This records the initial M1–M6 package qualification. The subsequent Regenerate feature has a rebuilt executable, current hashes in build-manifest.json, and94 passing tests; see REGENERATE_RESULTS.md.

Pass. Windows 11 build 26200; Python 3.12.10; PySide6 6.12.0; PyInstaller 6.22.3. Baseline57c3dc1 plus uncommitted implementation identified by build-manifest.json. No remote release was made.

Command: `powershell -NoProfile -File packaging/build_windows.ps1`. Actual output: build-final.txt. Artifact: `dist/packaged/GlitteringStars` (254 files,131617071 bytes), including RtMidi/mido backends, defaults, notices and six full dependency-license texts. Incompatible Git ICU DLLs are excluded; native Windows ICU resolved.

Executable SHA256: `c52829cf248863bb47ce9197533094718d9f622705a0e6b925f51f8987b5d9da`.

The orchestrator copied the final complete folder outside the repo to a fresh TEMP path with spaces. With PATH restricted to Windows system directories and isolated LOCALAPPDATA, `GlitteringStars.exe --preview --screenshot ... --close-after-ms 1400` exited0. See packaged-external.json and packaged-external-launch.png. Developer Python and `.venv` were not on PATH or required.

The final external executable was opened visibly and driven through native Windows controls. The recovery prompt was dismissed, and native Open restored a saved five-event session as Loop/Idle silently. Play entered Holding and Gap with countdown; history retained five events over repeated wraps. Escape stopped. Native Save wrote a second file; independent parsing proved exactly identical history and complete generator snapshot before/after those packaged loops. Screenshots: packaged-final-loop.png and packaged-workflow.png. The app was closed with no verification worker left running.

The preceding packaged workflow also used Generate to advance five to seven events, Stop, and native Save/Open dialogs. The rebuilt final version corrected a stale Loading status; its stronger regression changes history before load and checks restored state/cleared status. The final package showed the corrected Applied status after load.

workflow.json separately records one native source session covering12 events, live timing/velocity changes, selection4–7, loop/replacement, Pause/Next/Loop Off/Stop, Continue, edited child, audition, exact named save/open, and parsed two-pass MIDI export. All90 full-suite tests pass. Real MIDI receipt, user listening, DPI and10000-event stress have separate evidence.

Qualification is for this Windows machine/dependency set. The local build is unsigned. Sound requires separately installed Surge XT/loopMIDI; Preview works without them. MIDI stores notes/key markers rather than a synth patch or rendered audio. Future engine formats disable unsupported deterministic continuation. M7 remains optional/not implemented.

After the final selection-ordering repair, the binary was rebuilt and rerun outside the repository with system-only PATH and isolated data (packaged-external-final.json). The final MIDI run and90-test suite apply to these source hashes. Earlier packaged native file-dialog evidence remains under packaged-workflow.png; final loop evidence is packaged-final-loop.png.
