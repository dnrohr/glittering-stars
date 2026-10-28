"""Three-note MIDI chord walk for Surge XT. Settings live in settings.json."""
import argparse
import itertools
import json
import math
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
import mido

ROOT = Path(__file__).resolve().parent
C_MAJOR = {0, 2, 4, 5, 7, 9, 11}
KEY_NAMES = ('C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B')


def key_number(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Ga-g][#b]?', name):
        raise ValueError('starting_key must be a major tonic such as C, F#, or Bb')
    return note_number(name + '4') % 12


def note_number(value):
    """Scientific pitch notation: C2=36, C4=60 (MIDI middle C)."""
    if type(value) is int:
        number = value
    else:
        match = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d+)", str(value))
        if not match:
            raise ValueError(f"Invalid note {value!r}; use C2, F#3, Bb2, or an integer MIDI note")
        letter, accidental, octave = match.groups()
        number = 12 * (int(octave) + 1) + dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)[letter.upper()]
        number += {"": 0, "#": 1, "b": -1}[accidental]
    if not 0 <= number <= 127:
        raise ValueError("Pitch must be within MIDI 0..127")
    return number


def note_name(note, key=None):
    names = ('C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B') if key in (1, 3, 5, 8, 10) else ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
    return f"{names[note % 12]}{note // 12 - 1}"


@dataclass
class Settings:
    port: str = "Surge Generative"
    mode: str = "diatonic"
    low: str = "C2"
    high: str = "C4"
    hold: float = 3.0
    silence: float = 3.0
    chords: int = 0
    seed: int | None = None
    velocity: int = 55
    starting_key: str = 'C'
    fourth_modulation_probability: float = 0.15
    seventh_modulation_probability: float = 0.15
    diatonic_steps: list = field(default_factory=lambda: [0, 1, 2])
    diatonic_probabilities: list = field(default_factory=lambda: [0.1, 0.6, 0.3])
    chromatic_steps: list = field(default_factory=lambda: [1])
    chromatic_probabilities: list = field(default_factory=lambda: [1.0])

    def validate(self):
        key_number(self.starting_key)
        for name in ('fourth_modulation_probability', 'seventh_modulation_probability'):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f'{name} must be a finite probability from 0 to 1')
        if self.mode not in ("diatonic", "chromatic"):
            raise ValueError("mode must be diatonic or chromatic")
        if note_number(self.low) > note_number(self.high):
            raise ValueError("low must not exceed high")
        for name in ("hold", "silence"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (name == "hold" and value == 0):
                raise ValueError("hold must be positive; silence nonnegative; both finite")
        if type(self.chords) is not int or self.chords < 0:
            raise ValueError("chords must be a nonnegative integer (0 = continuous)")
        if type(self.velocity) is not int or not 1 <= self.velocity <= 127:
            raise ValueError("velocity must be an integer in 1..127")
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("seed must be an integer or null")
        for mode in ("diatonic", "chromatic"):
            steps = getattr(self, mode + "_steps")
            probabilities = getattr(self, mode + "_probabilities")
            if not steps or len(steps) != len(probabilities):
                raise ValueError(f"{mode}: provide one weight per step")
            if any(type(s) is not int or s < 0 for s in steps) or len(set(steps)) != len(steps):
                raise ValueError(f"{mode}: steps must be unique nonnegative integers")
            if any(not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0 for p in probabilities):
                raise ValueError(f"{mode}: weights must be finite and nonnegative")
            if not any(p > 0 for p in probabilities):
                raise ValueError(f"{mode}: at least one weight must be positive")


def valid_chord(chord):
    return len(set(chord)) == 3 and max(chord) - min(chord) > 6


class ChordWalk:
    def __init__(self, settings):
        settings.validate()
        self.settings = settings
        self.rng = random.Random(settings.seed)
        self.tonic = key_number(settings.starting_key)
        self.refresh_scale()
        initial = [c for c in itertools.combinations(self.pool, 3) if valid_chord(c)]
        if not initial:
            raise ValueError("Range contains no legal three-note chord spanning more than a tritone")
        self.chord = self.rng.choice(initial)

    @property
    def key(self):
        return KEY_NAMES[self.tonic]

    def refresh_scale(self):
        self.pool = [n for n in range(note_number(self.settings.low), note_number(self.settings.high) + 1)
                     if self.settings.mode == 'chromatic' or (n - self.tonic) % 12 in C_MAJOR]
        self.indices = {n: i for i, n in enumerate(self.pool)}

    def candidates(self, step):
        """Legal voice/direction pairs, keeping the sampled step size fixed."""
        result = []
        for voice, note in enumerate(self.chord):
            for direction in (-1, 1):
                # Retained out-of-key notes enter the current scale on their next
                # move: the nearest scale note in the chosen direction is step 1.
                targets = [n for n in self.pool if (n - note) * direction > 0]
                if direction < 0:
                    targets.reverse()
                if 0 < step <= len(targets):
                    chord = list(self.chord)
                    chord[voice] = targets[step - 1]
                    if valid_chord(chord):
                        result.append(tuple(sorted(chord)))
        return result

    def maybe_modulate(self, previous, chord):
        if self.settings.mode != 'diatonic':
            return chord, 'moved'
        landed = next(iter(set(chord) - set(previous)))
        degree = (landed - self.tonic) % 12
        if degree == 5:
            alteration, shift, probability = 1, 7, self.settings.fourth_modulation_probability
        elif degree == 11:
            alteration, shift, probability = -1, -7, self.settings.seventh_modulation_probability
        else:
            return chord, 'moved'
        if probability == 0 or self.rng.random() >= probability:
            return chord, 'moved'
        # A key change alters this pitch class in every octave of the chord.
        replacement = tuple(sorted(n + alteration if n % 12 == landed % 12 else n for n in chord))
        # A rejected modulation keeps the ordinary move and the original key.
        if (not all(note_number(self.settings.low) <= n <= note_number(self.settings.high) for n in replacement)
                or not valid_chord(replacement)
                or landed + alteration in set(previous) - set(chord)):
            return chord, 'moved; modulation blocked by chord/range constraints'
        old_key = self.key
        self.tonic = (self.tonic + shift) % 12
        self.refresh_scale()
        return replacement, f'modulated {old_key} -> {self.key} ({"fourth raised" if degree == 5 else "seventh lowered"})'

    def advance(self):
        cfg = self.settings
        weights = getattr(cfg, cfg.mode + "_probabilities")
        # Scaling preserves ratios and prevents overflow when adding large weights.
        scale = max(weights)
        step = self.rng.choices(getattr(cfg, cfg.mode + "_steps"),
                                weights=[w / scale for w in weights], k=1)[0]
        if step == 0:
            return self.chord, step, "repeat"
        candidates = self.candidates(step)
        if not candidates:
            return self.chord, step, "blocked: no legal move for this step; repeated"
        self.chord, status = self.maybe_modulate(self.chord, self.rng.choice(candidates))
        return self.chord, step, status


def chord_stream(walk):
    yield walk.chord, 0, "initial"
    index = 1
    while walk.settings.chords == 0 or index < walk.settings.chords:
        yield walk.advance()
        index += 1


def select_port(hint):
    names = mido.get_output_names()
    matches = [n for n in names if n == hint] or [n for n in names if hint.casefold() in n.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Expected one port matching {hint!r}; found {matches}. Available: {names}. "
                         "Start loopMIDI and create a port named 'Surge Generative'.")
    return matches[0]


def panic(port):
    for control in (64, 123, 120):
        port.send(mido.Message("control_change", control=control, value=0))


def wait_until(deadline):
    while (remaining := deadline - time.perf_counter()) > 0:
        time.sleep(min(remaining, 0.02))


def play(port, walk):
    cfg = walk.settings
    active = set()
    try:
        port.send(mido.Message("control_change", control=64, value=0))
        for index, (chord, step, status) in enumerate(chord_stream(walk), 1):
            print(f"{index:4}: {' '.join(note_name(n, walk.tonic) for n in chord):16} key={walk.key} major step={step} {status}", flush=True)
            for note in chord:
                active.add(note)
                port.send(mido.Message("note_on", note=note, velocity=cfg.velocity))
            wait_until(time.perf_counter() + cfg.hold)
            for note in chord:
                port.send(mido.Message("note_off", note=note))
                active.discard(note)
            # Full silence after actual note-off, even if the scheduler ran late.
            wait_until(time.perf_counter() + cfg.silence)
    finally:
        for note in active:
            port.send(mido.Message("note_off", note=note))
        port.send(mido.Message("control_change", control=64, value=0))
        # Preserve release/reverb tails: no All Sound Off during ordinary cleanup.


def save_midi(path, walk):
    cfg = walk.settings
    if cfg.chords == 0:
        raise ValueError("Use --chords with a positive count for MIDI export")
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=1000000))
    track.append(mido.Message("control_change", control=64, value=0))
    previous = 0
    last_key = None
    for index, (chord, _, status) in enumerate(chord_stream(walk)):
        onset = round(index * (cfg.hold + cfg.silence) * 480)
        if walk.key != last_key:
            track.append(mido.MetaMessage('key_signature', key=walk.key, time=onset - previous))
            previous = onset
            last_key = walk.key
            track.append(mido.MetaMessage('marker', text=f'{walk.key} major: {status}'))
        for second, kind in ((index * (cfg.hold + cfg.silence), "note_on"),
                             (index * (cfg.hold + cfg.silence) + cfg.hold, "note_off")):
            tick = round(second * 480)
            for note in chord:
                track.append(mido.Message(kind, note=note, velocity=cfg.velocity if kind == "note_on" else 0,
                                          time=tick - previous))
                previous = tick
    end = round(cfg.chords * (cfg.hold + cfg.silence) * 480)
    track.append(mido.MetaMessage("end_of_track", time=end - previous))
    midi.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "settings.json")
    parser.add_argument("--port")
    parser.add_argument("--mode", choices=("diatonic", "chromatic"))
    parser.add_argument("--low", help="Lowest pitch, e.g. C2")
    parser.add_argument("--high", help="Highest pitch, e.g. C4")
    parser.add_argument("--hold", type=float, help="Seconds holding each chord")
    parser.add_argument("--silence", type=float, help="Seconds after note-off")
    parser.add_argument("--chords", type=int, help="Number of chords; 0 = continuous")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--velocity", type=int)
    parser.add_argument('--starting-key', help='Starting major tonic, e.g. C, G, Bb')
    parser.add_argument('--fourth-modulation-probability', type=float)
    parser.add_argument('--seventh-modulation-probability', type=float)
    parser.add_argument("--steps", type=int, nargs="+", help="Override step sizes for selected mode")
    parser.add_argument("--probabilities", type=float, nargs="+", help="Relative weights; need not sum to 1")
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument("--panic", action="store_true")
    parser.add_argument("--preview", action="store_true", help="Print only; requires --chords > 0")
    parser.add_argument("--save", type=Path)
    args = parser.parse_args()
    try:
        values = json.loads(args.config.read_text(encoding="utf-8"))
        for key in Settings.__dataclass_fields__:
            value = getattr(args, key, None)
            if value is not None:
                values[key] = value
        cfg = Settings(**values)
        if args.list_ports:
            print("\n".join(mido.get_output_names()) or "No MIDI outputs found.")
            return
        if args.panic:
            with mido.open_output(select_port(cfg.port)) as port:
                panic(port)
            print("Notes stopped.")
            return
        if args.steps is not None:
            setattr(cfg, cfg.mode + "_steps", args.steps)
        if args.probabilities is not None:
            setattr(cfg, cfg.mode + "_probabilities", args.probabilities)
        walk = ChordWalk(cfg)
        if args.preview:
            if cfg.chords == 0:
                raise ValueError("Use --chords with a positive count for preview")
            for chord, step, status in chord_stream(walk):
                print(' '.join(note_name(n, walk.tonic) for n in chord), f"key={walk.key} major step={step} {status}")
        elif args.save:
            save_midi(args.save, walk)
            print(f"Saved {args.save}")
        else:
            with mido.open_output(select_port(cfg.port)) as port:
                print(f"{cfg.mode}: {cfg.low}..{cfg.high}; hold {cfg.hold:g}s, silence {cfg.silence:g}s. Ctrl+C to stop.")
                play(port, walk)
    except KeyboardInterrupt:
        print("\nStopped; notes released.")
    except (ValueError, TypeError, OSError, RuntimeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
