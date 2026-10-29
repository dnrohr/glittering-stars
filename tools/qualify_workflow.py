"""One native Qt session: generate/select/loop/replace/branch/edit/save/open/export."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import mido
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox,QDialog,QPushButton
from desktop import MainWindow
from glittering_stars.domain import Config
from glittering_stars.sessions import load


def main():
    with tempfile.TemporaryDirectory() as folder:
        os.environ['LOCALAPPDATA']=folder
        app=QApplication([])
        window=MainWindow(Config(seed=123,hold=.01,silence=.02,chords=12),preview=True)
        window.show()
        steps=[]
        def until(predicate):
            end=time.monotonic()+5
            while time.monotonic()<end:
                app.processEvents();time.sleep(.002)
                if predicate():return
            raise AssertionError(window._view.get('error') or 'Workflow deadline expired')
        def click(button):QTest.mouseClick(button,Qt.MouseButton.LeftButton)
        def select(first,last):
            table=window.timeline
            table.scrollTo(window.timeline_model.index(first,1));app.processEvents()
            QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=table.visualRect(window.timeline_model.index(first,1)).center())
            for _ in range(last-first):
                QTest.keyClick(table,Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier);app.processEvents()
            until(lambda:len(window._view['selection'])==last-first+1)
        try:
            click(window.generate_btn)
            until(lambda:window._view.get('phase')=='Holding')
            window.hold.setValue(.02);window.velocity.setValue(60);click(window.apply_btn)
            until(lambda:len(window._view.get('history',[]))==12 and window._view['phase']=='Paused')
            assert window._view['history'][-1]['hold']==.02 and window._view['history'][-1]['velocity']==60
            steps.append('Generate12 / live timing and velocity revision during hold')
            original=list(window._view['history']);engine=window._view['engine']
            select(3,6);click(window.loop_btn)
            until(lambda:window._view['mode']=='loop');click(window.play_btn)
            until(lambda:window._view['phase']=='Holding');QTest.qWait(180)
            select(4,5);until(lambda:len(window._view['playback_ids'])==2)
            click(window.pause_btn);until(lambda:window._view['phase']=='Paused')
            click(window.next_btn);until(lambda:window._view['phase']=='Holding');until(lambda:window._view['phase']=='Paused')
            click(window.loop_off_btn);until(lambda:window._view['mode']=='replay')
            click(window.stop_btn);until(lambda:window._view['phase']=='Idle')
            assert window._view['engine']==engine and window._view['history']==original
            steps.append('Select4-7/Loop/replace/Pause/Next/LoopOff/Stop isolated')
            select(3,3)
            window.content_tabs.setCurrentIndex(1)
            def choose_recorded():
                dialog=QApplication.activeModalWidget()
                next(b for b in dialog.buttons() if b.text()=='Recorded Settings').click()
            QTimer.singleShot(0,choose_recorded);click(window.continue_btn)
            until(lambda:len(window._view['branches'])==2)
            click(window.next_btn);until(lambda:len(window._view['history'])==13 and window._view['phase']=='Paused')
            window.content_tabs.setCurrentIndex(0);select(12,12);window.content_tabs.setCurrentIndex(1)
            def create_edit():
                dialog=QApplication.activeModalWidget()
                next(b for b in dialog.findChildren(QPushButton) if b.text()=='Create variation').click()
            QTimer.singleShot(0,create_edit);click(window.edit_btn)
            until(lambda:len(window._view['history'])==14)
            assert window._view['history'][:12]==original
            steps.append('Continue child / edit explicit child preserves parent')
            click(window.audition_btn);until(lambda:window._view['phase']=='Holding');until(lambda:window._view['phase']=='Paused')
            session=Path(folder)/'workflow.json';midi=Path(folder)/'workflow.mid'
            with patch('desktop.QFileDialog.getSaveFileName',return_value=(str(session),'')):
                click(window.save_btn);until(session.exists)
            saved=load(session)
            click(window.next_btn);until(lambda:len(window._view['history'])==15 and window._view['phase']=='Paused')
            with patch('desktop.QFileDialog.getOpenFileName',return_value=(str(session),'')):
                click(window.open_btn);until(lambda:len(window._view['history'])==14 and window._view['phase']=='Idle')
            assert window._view['history']==saved['history'] and window._view['engine']==saved['engine']
            steps.append('Audition / named Save/Open exact and silent')
            with patch('desktop.QInputDialog.getInt',return_value=(2,True)),patch('desktop.QFileDialog.getSaveFileName',return_value=(str(midi),'')):
                click(window.export_btn);until(midi.exists)
            parsed=mido.MidiFile(midi)
            notes=[m.note for m in parsed.tracks[0] if m.type=='note_on']
            selected=next(e for e in saved['history'] if e['id']==saved['selection'][0])
            assert notes==[v['pitch'] for v in selected['voices']]*2
            assert abs(parsed.length-2*(selected['hold']+selected['silence']))<.003
            steps.append('Stored selection MIDI two passes including final gap parsed equal')
            window.grab().save(str(ROOT/'docs/validation/workflow-window.png'))
            report=dict(pass_=True,native_qpa=app.platformName(),steps=steps,history_events=14,branches=len(saved['branches']),midi_notes=notes)
            (ROOT/'docs/validation/workflow.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2))
        finally:
            window.close();window._io_pool.shutdown(wait=True)


if __name__=='__main__':main()
