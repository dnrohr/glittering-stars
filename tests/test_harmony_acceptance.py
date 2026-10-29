"""Independent musical-policy fixtures and invariant walks."""
from dataclasses import replace
import itertools
import unittest
from glittering_stars.domain import Config, Engine, Voice, validate_chord


class HarmonyAcceptance(unittest.TestCase):
    def test_initial_sampling_set_equals_canonical_constraints(self):
        for mode in ('diatonic','chromatic'):
            for gap,octaves in ((1,True),(3,False)):
                cfg=Config(seed=3,low=48,high=72,mode=mode,min_gap=gap,octave_doubling=octaves,
                           min_span=9,max_span=19)
                engine=Engine(cfg)
                expected=[]
                for pitches in itertools.combinations(range(48,73),3):
                    if mode=='diatonic' and any(n%12 not in (0,2,4,5,7,9,11) for n in pitches):continue
                    try:validate_chord(tuple(Voice(i,n) for i,n in enumerate(pitches)),cfg)
                    except ValueError:continue
                    expected.append(pitches)
                self.assertEqual(engine._initial_chords(),expected)

    def test_all_keys_policies_and_constraint_walks(self):
        for key in range(12):
            for policy in ('off','moving_note','whole_chord','pivot'):
                for octaves in (True,False):
                    cfg=Config(seed=key,starting_key=key,low=36,high=84,policy=policy,
                               min_span=12,max_span=36,min_gap=3,octave_doubling=octaves,
                               fourth_modulation_probability=1,seventh_modulation_probability=1)
                    engine=Engine(cfg)
                    for _ in range(100):
                        before={v.id:v.pitch for v in engine.voices}
                        decision=engine.advance()
                        validate_chord(engine.voices,cfg)
                        self.assertEqual({v.id for v in engine.voices},{0,1,2})
                        if decision['modulated'] and policy in ('whole_chord','pivot'):
                            self.assertTrue(all((v.pitch-engine.key)%12 in (0,2,4,5,7,9,11) for v in engine.voices))
                        if not decision['modulated'] and decision['status']=='moved':
                            self.assertEqual(sum(before[v.id]!=v.pitch for v in engine.voices),1)

    def test_pivot_one_choice_one_roll_no_opposite_retry(self):
        engine=Engine(Config(seed=5,low=36,high=84,policy='pivot',
                             fourth_modulation_probability=.2,seventh_modulation_probability=.9))
        voices=tuple(Voice(i,n) for i,n in enumerate((48,64,79))) # C E G fit both adjacent keys
        class Draws:
            def __init__(self): self.choices=0;self.rolls=0
            def choice(self,eligible):
                self.choices+=1
                self.eligible=eligible
                return eligible[0]
            def random(self): self.rolls+=1;return .5
        draws=Draws();engine._rng=draws
        result,attempted,accepted,reason,affected=engine._try_modulation(voices,voices,0,0)
        self.assertEqual(len(draws.eligible),2)
        self.assertEqual((draws.choices,draws.rolls),(1,1))
        self.assertTrue(attempted);self.assertFalse(accepted)
        self.assertEqual(engine.key,0)
        self.assertEqual(result,voices)
        engine.config=replace(engine.config,fourth_modulation_probability=0)
        engine._try_modulation(voices,voices,0,0)
        self.assertEqual(len(draws.eligible),1)
        self.assertEqual(draws.eligible[0][0],5)

    def test_c_natural_belongs_to_g_major_spec_example_correction(self):
        engine=Engine(Config(seed=3,low=36,high=84,policy='whole_chord',fourth_modulation_probability=1))
        old=tuple(Voice(i,n) for i,n in enumerate((48,64,67)))
        candidate=tuple(Voice(i,n) for i,n in enumerate((48,64,65)))
        changed,_,accepted,_,_=engine._try_modulation(old,candidate,2,0)
        self.assertTrue(accepted)
        self.assertEqual(engine.key,7)
        self.assertEqual([v.pitch for v in changed],[48,64,66])

    def test_direction_extremes_and_all_locked_do_not_fallback(self):
        for upward in (0,1):
            cfg=Config(seed=4,mode='chromatic',low=48,high=72,upward_probability=upward,policy='off')
            engine=Engine(cfg)
            for _ in range(100):
                decision=engine.advance()
                if decision['status']=='moved':
                    self.assertEqual(decision['direction'],'up' if upward else 'down')
            engine.apply_config(replace(cfg,locks=(0,1,2)),1)
            before=engine.voices
            for _ in range(10):
                decision=engine.advance()
                self.assertIn(decision['status'],('blocked','repeat'))
                self.assertEqual(engine.voices,before)
