import copy
import json
import unittest

from glittering_stars.domain import Config, Engine, Voice, validate_chord


class EngineTests(unittest.TestCase):
    def config(self, **changes):
        return Config(**changes)

    def test_chord_constraints_and_voice_identity_survive_crossing_and_restore(self):
        cfg = self.config(low="C2", high="C6", mode="chromatic", chromatic_steps=(2,), chromatic_probabilities=(1,),
                          upward_probability=1.0)
        engine = Engine(cfg, seed=7)
        state = engine.snapshot()
        # Force a valid close voicing where voice 0 can cross voice 1 on upward motion.
        state["voices"] = [{"id": 0, "pitch": 60}, {"id": 1, "pitch": 61}, {"id": 2, "pitch": 72}]
        for seed in range(100):
            seeded = Engine(cfg, seed=seed).snapshot()
            seeded["voices"] = state["voices"]
            engine = Engine.restore(seeded)
            result = engine.advance()
            if result["voice_id"] == 0:
                self.assertEqual(engine.voices[0].pitch, 62)
                self.assertLess(engine.voices[1].pitch, engine.voices[0].pitch)
                self.assertEqual(engine.snapshot()["voices"][0]["id"], 0)
                validate_chord(engine.voices, cfg)
                break
        else:
            self.fail("did not find deterministic voice-0 crossing seed")

    def test_snapshot_restore_reproduces_one_hundred_transitions(self):
        cfg = self.config(seed=148, low="C2", high="C6")
        engine = Engine(cfg)
        for _ in range(9):
            engine.advance()
        encoded = json.loads(json.dumps(engine.snapshot()))
        restored = Engine.restore(encoded)
        self.assertEqual(engine.snapshot(), restored.snapshot())
        for _ in range(100):
            self.assertEqual(engine.advance(), restored.advance())
            self.assertEqual(engine.snapshot(), restored.snapshot())

    def test_bad_config_and_rng_snapshots_rejected_without_mutation(self):
        for kwargs in ({"diatonic_steps": (1, 1)}, {"chromatic_probabilities": (0,)},
                       {"min_span": 6}, {"upward_probability": float("nan")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.config(**kwargs)
        engine = Engine(self.config(), seed=4)
        before = engine.snapshot()
        bad = copy.deepcopy(before)
        bad["rng_state"] = [3, [0, -1], None]
        with self.assertRaises(ValueError):
            Engine.restore(bad)
        bad = copy.deepcopy(before)
        bad["schema_version"] = 999
        with self.assertRaises(ValueError):
            Engine.restore(bad)
        self.assertEqual(engine.snapshot(), before)

    def test_initial_and_step_zero_do_not_modulate(self):
        cfg = self.config(diatonic_steps=(0,), diatonic_probabilities=(1,),
                          fourth_modulation_probability=1, seventh_modulation_probability=1)
        engine = Engine(cfg, seed=11)
        before = engine.snapshot()
        self.assertEqual(engine.initial()["status"], "initial")
        self.assertEqual(engine.snapshot(), before)
        result = engine.advance()
        self.assertEqual(result["status"], "repeat")
        self.assertEqual(result["modulation_attempt"], False)

    def test_locked_voices_are_immobile_and_modulation_vetoes_octaves_atomically(self):
        cfg = self.config(low="C2", high="C6", diatonic_steps=(1,), diatonic_probabilities=(1,),
                          locks=(0, 1, 2), upward_probability=0.5)
        engine = Engine(cfg, seed=1)
        result = engine.advance()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len({v.pitch for v in engine.voices}), 3)

        # A locked F octave must veto the all-octave F->F# alteration.
        cfg = self.config(low="C2", high="C6", policy="moving_note", diatonic_steps=(1,),
                          diatonic_probabilities=(1,), fourth_modulation_probability=1,
                          upward_probability=1, locks=(0,))
        state = Engine(cfg, seed=2).snapshot()
        state["voices"] = [{"id": 0, "pitch": 53}, {"id": 1, "pitch": 60}, {"id": 2, "pitch": 65}]
        engine = Engine.restore(state)
        # The locked F is not selected as the mover; make the deterministic candidate F4 by direct RNG setup
        # via repeated engine seeds until the chosen legal voice is the C4 voice.
        # The assertion is the invariant: if any locked pitch-class octave would change, none changes.
        for seed in range(100):
            trial = Engine.restore({**state, "rng_state": Engine(cfg, seed=seed).snapshot()["rng_state"]})
            result = trial.advance()
            if result["modulation_attempt"] and "locked voice" in result["reason"]:
                pitches = {v.id: v.pitch for v in trial.voices}
                self.assertEqual(pitches[0], 53)
                self.assertEqual(result["key_after"], result["key_before"])
                break

    def test_allowed_keys_and_cooldown_and_manual_key(self):
        cfg = self.config(low="C2", high="C6", policy="moving_note", allowed_keys=(0, 7, 5),
                          max_fifths=2, cooldown_events=2, diatonic_steps=(1,),
                          diatonic_probabilities=(1,), fourth_modulation_probability=1,
                          upward_probability=1)
        engine = Engine(cfg, seed=3)
        engine.cooldown = 1
        result = engine.advance()
        self.assertEqual(result["cooldown"], 0)
        self.assertFalse(result["modulated"])
        before = engine.snapshot()
        with self.assertRaises(ValueError):
            engine.set_key(2)
        self.assertEqual(engine.snapshot(), before)
        engine.set_key(7)
        self.assertEqual(engine.key, 7)
        self.assertEqual(engine.cooldown, 0)

    def test_pivot_changes_context_without_pitch_changes(self):
        cfg = self.config(low="C2", high="C6", policy="pivot", diatonic_steps=(1,),
                          diatonic_probabilities=(1,), fourth_modulation_probability=1,
                          seventh_modulation_probability=0, upward_probability=1)
        state = Engine(cfg, seed=8).snapshot()
        state["voices"] = [{"id": 0, "pitch": 55}, {"id": 1, "pitch": 59}, {"id": 2, "pitch": 62}]
        # Ensure the ordinary move lands on a chord fitting both C and G; choose a seeded path.
        for seed in range(500):
            start = Engine(cfg, seed=seed).snapshot()
            start["voices"] = state["voices"]
            trial = Engine.restore(start)
            before = tuple(v.pitch for v in trial.voices)
            result = trial.advance()
            if result["modulated"]:
                self.assertEqual(result["key_after"], 7)
                self.assertEqual(len(set(v.pitch for v in trial.voices)), 3)
                self.assertNotEqual(tuple(v.pitch for v in trial.voices), before)
                # Pivot itself must not retune; resulting movement only changes its one voice.
                self.assertEqual(result["affected_voice_ids"], [])
                break

    def test_whole_chord_fit_rejects_destination_with_foreign_pitch(self):
        cfg = self.config(low="C2", high="C6", policy="whole_chord", diatonic_steps=(1,),
                          diatonic_probabilities=(1,), fourth_modulation_probability=1,
                          upward_probability=1)
        # C natural belongs to G major, so use C# to test a foreign pitch;
        # the specification's C3-E4-F#4 example actually fits G major.
        engine = Engine(cfg, seed=5)
        engine.voices = (Voice(0, 49), Voice(1, 64), Voice(2, 53))  # C#3 E4 F3
        candidate = (Voice(0, 49), Voice(1, 64), Voice(2, 65))
        result, attempted, modulated, reason, affected = engine._try_modulation(
            engine.voices, candidate, 2, 0)
        self.assertTrue(attempted)
        self.assertFalse(modulated)
        self.assertIn("does not fit destination", reason)
        self.assertEqual(engine.key, 0)
        self.assertEqual(result, candidate)

    def test_large_relative_weights_and_negative_seed_roundtrip(self):
        cfg = self.config(seed=-12, diatonic_steps=(0, 1),
                          diatonic_probabilities=(1e308, 1e308))
        engine = Engine(cfg)
        restored = Engine.restore(json.loads(json.dumps(engine.snapshot())))
        self.assertEqual(restored.effective_seed, -12)
        self.assertEqual(engine.snapshot(), restored.snapshot())
        for _ in range(10):
            self.assertEqual(engine.advance(), restored.advance())

    def test_apply_config_rejects_without_mutating_engine(self):
        engine = Engine(self.config(seed=3), seed=3)
        before = engine.snapshot()
        with self.assertRaises(ValueError):
            engine.apply_config(self.config(low="C5", high="C6"), 1)
        self.assertEqual(engine.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
