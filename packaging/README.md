# Windows build

Tested on Windows11 build26200, Python3.12.10, PySide6 6.12.0 and PyInstaller6.22.3. Install requirements.txt and requirements-desktop.txt in `.venv`, then from the repository run:

```powershell
powershell -NoProfile -File packaging/build_windows.ps1
```

The application is `dist/packaged/GlitteringStars/GlitteringStars.exe`. Keep the whole folder, including `_internal`, together. No developer Python environment is needed to run the package. Surge XT and loopMIDI remain separately installed prerequisites for sound; Preview and session inspection work without them. No installers for those programs are redistributed.

The spec collects dynamic mido/RtMidi backends, bundled default settings, notices and full license texts. It excludes the incompatible Git ICU DLL that PyInstaller can discover through PATH; Qt uses the Windows ICU. Build output and source/executable hashes are under docs/validation. The final external launch check removes developer Python from PATH and runs a copy from a folder with spaces.

Runtime sessions/autosave/settings belong in LOCALAPPDATA/GlitteringStars. Launch never rewrites the repository settings.json or the bundled defaults. Session open disconnects the current MIDI handle and remains silent; reconnect explicitly to the selected output/channel.

Native Qt interaction, real MIDI receipt, listening, large-history performance and packaging are separate evidence categories. See docs/validation/ACCEPTANCE.md and MILESTONE_6_RESULTS.md for qualification and measured limits. Optional M7 audio capture/Surprise is not part of this build.

This local development build is unsigned. Remote releases and publishing have not been performed. Retain THIRD_PARTY_NOTICES.txt and the full bundled licenses when copying the application folder.
