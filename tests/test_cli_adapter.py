import unittest
from dataclasses import asdict
import generate
from glittering_stars.domain import Config, Engine


class CLIAdapterTests(unittest.TestCase):
    def test_cli_generation_uses_shared_engine(self):
        settings=generate.Settings(seed=31,low='C3',high='C5')
        walk=generate.ChordWalk(settings)
        engine=Engine(Config.from_dict(asdict(settings)))
        self.assertEqual(walk.chord,tuple(sorted(v.pitch for v in engine.voices)))
        for _ in range(100):
            decision=engine.advance()
            chord,step,status=walk.advance()
            self.assertEqual(chord,tuple(sorted(v.pitch for v in engine.voices)))
            self.assertEqual(step,decision['step'])
            self.assertEqual(walk.tonic,engine.key)

    def test_cli_panic_entry_point_uses_recorded_sink(self):
        sent=[]
        class Sink:
            def send(self,msg): sent.append(msg)
        generate.panic(Sink())
        self.assertEqual([(m.type,m.control,m.value,m.channel) for m in sent],
                         [('control_change',64,0,0),('control_change',123,0,0),('control_change',120,0,0)])
