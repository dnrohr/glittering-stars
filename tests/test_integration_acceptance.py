"""Independent cross-module acceptance probes, separate from subsystem authors."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from glittering_stars.domain import Config, Engine
from glittering_stars.playback import Controller
from glittering_stars.sessions import save, load


class Clock:
    def __init__(self): self.now = 0.
    def __call__(self): return self.now


class Sink:
    def __init__(self, clock): self.messages=[]; self.clock=clock
    def send(self, msg): self.messages.append((self.clock(),msg.copy()))


class IntegratedAcceptance(unittest.TestCase):
    def setUp(self):
        self.clock=Clock()
        self.sink=Sink(self.clock)
        self.controller=Controller(Config(seed=143,hold=.2,silence=.3),self.sink,self.clock)

    def command(self, name, **payload):
        reply=self.controller.command(name,**payload)
        self.assertTrue(reply['ok'],reply)
        return reply

    def finish(self):
        for _ in range(2):
            self.clock.now=self.controller.next_deadline
            self.controller.tick()

    def generate(self, count):
        for _ in range(count):
            self.command('next')
            self.finish()
        return self.controller.view()['history']

    def test_continue_historical_rng_retains_parent_future(self):
        history=list(self.generate(12))
        anchor=history[3]
        expected=Engine.restore(anchor['snapshot'])
        decisions=[expected.advance() for _ in range(100)]
        self.command('continue',anchor_id=anchor['id'])
        for decision in decisions:
            self.command('next')
            event=self.controller.view()['history'][-1]
            self.assertEqual(event['decision'],decision)
            self.finish()
        self.assertEqual(self.controller.view()['history'][:12],history)

    def test_transition_generate_to_loop_starts_first_selected_with_full_gap(self):
        history=self.generate(12)
        selected=[e['id'] for e in history[3:7]]
        self.command('play')
        count=len(self.controller.view()['history'])
        self.command('loop',event_ids=selected)
        self.finish()
        view=self.controller.view()
        self.assertEqual(len(view['history']),count)
        self.assertEqual(view['mode'],'loop')
        actual=[m.note for _,m in self.sink.messages[-3:] if m.type=='note_on']
        self.assertEqual(actual,[v['pitch'] for v in history[3]['voices']])
        before=copy.deepcopy(view['engine'])
        for _ in range(400): self.finish()
        after=self.controller.view()
        self.assertEqual(after['engine'],before)
        self.assertEqual(len(after['history']),count)
        self.command('stop')

    def test_live_revision_replay_isolation_and_override(self):
        history=self.generate(3)
        ids=[history[0]['id']]
        self.command('loop',event_ids=ids)
        cfg=self.controller.view()['config']|dict(hold=1.,silence=2.,velocity=90,policy='off')
        self.command('config',config=cfg)
        snapshot=copy.deepcopy(self.controller.view()['engine'])
        self.command('play')
        self.assertEqual(self.controller.next_deadline,self.clock.now+.2)
        self.finish()
        self.assertEqual(self.controller.view()['engine'],snapshot)
        self.assertIsNotNone(self.controller.view()['pending_config'])
        self.command('override',enabled=True)
        self.finish()
        self.assertEqual(self.controller.next_deadline,self.clock.now+1.)
        self.assertEqual(self.controller.view()['history'],history)
        self.command('stop')

    def test_save_loaded_controller_retains_loop_position_and_stays_silent(self):
        history=self.generate(4)
        self.command('loop',event_ids=[e['id'] for e in history[1:3]])
        self.command('play')
        self.finish()
        view=self.controller.view()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'session.json'
            save(path,view)
            incoming=load(path)
            count=sum(m.type=='note_on' for _,m in self.sink.messages)
            self.command('load',session=incoming)
        restored=self.controller.view()
        self.assertEqual(restored['phase'],'Idle')
        self.assertEqual(restored['mode'],'loop')
        self.assertEqual(restored['cursor'],view['cursor'])
        self.assertEqual(sum(m.type=='note_on' for _,m in self.sink.messages),count)
        self.assertEqual(restored['engine'],view['engine'])

    def test_edit_anchor_copies_cooldown_and_preserves_history(self):
        history=list(self.generate(4))
        anchor=history[2]
        anchor_snapshot=copy.deepcopy(anchor['snapshot'])
        self.command('edit',anchor_id=anchor['id'],values=dict(hold=1.2,silence=2.3,velocity=100))
        after=self.controller.view()
        self.assertEqual(after['history'][:4],history)
        edit=after['history'][-1]
        self.assertEqual(edit['snapshot']['rng_state'],anchor_snapshot['rng_state'])
        self.assertEqual(edit['snapshot']['cooldown'],anchor_snapshot['cooldown'])
        self.assertEqual(edit['hold'],1.2)
        self.assertEqual(edit['snapshot']['config']['hold'],1.2)

    def test_save_before_first_child_event_does_not_replay_anchor(self):
        history=self.generate(2)
        anchor=history[0]
        expected=Engine.restore(anchor['snapshot']).advance()
        self.command('continue',anchor_id=anchor['id'])
        incoming=json.loads(json.dumps(self.controller.view()))
        other=Controller(Config(seed=1),None,self.clock)
        self.assertTrue(other.command('load',session=incoming)['ok'])
        self.assertTrue(other.command('next')['ok'])
        self.assertEqual(other.view()['history'][-1]['decision'],expected)

    def test_locks_cooldown_roundtrip_and_replay_isolation(self):
        self.generate(4)
        view=copy.deepcopy(self.controller.view())
        for snapshot in [view['engine']]+[event['snapshot'] for event in view['history']]:
            snapshot['config']['locks']=[0]
            snapshot['config']['cooldown_events']=3
            snapshot['cooldown']=3
        view['config']=view['engine']['config']
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'locked.json'
            save(path,view);incoming=load(path)
        self.command('load',session=incoming)
        before=copy.deepcopy(self.controller.view()['engine'])
        self.assertEqual(before['cooldown'],3)
        self.assertEqual(before['config']['locks'],[0])
        self.command('loop',event_ids=[e['id'] for e in view['history'][1:3]])
        self.command('play')
        for _ in range(100):self.finish()
        self.assertEqual(self.controller.view()['engine'],before)
        self.command('stop')
        anchor=view['history'][1]
        self.command('continue',anchor_id=anchor['id'])
        self.assertEqual(self.controller.view()['engine']['cooldown'],3)
        self.command('next')
        self.assertEqual(self.controller.view()['engine']['cooldown'],2)
        self.assertEqual(self.controller.view()['engine']['voices'][0],anchor['snapshot']['voices'][0])


if __name__=='__main__': unittest.main()
