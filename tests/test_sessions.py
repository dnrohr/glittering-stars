import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mido
from glittering_stars.domain import Config, Engine
from glittering_stars.sessions import save, load, validate_session, export_midi, save_preset, load_preset


def fixture():
    config = Config(seed=123)
    engine = Engine(config)
    history = []
    for i in range(4):
        decision = engine.initial() if i == 0 else engine.advance()
        history.append(dict(id=str(i), branch_id='main', voices=engine.snapshot()['voices'],
                            key=engine.key, hold=.1234+i*.01, silence=.4567, velocity=55+i,
                            channel=3, revision=0, decision=decision, snapshot=engine.snapshot()))
    return dict(config=config.to_dict(), engine=engine.snapshot(), history=history,
                branches=[dict(id='main', parent_id=None, anchor_id=None, name='Main')],
                selection=['1','2'], playback_ids=['1','2'], phase='Holding', cursor=1,
                active_branch='main', mode='loop', override=False, pending_config=None)


class SessionTests(unittest.TestCase):
    def test_roundtrip_is_silent_and_rng_exact(self):
        original = fixture()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'session.json'
            save(path, original)
            restored = load(path)
        self.assertEqual(restored['phase'], 'Idle')
        self.assertEqual(original['history'], restored['history'])
        a, b = Engine.restore(original['engine']), Engine.restore(restored['engine'])
        self.assertEqual([a.advance() for _ in range(100)], [b.advance() for _ in range(100)])

    def test_failed_atomic_replace_preserves_last_good(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'session.json'
            save(path, fixture())
            good = path.read_bytes()
            with patch('glittering_stars.sessions.storage.os.replace', side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):
                    save(path, fixture())
            self.assertEqual(path.read_bytes(), good)
            self.assertEqual(list(Path(folder).glob('*.tmp')), [])

    def test_corruption_and_future_inspection(self):
        original = fixture()
        for change in (lambda x:x['history'][0].update(voices=[]),
                       lambda x:x['history'][0].update(key=12),
                       lambda x:x['history'][0].update(hold=float('nan')),
                       lambda x:x.update(selection=['missing']),
                       lambda x:x['branches'][0].update(parent_id='main'),
                       lambda x:x['history'][0]['snapshot'].update(rng_state=['evil'])):
            document = copy.deepcopy(original)
            change(document)
            with self.assertRaises(ValueError):
                validate_session(document)
        future = copy.deepcopy(original)
        future['schema_version'] = 2
        future['history'][0]['snapshot']['schema_version'] = 2
        self.assertFalse(validate_session(future)['continuation_supported'])
        self.assertEqual(original['phase'], 'Holding')

    def test_presets_and_legacy_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'legacy.json'
            path.write_text(json.dumps(dict(low='C3', high='C5', seed=12)))
            config = load_preset(path)
            self.assertEqual(config.min_span, 7)
            self.assertEqual(config.policy, 'moving_note')
            save_preset(path, config)
            self.assertEqual(load_preset(path), config)
            self.assertNotIn('history', json.loads(path.read_text()))

    def test_pending_context_schema_is_validated(self):
        for field, value in [('output_channel',16),('output_channel',True),('pending_reseed','invalid'),('pending_key','H'),('run_events',-1),
                             ('start_from_anchor','yes'),('context_log',[dict(kind='arbitrary')])]:
            view=fixture();view[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_session(view)

    def test_midi_exact_absolute_rounding_final_gap_and_keys(self):
        events = fixture()['history'][1:3]
        events[0]['key'], events[1]['key'] = 0, 7
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'selection.mid'
            duration = export_midi(path, events, repetitions=3)
            midi = mido.MidiFile(path)
        tick = 0
        on, off, keys = [], [], []
        for msg in midi.tracks[0]:
            self.assertGreaterEqual(msg.time, 0)
            tick += msg.time
            if msg.type == 'note_on': on.append((tick,msg.note,msg.velocity,msg.channel))
            if msg.type == 'note_off': off.append((tick,msg.note,msg.channel))
            if msg.type == 'key_signature': keys.append((tick,msg.key))
        expected_on, expected_off = [], []
        second = 0
        for _ in range(3):
            for event in events:
                expected_on.extend((round(second*480), v['pitch'],event['velocity'],3) for v in event['voices'])
                expected_off.extend((round((second+event['hold'])*480),v['pitch'],3) for v in event['voices'])
                second += event['hold']+event['silence']
        self.assertEqual(on, expected_on)
        self.assertEqual(off, expected_off)
        self.assertEqual(keys[0], (0,'C'))
        self.assertEqual(len(keys), 6)
        self.assertEqual(tick, round(duration*480))
        self.assertGreater(tick, off[-1][0])

    def test_export_override_does_not_mutate(self):
        events = fixture()['history']
        before = copy.deepcopy(events)
        with tempfile.TemporaryDirectory() as folder:
            duration = export_midi(Path(folder)/'override.mid', events, override=dict(hold=1,silence=2,velocity=90))
        self.assertEqual(duration, 12)
        self.assertEqual(before, events)


if __name__ == '__main__':
    unittest.main()
