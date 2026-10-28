import collections
import contextlib
import io
import itertools
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mido
import generate as g


class ChordTests(unittest.TestCase):
    def test_modulation_changes_all_octaves_of_trigger_pitch(self):
        cfg = g.Settings(low='C2', high='C5', fourth_modulation_probability=1, seventh_modulation_probability=1)
        for previous, candidate, expected, key in (
                ((48, 53, 64), (48, 53, 65), (48, 54, 66), 'G'),
                ((48, 59, 69), (48, 59, 71), (48, 58, 70), 'F'),
                ((41, 53, 64), (41, 53, 65), (42, 54, 66), 'G')):
            walk = g.ChordWalk(cfg)
            chord, status = walk.maybe_modulate(previous, candidate)
            self.assertEqual(chord, expected)
            self.assertEqual(walk.key, key)
            self.assertTrue(status.startswith('modulated'))
        # The landed F is in range, but the other F would exceed the ceiling.
        walk = g.ChordWalk(g.Settings(high='F4', fourth_modulation_probability=1))
        chord, status = walk.maybe_modulate((43, 48, 65), (41, 48, 65))
        self.assertEqual(chord, (41, 48, 65))
        self.assertEqual(walk.key, 'C')
        self.assertIn('blocked', status)

    def test_modulation_directions_and_persistent_key(self):
        cfg = g.Settings(high='C5', fourth_modulation_probability=1, seventh_modulation_probability=1)
        walk = g.ChordWalk(cfg)
        chord, status = walk.maybe_modulate((48, 52, 55), (48, 53, 55))
        self.assertEqual(chord, (48, 54, 55))
        self.assertEqual(walk.key, 'G')
        self.assertIn('C -> G', status)
        # The fourth of G is C: raising C to C# now moves to D, not G.
        chord, status = walk.maybe_modulate((43, 59, 62), (43, 59, 60))
        self.assertEqual(chord, (43, 59, 61))
        self.assertEqual(walk.key, 'D')
        walk = g.ChordWalk(cfg)
        chord, status = walk.maybe_modulate((48, 52, 57), (48, 52, 59))
        self.assertEqual(chord, (48, 52, 58))
        self.assertEqual(walk.key, 'F')
        self.assertIn('C -> F', status)

    def test_modulation_rejections_and_eligibility(self):
        cfg = g.Settings(fourth_modulation_probability=1, seventh_modulation_probability=1)
        cases = [
            (cfg, (36, 52, 54), (36, 53, 54)),  # altered unison
            (cfg, (48, 52, 66), (48, 52, 65)),  # alteration would undo the move
            (g.Settings(high='F4', fourth_modulation_probability=1), (48, 55, 64), (48, 55, 65)),
            (cfg, (52, 55, 60), (52, 55, 59)),  # lowering seventh would shrink span to tritone
        ]
        for settings, previous, candidate in cases:
            walk = g.ChordWalk(settings)
            chord, status = walk.maybe_modulate(previous, candidate)
            self.assertEqual(chord, candidate)
            self.assertEqual(walk.key, 'C')
            self.assertIn('blocked', status)
        # F sits unchanged in the chord; moving G to A does not roll modulation.
        walk = g.ChordWalk(cfg)
        chord, status = walk.maybe_modulate((48, 53, 55), (48, 53, 57))
        self.assertEqual(walk.key, 'C')
        self.assertEqual(status, 'moved')
        walk = g.ChordWalk(g.Settings(diatonic_steps=[0], diatonic_probabilities=[1],
                                     fourth_modulation_probability=1, seventh_modulation_probability=1))
        walk.chord = (48, 53, 59)
        self.assertEqual(walk.advance(), ((48, 53, 59), 0, 'repeat'))
        self.assertEqual(walk.key, 'C')
        walk = g.ChordWalk(g.Settings(mode='chromatic', fourth_modulation_probability=1))
        self.assertEqual(walk.maybe_modulate((48, 52, 55), (48, 53, 55)), ((48, 53, 55), 'moved'))
        self.assertEqual(walk.key, 'C')

    def test_retained_out_of_key_notes_and_long_walk(self):
        walk = g.ChordWalk(g.Settings(seed=5))
        walk.tonic = 7
        walk.refresh_scale()
        walk.chord = (48, 52, 54)  # C remains from the old key
        moves = [c for c in walk.candidates(1) if 48 not in c]
        self.assertTrue(moves)
        self.assertTrue(all(next(iter(set(c) - set(walk.chord))) in (47, 50) for c in moves))
        changes = 0
        for _ in range(10000):
            previous = set(walk.chord)
            chord, step, status = walk.advance()
            self.assertTrue(g.valid_chord(chord))
            self.assertTrue(all(36 <= n <= 60 for n in chord))
            if status.startswith('modulated'):
                self.assertLessEqual(len(previous & set(chord)), 2)
                changes += 1
                for new in set(chord) - previous:
                    self.assertIn((new - walk.tonic) % 12, g.C_MAJOR)
            else:
                self.assertEqual(len(previous & set(chord)), 3 if step == 0 or status.startswith('blocked:') else 2)
        self.assertGreater(changes, 100)

    def test_walk_constraints_and_step_distribution(self):
        for mode in ('diatonic', 'chromatic'):
            walk = g.ChordWalk(g.Settings(mode=mode, seed=7, fourth_modulation_probability=0, seventh_modulation_probability=0))
            counts = collections.Counter()
            for _ in range(20000):
                previous = set(walk.chord)
                chord, step, status = walk.advance()
                counts[step] += 1
                self.assertTrue(g.valid_chord(chord))
                self.assertTrue(all(36 <= n <= 60 for n in chord))
                if mode == 'diatonic':
                    self.assertTrue(all(n % 12 in g.C_MAJOR for n in chord))
                if step == 0:
                    self.assertEqual(previous, set(chord))
                else:
                    self.assertEqual(status, 'moved')
                    self.assertEqual(len(previous & set(chord)), 2)
                    old = next(iter(previous - set(chord)))
                    new = next(iter(set(chord) - previous))
                    self.assertEqual(abs(walk.indices[old] - walk.indices[new]), step)
            if mode == 'diatonic':
                for step, target in enumerate((.1, .6, .3)):
                    self.assertAlmostEqual(counts[step] / 20000, target, delta=.015)
            else:
                self.assertEqual(counts[1], 20000)

    def test_all_default_states_have_legal_positive_steps(self):
        for mode in ('diatonic', 'chromatic'):
            walk = g.ChordWalk(g.Settings(mode=mode))
            for chord in itertools.combinations(walk.pool, 3):
                if g.valid_chord(chord):
                    walk.chord = chord
                    for step in ((1, 2) if mode == 'diatonic' else (1,)):
                        self.assertTrue(walk.candidates(step), (mode, chord, step))

    def test_invalid_settings_and_blocked_step(self):
        for cfg in (g.Settings(low='C4', high='C2'), g.Settings(low='C2', high='F#2'),
                    g.Settings(diatonic_probabilities=[0, 0, 0]), g.Settings(hold=0),
                    g.Settings(silence=-1), g.Settings(starting_key='H'),
                    g.Settings(fourth_modulation_probability=1.1),
                    g.Settings(seventh_modulation_probability=-.1)):
            with self.assertRaises(ValueError):
                g.ChordWalk(cfg)
        walk = g.ChordWalk(g.Settings(diatonic_steps=[100], diatonic_probabilities=[1]))
        previous = walk.chord
        chord, step, status = walk.advance()
        self.assertEqual(chord, previous)
        self.assertEqual(step, 100)
        self.assertIn('blocked', status)

    def test_relative_weights(self):
        for mode in ('diatonic', 'chromatic'):
            kwargs = {mode + '_steps': [0, 1, 2], mode + '_probabilities': [1, 6, 3]}
            weighted = g.ChordWalk(g.Settings(mode=mode, seed=17, **kwargs))
            normalized = g.ChordWalk(g.Settings(mode=mode, seed=17, **{
                mode + '_steps': [0, 1, 2], mode + '_probabilities': [.1, .6, .3]}))
            for _ in range(1000):
                self.assertEqual(weighted.advance(), normalized.advance())
        for weights in ([0, 7, 0], [0, 1e308, 0]):
            walk = g.ChordWalk(g.Settings(diatonic_probabilities=weights))
            for _ in range(100):
                self.assertEqual(walk.advance()[1], 1)
        for weights in ([0, 0, 0], [-1, 2, 3], [1, float('inf'), 3], [1, float('nan'), 3]):
            with self.assertRaises(ValueError):
                g.ChordWalk(g.Settings(diatonic_probabilities=weights))

    def test_play_timing_and_interrupt_cleanup(self):
        now = [0.0]
        sent = []
        class Port:
            def send(self, message):
                sent.append((now[0], message))
        def wait(deadline):
            now[0] = deadline
        with patch.object(g.time, 'perf_counter', side_effect=lambda: now[0]), \
             patch.object(g, 'wait_until', side_effect=wait), contextlib.redirect_stdout(io.StringIO()):
            g.play(Port(), g.ChordWalk(g.Settings(chords=2, seed=1)))
        self.assertEqual([t for t,m in sent if m.type == 'note_on'], [0]*3 + [6]*3)
        self.assertEqual([t for t,m in sent if m.type == 'note_off'], [3]*3 + [9]*3)
        self.assertEqual(now[0], 12)
        self.assertFalse(any(m.type == 'control_change' and m.control == 120 for _,m in sent))
        sent.clear()
        with patch.object(g, 'wait_until', side_effect=KeyboardInterrupt), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                g.play(Port(), g.ChordWalk(g.Settings(chords=2)))
        self.assertEqual({m.note for _,m in sent if m.type == 'note_on'},
                         {m.note for _,m in sent if m.type == 'note_off'})

    def test_export_and_seed(self):
        cfg = g.Settings(chords=4, seed=42)
        self.assertEqual(list(g.chord_stream(g.ChordWalk(cfg))), list(g.chord_stream(g.ChordWalk(cfg))))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.mid'
            g.save_midi(path, g.ChordWalk(cfg))
            midi = mido.MidiFile(path)
            self.assertAlmostEqual(midi.length, 24)
            active = set()
            maximum = 0
            for message in midi.tracks[0]:
                if message.type == 'note_on':
                    self.assertNotIn(message.note, active)
                    active.add(message.note)
                elif message.type == 'note_off':
                    active.remove(message.note)
                maximum = max(maximum, len(active))
            self.assertEqual(maximum, 3)
            self.assertFalse(active)

    def test_export_modulation_metadata_matches_notes(self):
        cfg = g.Settings(low='C3', high='C5', chords=40, seed=42)
        walk = g.ChordWalk(cfg)
        expected_keys = []
        expected_chords = []
        for chord, _, _ in g.chord_stream(walk):
            if not expected_keys or expected_keys[-1] != walk.key:
                expected_keys.append(walk.key)
            expected_chords.append(chord)
        self.assertGreater(len(expected_keys), 1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'modulations.mid'
            g.save_midi(path, g.ChordWalk(cfg))
            midi = mido.MidiFile(path)
            self.assertEqual([m.key for m in midi.tracks[0] if m.type == 'key_signature'], expected_keys)
            notes = [m.note for m in midi.tracks[0] if m.type == 'note_on']
            self.assertEqual([tuple(notes[i:i+3]) for i in range(0, len(notes), 3)], expected_chords)
            self.assertAlmostEqual(midi.length, 240)

    def test_all_starting_keys(self):
        for tonic, name in enumerate(g.KEY_NAMES):
            walk = g.ChordWalk(g.Settings(starting_key=name, seed=2))
            self.assertEqual(walk.tonic, tonic)
            self.assertTrue(all((n - tonic) % 12 in g.C_MAJOR for n in walk.chord))
            for _ in range(100):
                self.assertTrue(g.valid_chord(walk.advance()[0]))


if __name__ == '__main__':
    unittest.main()
