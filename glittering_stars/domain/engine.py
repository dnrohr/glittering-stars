"""Deterministic, device-independent three-voice harmony engine.

Snapshot schema 1 is a JSON object containing the full frozen configuration,
voice IDs and pitches, current/start key, effective seed, Python Random state,
transition counter, cooldown, and configuration revision. RNG state is an
integer tree validated against random.Random's current state shape; it is never
unpickled. Reproducibility is promised within this engine/Python RNG format.
"""
from __future__ import annotations

import itertools
import json
import math
import random
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable

ENGINE_VERSION = 1
KEY_NAMES = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
_LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_MAJOR = frozenset((0, 2, 4, 5, 7, 9, 11))
_POLICIES = {"off", "moving_note", "whole_chord", "pivot"}


def note_number(value: int | str) -> int:
    """Convert MIDI number or scientific pitch name (C4 is 60)."""
    if type(value) is int:
        number = value
    else:
        match = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d+)", str(value))
        if not match:
            raise ValueError(f"Invalid pitch {value!r}; use C3, F#4, Bb2, or MIDI 0..127")
        letter, accidental, octave = match.groups()
        number = 12 * (int(octave) + 1) + _LETTERS[letter.upper()] + {"": 0, "#": 1, "b": -1}[accidental]
    if not 0 <= number <= 127:
        raise ValueError("Pitch must be within MIDI 0..127")
    return number


def key_number(name: str | int) -> int:
    if type(name) is int and 0 <= name <= 11:
        return name
    if not isinstance(name, str) or not re.fullmatch(r"[A-Ga-g][#b]?", name):
        raise ValueError("Key must be a major tonic such as C, F#, or Bb")
    return note_number(name + "4") % 12


def note_name(note: int, key: str | int | None = None) -> str:
    tonic = key_number(key) if key is not None else None
    flat = tonic in (1, 3, 5, 8, 10) if tonic is not None else False
    names = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B") if flat else (
        "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    return f"{names[note % 12]}{note // 12 - 1}"


def _tuple_ints(values, name: str) -> tuple[int, ...]:
    if not isinstance(values, (tuple, list)) or any(type(x) is not int for x in values):
        raise ValueError(f"{name} must be a sequence of integers")
    return tuple(values)


@dataclass(frozen=True)
class Config:
    # Legacy CLI configuration fields
    port: str = "Surge Generative"
    mode: str = "diatonic"
    low: str | int = "C2"
    high: str | int = "C4"
    hold: float = 3.0
    silence: float = 3.0
    chords: int = 0
    seed: int | None = None
    velocity: int = 55
    starting_key: str | int = "C"
    fourth_modulation_probability: float = 0.15
    seventh_modulation_probability: float = 0.15
    diatonic_steps: tuple[int, ...] = (0, 1, 2)
    diatonic_probabilities: tuple[float, ...] = (0.1, 0.6, 0.3)
    chromatic_steps: tuple[int, ...] = (1,)
    chromatic_probabilities: tuple[float, ...] = (1.0,)
    # Desktop and harmonic policy fields
    channel: int = 0
    policy: str = "moving_note"
    locks: tuple[int, ...] = ()
    allowed_keys: tuple[int, ...] = ()  # empty means unrestricted
    max_fifths: int | None = None
    cooldown_events: int = 0
    min_span: int = 7
    max_span: int | None = None
    min_gap: int = 1
    octave_doubling: bool = True
    upward_probability: float = 0.5

    def __post_init__(self):
        for name in ("diatonic_steps", "diatonic_probabilities", "chromatic_steps",
                     "chromatic_probabilities", "locks", "allowed_keys"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        self.validate()

    def validate(self):
        if self.mode not in ("diatonic", "chromatic"):
            raise ValueError("mode must be diatonic or chromatic")
        if note_number(self.low) > note_number(self.high):
            raise ValueError("low must not exceed high")
        key_number(self.starting_key)
        if not isinstance(self.port, str) or not self.port.strip():
            raise ValueError("port must be a nonempty string")
        for name in ("hold", "silence"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (name == "hold" and value == 0):
                raise ValueError("hold must be positive; silence nonnegative; both finite")
        if type(self.chords) is not int or self.chords < 0:
            raise ValueError("chords must be a nonnegative integer")
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("seed must be an integer or null")
        if type(self.velocity) is not int or not 1 <= self.velocity <= 127:
            raise ValueError("velocity must be an integer in 1..127")
        if type(self.channel) is not int or not 0 <= self.channel <= 15:
            raise ValueError("channel must be in 0..15")
        if self.policy not in _POLICIES:
            raise ValueError(f"policy must be one of {sorted(_POLICIES)}")
        if any(type(i) is not int or i not in (0, 1, 2) for i in self.locks) or len(set(self.locks)) != len(self.locks):
            raise ValueError("locks must contain distinct voice IDs 0, 1, or 2")
        if any(type(k) is not int or not 0 <= k <= 11 for k in self.allowed_keys) or len(set(self.allowed_keys)) != len(self.allowed_keys):
            raise ValueError("allowed_keys must contain distinct tonic integers 0..11")
        if self.allowed_keys and (key_number(self.starting_key) not in self.allowed_keys):
            raise ValueError("allowed destination keys must include the starting key")
        if self.max_fifths is not None and (type(self.max_fifths) is not int or not 0 <= self.max_fifths <= 6):
            raise ValueError("max_fifths must be 0..6 or null")
        if type(self.cooldown_events) is not int or self.cooldown_events < 0:
            raise ValueError("cooldown_events must be a nonnegative integer")
        if type(self.min_span) is not int or self.min_span < 7:
            raise ValueError("min_span has a hard floor of 7 semitones")
        if self.max_span is not None and (type(self.max_span) is not int or self.max_span < self.min_span):
            raise ValueError("max_span must be null or at least min_span")
        if type(self.min_gap) is not int or self.min_gap < 1:
            raise ValueError("min_gap must be an integer of at least one semitone")
        if type(self.octave_doubling) is not bool:
            raise ValueError("octave_doubling must be boolean")
        for name in ("fourth_modulation_probability", "seventh_modulation_probability", "upward_probability"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite probability from 0 to 1")
        for mode in ("diatonic", "chromatic"):
            steps = getattr(self, mode + "_steps")
            weights = getattr(self, mode + "_probabilities")
            if not steps or len(steps) != len(weights) or any(type(s) is not int or s < 0 for s in steps) or len(set(steps)) != len(steps):
                raise ValueError(f"{mode}: steps must be distinct nonnegative integers with one weight each")
            if any(not isinstance(w, (int, float)) or not math.isfinite(w) or w < 0 for w in weights) or not any(w > 0 for w in weights):
                raise ValueError(f"{mode}: weights must be finite, nonnegative and have a positive value")
        return self

    @classmethod
    def from_dict(cls, values: dict) -> "Config":
        if not isinstance(values, dict):
            raise ValueError("configuration must be a JSON object")
        known = set(cls.__dataclass_fields__)
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"unknown configuration fields: {sorted(unknown)}")
        return cls(**values)

    def to_dict(self) -> dict:
        values = asdict(self)
        for name in ("diatonic_steps", "diatonic_probabilities", "chromatic_steps",
                     "chromatic_probabilities", "locks", "allowed_keys"):
            values[name] = list(values[name])
        return values


@dataclass(frozen=True, order=True)
class Voice:
    id: int
    pitch: int

    def __post_init__(self):
        if type(self.id) is not int or self.id not in (0, 1, 2):
            raise ValueError("voice ID must be 0, 1, or 2")
        if type(self.pitch) is not int:
            raise ValueError("voice pitch must be an integer MIDI note")
        note_number(self.pitch)


def _voices(value: Iterable[Voice | dict | tuple]) -> tuple[Voice, ...]:
    try:
        result = tuple(v if isinstance(v, Voice) else Voice(**v) if isinstance(v, dict) else Voice(*v) for v in value)
    except (TypeError, KeyError) as exc:
        raise ValueError("voices must contain id/pitch pairs") from exc
    if len(result) != 3 or {v.id for v in result} != {0, 1, 2}:
        raise ValueError("exactly voices with IDs 0, 1, and 2 are required")
    if len({v.pitch for v in result}) != 3:
        raise ValueError("voice pitches must be distinct")
    return tuple(sorted(result, key=lambda v: v.id))


def validate_chord(voices: Iterable[Voice | dict | tuple], config: Config) -> tuple[Voice, ...]:
    result = _voices(voices)
    pitches = sorted(v.pitch for v in result)
    low, high = note_number(config.low), note_number(config.high)
    if any(not low <= p <= high for p in pitches):
        raise ValueError("chord pitch is outside the inclusive configured range")
    if pitches[-1] - pitches[0] < config.min_span or (config.max_span is not None and pitches[-1] - pitches[0] > config.max_span):
        raise ValueError("chord violates span constraints")
    if any(b - a < config.min_gap for a, b in zip(pitches, pitches[1:])):
        raise ValueError("neighboring pitches violate minimum gap")
    if not config.octave_doubling and any((b - a) % 12 == 0 for a, b in itertools.combinations(pitches, 2)):
        raise ValueError("octave doubling is disabled")
    return result


class Engine:
    """Mutable transition state; one instance belongs to the authoritative worker."""
    def __init__(self, config: Config, seed: int | None = None):
        self.config = config.validate()
        self.start_key = key_number(config.starting_key)
        self.key = self.start_key
        self.effective_seed = config.seed if seed is None else seed
        if self.effective_seed is None:
            self.effective_seed = random.SystemRandom().randrange(0, 2**63)
        if type(self.effective_seed) is not int:
            raise ValueError("effective seed must be an integer")
        self._rng = random.Random(self.effective_seed)
        self.counter = 0
        self.cooldown = 0
        self.revision = 0
        initial = self._initial_chords()
        if not initial:
            raise ValueError("range and constraints contain no legal three-note chord")
        pitches = self._rng.choice(initial)
        self.voices = tuple(Voice(i, p) for i, p in enumerate(pitches))

    @staticmethod
    def _in_key(note: int, tonic: int) -> bool:
        return (note - tonic) % 12 in _MAJOR

    @staticmethod
    def _fifths_distance(first: int, second: int) -> int:
        a, b = (first * 7) % 12, (second * 7) % 12
        delta = abs(a - b)
        return min(delta, 12 - delta)

    def _key_allowed(self, tonic: int) -> bool:
        return (not self.config.allowed_keys or tonic in self.config.allowed_keys) and (
            self.config.max_fifths is None or self._fifths_distance(self.start_key, tonic) <= self.config.max_fifths)

    def _initial_chords(self):
        cfg = self.config
        notes = range(note_number(cfg.low), note_number(cfg.high) + 1)
        if cfg.mode == "diatonic":
            notes = (n for n in notes if self._in_key(n, self.key))
        # combinations already guarantees sorted, distinct, in-range pitches.
        # Avoid constructing a Voice/Config validation graph for every one of
        # 341,376 full-MIDI-range candidates while a transport command is waiting.
        return [c for c in itertools.combinations(notes, 3)
                if c[2] - c[0] >= cfg.min_span
                and (cfg.max_span is None or c[2] - c[0] <= cfg.max_span)
                and c[1] - c[0] >= cfg.min_gap and c[2] - c[1] >= cfg.min_gap
                and (cfg.octave_doubling or len({n % 12 for n in c}) == 3)]

    def initial(self) -> dict:
        return {"status": "initial", "step": 0, "voice_id": None, "direction": None,
                "ordinary_destination": None, "modulation_attempt": False, "modulated": False,
                "reason": "initial chord", "key_before": self.key, "key_after": self.key,
                "affected_voice_ids": [], "voices": self._voice_dicts(), "counter": self.counter,
                "cooldown": self.cooldown, "revision": self.revision}

    def _voice_dicts(self):
        return [{"id": v.id, "pitch": v.pitch} for v in self.voices]

    def _targets(self, pitch: int, direction: int) -> list[int]:
        lo, hi = note_number(self.config.low), note_number(self.config.high)
        candidates = [n for n in range(lo, hi + 1) if (n - pitch) * direction > 0]
        if self.config.mode == "chromatic":
            return candidates if direction > 0 else list(reversed(candidates))
        candidates = [n for n in candidates if self._in_key(n, self.key)]
        return candidates if direction > 0 else list(reversed(candidates))

    def _candidate_pairs(self, step: int):
        pairs = []
        for voice in self.voices:
            if voice.id in self.config.locks:
                continue
            for direction in (-1, 1):
                weight = (1 - self.config.upward_probability) if direction < 0 else self.config.upward_probability
                if weight <= 0:
                    continue
                targets = self._targets(voice.pitch, direction)
                if step <= len(targets):
                    target = targets[step - 1]
                    candidate = tuple(Voice(v.id, target if v.id == voice.id else v.pitch) for v in self.voices)
                    if not _chord_error(candidate, self.config):
                        pairs.append((voice.id, direction, target, candidate, weight))
        return pairs

    def _destination_allowed(self, destination: int) -> bool:
        return self._key_allowed(destination)

    def _try_modulation(self, old: tuple[Voice, ...], candidate: tuple[Voice, ...], moved_id: int,
                        cooldown_at_start: int) -> tuple[tuple[Voice, ...], bool, bool, str, list[int]]:
        cfg = self.config
        if cfg.mode == "chromatic" or cfg.policy == "off":
            return candidate, False, False, "automatic modulation disabled", []
        if cooldown_at_start > 0:
            return candidate, False, False, "modulation suppressed by cooldown", []
        before = {v.id: v.pitch for v in old}
        after = {v.id: v.pitch for v in candidate}
        if cfg.policy in ("moving_note", "whole_chord"):
            landed = after[moved_id]
            if before[moved_id] == landed:
                return candidate, False, False, "trigger voice unchanged", []
            degree = (landed - self.key) % 12
            if degree == 5:
                alteration, shift, chance = 1, 7, cfg.fourth_modulation_probability
            elif degree == 11:
                alteration, shift, chance = -1, -7, cfg.seventh_modulation_probability
            else:
                return candidate, False, False, "no fourth/seventh landing trigger", []
            if chance <= 0 or self._rng.random() >= chance:
                return candidate, True, False, "modulation probability failed", []
            destination = (self.key + shift) % 12
            if not self._destination_allowed(destination):
                return candidate, True, False, "destination key is outside exploration limits", []
            try:
                altered = tuple(Voice(v.id, v.pitch + alteration if v.pitch % 12 == landed % 12 else v.pitch)
                                for v in candidate)
            except ValueError:
                return candidate, True, False, "modulation blocked: altered pitch is outside MIDI range", []
            affected = [v.id for v in altered if v.pitch != after[v.id]]
            reason = _chord_error(altered, cfg)
            if reason:
                return candidate, True, False, f"modulation blocked: {reason}", []
            if any(i in cfg.locks for i in affected):
                return candidate, True, False, "modulation blocked: locked voice would change", []
            if cfg.policy == "whole_chord" and not all(self._in_key(v.pitch, destination) for v in altered):
                return candidate, True, False, "modulation blocked: altered chord does not fit destination key", []
            if altered_by_id(altered)[moved_id] == before[moved_id]:
                return candidate, True, False, "modulation blocked: trigger voice returns to its previous pitch", []
            self.key = destination
            self.cooldown = cfg.cooldown_events
            return altered, True, True, f"modulated to {KEY_NAMES[destination]}", affected

        # Pivot: evaluate both adjacent fifths, choose uniformly among eligible
        # directions, then perform one chance roll. Never fall back after failure.
        eligible = []
        for shift, chance in ((7, cfg.fourth_modulation_probability), (-7, cfg.seventh_modulation_probability)):
            destination = (self.key + shift) % 12
            if chance > 0 and self._destination_allowed(destination) and all(
                    self._in_key(v.pitch, self.key) and self._in_key(v.pitch, destination) for v in candidate):
                eligible.append((destination, chance))
        if not eligible:
            return candidate, False, False, "no admissible pivot destination", []
        destination, chance = self._rng.choice(eligible)
        if self._rng.random() >= chance:
            return candidate, True, False, "pivot probability failed", []
        self.key = destination
        self.cooldown = cfg.cooldown_events
        return candidate, True, True, f"pivoted to {KEY_NAMES[destination]} without altering pitches", []

    def advance(self) -> dict:
        cfg = self.config
        steps = getattr(cfg, cfg.mode + "_steps")
        weights = getattr(cfg, cfg.mode + "_probabilities")
        weight_scale = max(weights)
        step = self._rng.choices(steps, weights=[w / weight_scale for w in weights], k=1)[0]
        before_key = self.key
        before = self.voices
        cooldown_at_start = self.cooldown
        self.counter += 1
        if step == 0:
            self.cooldown = max(0, self.cooldown - 1)
            return self._decision("repeat", step, before_key, "requested zero-step repeat")
        candidates = self._candidate_pairs(step)
        if not candidates:
            self.cooldown = max(0, self.cooldown - 1)
            return self._decision("blocked", step, before_key, "no legal voice/direction candidate for sampled step")
        chosen = self._rng.choices(candidates, weights=[x[4] for x in candidates], k=1)[0]
        voice_id, direction, target, candidate, _ = chosen
        self.voices = candidate
        adjusted, attempted, modulated, reason, affected = self._try_modulation(before, candidate, voice_id, cooldown_at_start)
        self.voices = adjusted
        if cooldown_at_start > 0:
            self.cooldown = cooldown_at_start - 1
        changed_ids = affected if modulated else [voice_id]
        return {"status": "modulated" if modulated else "moved", "step": step, "voice_id": voice_id,
                "direction": "up" if direction > 0 else "down", "ordinary_destination": target,
                "modulation_attempt": attempted, "modulated": modulated, "reason": reason,
                "key_before": before_key, "key_after": self.key, "affected_voice_ids": changed_ids,
                "voices": self._voice_dicts(), "counter": self.counter, "cooldown": self.cooldown,
                "revision": self.revision}

    def _decision(self, status, step, before_key, reason):
        return {"status": status, "step": step, "voice_id": None, "direction": None,
                "ordinary_destination": None, "modulation_attempt": False, "modulated": False,
                "reason": reason, "key_before": before_key, "key_after": self.key,
                "affected_voice_ids": [], "voices": self._voice_dicts(), "counter": self.counter,
                "cooldown": self.cooldown, "revision": self.revision}

    def apply_config(self, config: Config, revision: int):
        if type(revision) is not int or revision <= self.revision:
            raise ValueError("configuration revision must increase")
        config.validate()
        if not (note_number(config.low) <= min(v.pitch for v in self.voices) and
                max(v.pitch for v in self.voices) <= note_number(config.high)):
            raise ValueError("new range excludes a current voice; start a new phrase explicitly")
        if _chord_error(self.voices, config):
            raise ValueError(_chord_error(self.voices, config))
        if config.allowed_keys and (self.key not in config.allowed_keys or self.start_key not in config.allowed_keys):
            raise ValueError("allowed keys must include current and starting key")
        if config.max_fifths is not None and self._fifths_distance(self.start_key, self.key) > config.max_fifths:
            raise ValueError("fifths limit excludes the current key")
        old = (self.config, self.revision)
        self.config, self.revision = config, revision
        try:
            validate_chord(self.voices, self.config)
        except ValueError:
            self.config, self.revision = old
            raise

    def set_voices(self, voices: Iterable[Voice | dict | tuple]):
        """Atomically replace musical state while retaining random progress."""
        replacement = validate_chord(voices, self.config)
        self.voices = replacement

    def reseed(self, seed: int):
        if type(seed) is not int:
            raise ValueError("seed must be an integer")
        self.effective_seed = seed
        self._rng = random.Random(seed)
        self.revision += 1

    def set_key(self, tonic: int):
        tonic = key_number(tonic)
        if not self._key_allowed(tonic):
            raise ValueError("key is outside exploration limits")
        before = self.key
        self.key = tonic
        self.cooldown = 0
        self.revision += 1
        return {"status": "key_changed", "key_before": before, "key_after": tonic,
                "reason": f"manual key context set to {KEY_NAMES[tonic]}"}

    def snapshot(self) -> dict:
        return {"schema_version": ENGINE_VERSION, "config": self.config.to_dict(),
                "voices": self._voice_dicts(), "key": self.key, "start_key": self.start_key,
                "effective_seed": self.effective_seed, "rng_state": _state_to_json(self._rng.getstate()),
                "counter": self.counter, "cooldown": self.cooldown, "revision": self.revision}

    @classmethod
    def restore(cls, snapshot: dict) -> "Engine":
        required = {"schema_version", "config", "voices", "key", "start_key", "effective_seed",
                    "rng_state", "counter", "cooldown", "revision"}
        if not isinstance(snapshot, dict) or set(snapshot) != required or snapshot.get("schema_version") != ENGINE_VERSION:
            raise ValueError("unsupported or malformed engine snapshot")
        for field_name in ("key", "start_key"):
            if type(snapshot[field_name]) is not int or not 0 <= snapshot[field_name] <= 11:
                raise ValueError(f"invalid snapshot {field_name}")
        for field_name in ("counter", "cooldown", "revision"):
            if type(snapshot[field_name]) is not int or snapshot[field_name] < 0:
                raise ValueError(f"invalid snapshot {field_name}")
        if type(snapshot["effective_seed"]) is not int:
            raise ValueError("invalid snapshot effective_seed")
        config = Config.from_dict(snapshot["config"])
        voices = validate_chord(snapshot["voices"], config)
        if config.allowed_keys and (snapshot["start_key"] not in config.allowed_keys or snapshot["key"] not in config.allowed_keys):
            raise ValueError("snapshot key violates allowed keys")
        if config.max_fifths is not None and cls._fifths_distance(snapshot["start_key"], snapshot["key"]) > config.max_fifths:
            raise ValueError("snapshot key violates fifths limit")
        rng_state = _state_from_json(snapshot["rng_state"])
        obj = cls.__new__(cls)
        obj.config = config
        obj.voices = voices
        obj.key = snapshot["key"]
        obj.start_key = snapshot["start_key"]
        obj.effective_seed = snapshot["effective_seed"]
        obj.counter, obj.cooldown, obj.revision = snapshot["counter"], snapshot["cooldown"], snapshot["revision"]
        obj._rng = random.Random()
        try:
            obj._rng.setstate(rng_state)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid PRNG state") from exc
        return obj


def _chord_error(voices, config):
    try:
        validate_chord(voices, config)
    except ValueError as exc:
        return str(exc)
    return ""


def altered_by_id(voices):
    return {v.id: v.pitch for v in voices}


def _state_to_json(state):
    if not (isinstance(state, tuple) and len(state) == 3 and type(state[0]) is int and isinstance(state[1], tuple)
            and all(type(n) is int for n in state[1]) and (state[2] is None or isinstance(state[2], float))):
        raise ValueError("unexpected random state shape")
    return [state[0], list(state[1]), state[2]]


def _state_from_json(data):
    if not isinstance(data, list) or len(data) != 3 or type(data[0]) is not int or not isinstance(data[1], list):
        raise ValueError("invalid PRNG state shape")
    if any(type(n) is not int or not 0 <= n < 2**32 for n in data[1]):
        raise ValueError("invalid PRNG state words")
    if data[2] is not None and (not isinstance(data[2], (int, float)) or not math.isfinite(data[2])):
        raise ValueError("invalid PRNG Gaussian cache")
    state = (data[0], tuple(data[1]), data[2])
    probe = random.Random()
    try:
        probe.setstate(state)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid PRNG state") from exc
    return state
