# glittering-stars

Generative three-note MIDI chord walks for Surge XT.

## Desktop application

The native Windows desktop adds live controls, a selectable chord timeline, exact selection looping, composition branches, sessions and modulation policies. Install desktop dependencies and launch it separately from the CLI:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-desktop.txt
.\.venv\Scripts\python.exe desktop.py
```

Or double-click **Desktop.cmd**. Connect the MIDI output explicitly, or use Preview without a synth. Select a contiguous passage, choose Loop Selection (Ctrl+L), and Play to hear its stored notes and full gaps. Stop preserves synth tails; Panic silences immediately. Existing settings.json is read without rewriting it.

Use **Regenerate (clear history)** to reseed and start fresh. It clears the old timeline, branches and selection, preserves your current controls/connection, and starts a new sequence. **Generate** continues the existing history.

See the [desktop guide](docs/user-guide.md), [session format](docs/session-format.md), [architecture](docs/architecture.md), and [acceptance evidence](docs/validation/ACCEPTANCE.md). Contract documents:

- [Application specification](SPECIFICATION.md)
- [Roadmap and milestone index](ROADMAP.md)
- [Fresh orchestrator implementation task](ORCHESTRATOR_HANDOFF.md)

Actual pass/fail/unverified results are under docs/validation. Optional M7 audio-tail capture and Surprise remain outside this build.

Run all CLI, domain, controller, session and Qt checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

Build with `powershell -File packaging/build_windows.ps1`; distribute the entire generated application folder, including `_internal` and dependency licenses. The packaged app does not need the repo `.venv`. See [packaging instructions](packaging/README.md).

## Install from this repository

On Windows, install Python 3.12 or newer, Surge XT, and loopMIDI. Create a loopMIDI port named **Surge Generative** and enable it in Surge's MIDI settings. In PowerShell, from this repository folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Then double-click **Play.cmd**. The launchers use the standard Windows install paths for Surge and loopMIDI. The local `.venv` has already been rebuilt for this folder. To run the checks:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_generate
```


Double-click **Play.cmd**. It opens loopMIDI and Surge if needed and plays continuously until **Ctrl+C**. Keep Surge in **Poly** mode and loopMIDI running. MIDI input: **Surge Generative**, channel 1.

## Settings

Edit **settings.json** before starting:

| Setting | Default | Meaning |
|---|---|---|
| mode | diatonic | Current major-key scale steps; chromatic uses semitones |
| low / high | C2 / C4 | Inclusive bounds; C2=36, C4=60 (scientific notation) |
| hold | 3 | Seconds holding all three notes |
| silence | 3 | Seconds after note-off before the next chord |
| chords | 0 | Continuous; positive values give a finite count |
| seed | null | Fresh randomness; use an integer for repeatability |
| velocity | 55 | MIDI velocity for all notes |
| starting_key | C | Starting major tonic, such as C, G, F#, Bb |
| fourth_modulation_probability | 0.15 | Chance to raise an eligible fourth and move to the dominant key |
| seventh_modulation_probability | 0.15 | Chance to lower an eligible seventh and move to the subdominant key |
| diatonic_steps | [0,1,2] | Step sizes in the C-major scale |
| diatonic_probabilities | [0.1,0.6,0.3] | Corresponding step probabilities |
| chromatic_steps | [1] | Step sizes in semitones |
| chromatic_probabilities | [1.0] | Corresponding step probabilities |

The probability fields accept **relative weights**; they do not need to sum to 1. For example, `[1,6,3]`, `[10,60,30]`, and `[0.1,0.6,0.3]` all give 10% / 60% / 30%. Weights must be finite and nonnegative, with at least one positive value. A zero weight disables that step. For 0..N, list every step and its weight explicitly. There is no extra change-probability gate: step 0 repeats the chord.

The initial chord is sampled uniformly from legal combinations in the starting major key. Chromatic mode uses all semitones. Each transition samples a step first, then chooses uniformly among legal combinations of one voice and one direction (up/down). Ordinary moves leave the other two notes unchanged; modulation also alters octave doublings of its triggering pitch class. Constraints can restrict which voices and directions are available.

## Adjacent-key modulation

In diatonic mode, only the newly moving note can trigger modulation:

- Landing on the current key's fourth: a successful roll raises it by a semitone and moves the key up a fifth. In C, F becomes F# and the key becomes G.
- Landing on the current key's seventh: a successful roll lowers it by a semitone and moves the key down a fifth. In C, B becomes Bb and the key becomes F.

Each direction defaults to 15% per eligible landing. These two modulation settings are independent probabilities from 0 to 1, unlike the relative step weights. Set both to 0 to stay in one key, or 1 to attempt every eligible modulation. There is no cooldown. Chromatic mode does not modulate. Step-zero repeats, initial chords, blocked moves, and unchanged fourths/sevenths never trigger a roll.

On successful modulation, **every occurrence of the triggering pitch class changes together**, across octaves. For example, landing on F4 while F3 is held changes both to F#4 and F#3 when moving to G; landing on B4 while B3 is held changes both to Bb4 and Bb3 when moving to F. This is an exception to the ordinary one-note movement rule. The probability is rolled once for the whole modulation, not once per octave. Other pitch classes remain unchanged.

If any altered octave would leave the range, create a unison, shrink the span to six semitones or less, or undo the original moving note's change, the whole modulation is rejected: the ordinary diatonic move plays and the current key stays the same. No partial octave alteration is applied.

The current key persists and determines subsequent scale steps and fourth/seventh triggers. An unchanged pitch may temporarily lie outside the new key. When that pitch moves, step 1 means the nearest note of the current scale in the chosen direction; larger steps continue along that scale. Automatic changes to other voices during modulation are limited to the triggering pitch class.

Playback and preview show the current key and announce every modulation, such as `modulated C -> F (seventh lowered)`. MIDI exports include key-signature changes and markers. Pitch display uses common sharp/flat spellings, rather than full theoretical enharmonic spelling.

Unisons (identical pitches) are prohibited; octave doublings are allowed. Highest minus lowest pitch must be **greater than six semitones**, so all three cannot fit within a flat fifth. These constraints and the inclusive pitch bounds apply throughout. If a sampled step has no legal move, the player repeats and prints a blocked-move notice. It does not redraw the step and alter the requested sampling probabilities. Extreme custom ranges or steps can therefore cause extra repeats.

Three note-ons are sent together, then three note-offs after the hold. MIDI sends them sequentially as closely as possible. There are no additional melody notes. The silence starts after actual note-off and includes release and reverb decay. Increase it if the preset's tail remains audible; this is an adjustable wait, not automatic audio-silence detection. Normal completion and Ctrl+C release notes while allowing tails to decay. **Stop Notes.cmd** is the emergency silence command.

## Command-line overrides

Open PowerShell in this folder:

```powershell
# Chromatic: one semitone, random legal up/down movement
.\.venv\Scripts\python.exe .\generate.py --mode chromatic

# Start in F, with different modulation probabilities for each direction
.\.venv\Scripts\python.exe .\generate.py --starting-key F --fourth-modulation-probability 0.2 --seventh-modulation-probability 0.1

# Wider range, longer reverb wait
.\.venv\Scripts\python.exe .\generate.py --low C1 --high C5 --hold 3 --silence 10

# Override steps and probabilities for the selected mode
.\.venv\Scripts\python.exe .\generate.py --steps 0 1 2 3 --probabilities 0.1 0.5 0.3 0.1

# Print a reproducible walk without playing
.\.venv\Scripts\python.exe .\generate.py --preview --chords 20 --seed 7

# Export finite MIDI, including the final silence
.\.venv\Scripts\python.exe .\generate.py --chords 16 --seed 7 --save .\MySequence.mid

# List ports or silence notes
.\.venv\Scripts\python.exe .\generate.py --list-ports
.\.venv\Scripts\python.exe .\generate.py --panic
```

`Example.mid` is a finite example with seed 42. `generate.py` is the editable source. Avoid overlapping players because they share a channel. Settings changes take effect next run. Stop, change mode, and restart to switch modes; each run chooses a new initial chord. Your settings.json values for pitch range, timing, and step weights are preserved when new features are added; the table lists original defaults.

If routing needs restoring: Surge Settings → Active MIDI inputs → check **Surge Generative**. Its port must exist in loopMIDI. Keep this folder at its current location because `.venv` contains absolute paths. To rebuild after moving: `python -m venv .venv`, then `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
