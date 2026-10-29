"""Finite 10,000-event native Qt render, selection, background-save stress."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from desktop import MainWindow
from glittering_stars.domain import Config
from glittering_stars.playback import Controller
from glittering_stars.sessions import save, load


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',default=str(ROOT/'docs/validation/capacity.json'))
    args=parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        os.environ['LOCALAPPDATA']=folder
        clock=[0.]
        core=Controller(Config(seed=12,low=48,high=72,hold=.03,silence=.03),clock=lambda:clock[0])
        began=time.perf_counter()
        for _ in range(10000):
            result=core.command('next')
            if not result['ok']:raise RuntimeError(result)
            clock[0]=core.next_deadline;core.tick()
            clock[0]=core.next_deadline;core.tick()
        generation=time.perf_counter()-began
        view=core.view()
        app=QApplication.instance() or QApplication([])
        window=MainWindow(Config(seed=12),preview=True)
        window.show();app.processEvents()
        sequence=window.worker.command('load',session=view)
        if not window.worker.wait_ack(sequence,3)['ok']:raise RuntimeError('Load failed')
        began=time.perf_counter()
        app.processEvents()
        window.timeline.scrollTo(window.timeline_model.index(9999,1))
        app.processEvents()
        render=time.perf_counter()-began
        point=window.timeline.visualRect(window.timeline_model.index(9996,1)).center()
        QTest.mouseClick(window.timeline.viewport(),Qt.MouseButton.LeftButton,pos=point)
        for _ in range(3):QTest.keyClick(window.timeline,Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier)
        QTest.qWait(40)
        selected=window._selected_ids()
        if selected != [e['id'] for e in view['history'][9996:10000]]:raise RuntimeError('Lost keyboard selection')
        # Recorded sink timestamps measure scheduler while JSON copies/encodes.
        class Sink:
            def __init__(self): self.messages=[]
            def send(self,msg):self.messages.append((time.perf_counter(),msg.copy()))
        sink=Sink()
        # Sink installation before worker dispatch is safe while idle; no MIDI opened.
        window.worker.close()
        from glittering_stars.playback import Worker
        window.controller.sink=sink
        window.worker=Worker(window.controller,on_view=window.bridge.updated.emit)
        window.worker.start()
        window.worker.command('loop',event_ids=selected)
        window.worker.command('play')
        target=Path(folder)/'capacity.gstars.json'
        began=time.perf_counter()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(save,target,window._view)
            deadline=time.monotonic()+60
            qt_ticks=0
            while not future.done() and time.monotonic()<deadline:
                window.timeline.verticalScrollBar().setValue(9990 if qt_ticks%2 else 0)
                app.processEvents();time.sleep(.005);qt_ticks+=1
            future.result(timeout=1)
        duration=time.perf_counter()-began
        window.worker.command('stop');QTest.qWait(40)
        ons=[(t,m) for t,m in sink.messages if m.type=='note_on']
        offs=[(t,m) for t,m in sink.messages if m.type=='note_off']
        # Stop can shorten the final hold; compare only fully completed groups.
        groups=min(len(ons)//3,len(offs)//3)
        errors=[abs(offs[i][0]-ons[i][0]-.03)*1000 for i in range(max(0,(groups-1)*3))]
        rng_unchanged=window._view['engine']==view['engine']
        history_unchanged=len(window._view['history'])==10000
        still_selected=window._selected_ids()==selected
        window.grab().save(str(ROOT/'docs/validation/capacity-window.png'))
        window.close();window._io_pool.shutdown(wait=True)
        began=time.perf_counter();restored=load(target);restore_time=time.perf_counter()-began
        report=dict(events=10000,generation_seconds=generation,render_scroll_seconds=render,
                    save_seconds=duration,load_seconds=restore_time,file_bytes=target.stat().st_size,
                    qt_event_pumps=qt_ticks,completed_chords=groups-1,
                    max_hold_error_ms=max(errors,default=None),rng_unchanged=rng_unchanged,
                    history_unchanged=history_unchanged,selection_retained=still_selected,
                    restored_events=len(restored['history']),native_qpa=app.platformName())
        report['pass']=all((render<2,rng_unchanged,history_unchanged,still_selected,
                            len(restored['history'])==10000, bool(errors),max(errors,default=999)<50))
        Path(args.report).write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
        return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
