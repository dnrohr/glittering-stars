"""Finite audible acceptance demo: four stored chords, exactly two passes."""
from pathlib import Path
import json
import os
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import mido
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from desktop import MainWindow
from glittering_stars.domain import Config
from glittering_stars.playback import Controller


def main():
    with tempfile.TemporaryDirectory() as folder:
        os.environ['LOCALAPPDATA']=folder
        output=next(n for n in mido.get_output_names() if n.startswith('Surge Generative'))
        received=[]
        midi_input=next(n for n in mido.get_input_names() if n.startswith('Surge Generative'))
        port=mido.open_input(midi_input,callback=lambda msg:received.append((time.perf_counter(),msg.copy())))
        cfg=Config(port=output,seed=42,low='C3',high='C5',hold=.5,silence=.8,velocity=40)
        now=[0.]
        core=Controller(cfg,clock=lambda:now[0])
        for _ in range(8):
            assert core.command('next')['ok']
            now[0]=core.next_deadline;core.tick()
            now[0]=core.next_deadline;core.tick()
        view=core.view()
        ids=[e['id'] for e in view['history'][3:7]]
        app=QApplication([])
        window=MainWindow(cfg,preview=False)
        window.show()
        try:
            def wait_for(predicate, seconds=3):
                deadline=time.monotonic()+seconds
                while time.monotonic()<deadline:
                    app.processEvents();time.sleep(.005)
                    if predicate():return
                raise RuntimeError('Demo did not reach its expected transport state')
            window.worker.command('load',session=view)
            wait_for(lambda:len(window._view.get('history',[]))==8)
            window.port.setCurrentText(output);window.connect_btn.click()
            wait_for(lambda:window._view.get('connected'))
            before=core.view()['engine']
            for cycle in range(2):
                window.worker.command('replay',event_ids=ids)
                wait_for(lambda:window._view.get('mode')=='replay' and window._view.get('cursor')==0)
                window.play_btn.click()
                wait_for(lambda:window._view.get('phase')=='Holding')
                wait_for(lambda:window._view.get('phase')=='Paused' and window._view.get('cursor')==4,10)
            snapshot=window._view
            window.grab().save(str(ROOT/'docs/validation/audible-demo.png'))
        finally:
            window.close();window._io_pool.shutdown(wait=True);port.close()
        ons=[msg.note for _,msg in received if msg.type=='note_on' and msg.velocity]
        source=[v['pitch'] for e in view['history'][3:7] for v in e['voices']]
        assert ons==source*2,(ons,source)
        assert snapshot['engine']==before
        report=dict(passes=2,events_per_pass=4,hold=.5,gap=.8,velocity=40,notes=ons,
                    midi_exact=True,rng_unchanged=True,audio_listening='Requires user confirmation')
        (ROOT/'docs/validation/audible-demo.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))


if __name__=='__main__':main()
