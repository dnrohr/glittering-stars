"""Real widget -> queued worker -> event/model acceptance checks."""
import copy
import os
import time
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop import MainWindow
from glittering_stars.domain import Config


class GUIAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.data_folder=tempfile.TemporaryDirectory()
        self.data_patch=patch.dict(os.environ,{'LOCALAPPDATA':self.data_folder.name})
        self.data_patch.start()
        self.window=MainWindow(Config(seed=123,hold=.01,silence=.01,chords=12),preview=True)
        self.window.show();QTest.qWait(30)

    def tearDown(self):
        self.window.close();self.app.processEvents()
        self.window._io_pool.shutdown(wait=True)
        self.data_patch.stop();self.data_folder.cleanup()

    def until(self,predicate,timeout=3):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline: QTest.qWait(5)
        self.assertTrue(predicate(),self.window._view.get('error'))

    def generated(self):
        QTest.mouseClick(self.window.play_btn,Qt.MouseButton.LeftButton)
        self.until(lambda:len(self.window._view.get('history',[]))==12 and self.window._view['phase']=='Paused')

    def test_regenerate_button_clears_timeline_and_displays_fresh_seed(self):
        self.generated()
        self.select_range()
        old_ids={e['id'] for e in self.window._view['history']}
        self.window.hold.setValue(1)
        self.window.gap.setValue(1)
        self.window.chords.setValue(1)
        with patch('secrets.randbits',return_value=777):
            QTest.mouseClick(self.window.regenerate_btn,Qt.MouseButton.LeftButton)
            self.until(lambda:self.window._view.get('config',{}).get('seed')==777)
        self.assertEqual(self.window.seed.text(),'777')
        self.assertEqual(self.window.timeline_model.rowCount(),1)
        self.assertEqual(self.window._selected_ids(),[])
        self.assertEqual(self.window._view['selection'],[])
        self.assertEqual(len(self.window._view['branches']),1)
        self.assertNotIn(self.window._view['history'][0]['id'],old_ids)
        self.assertEqual(self.window._view['config']['hold'],1)
        self.assertEqual(self.window._view['mode'],'generate')

    def select_range(self):
        table=self.window.timeline
        table.scrollTo(self.window.timeline_model.index(3,0))
        QTest.qWait(20)
        point=table.visualRect(self.window.timeline_model.index(3,1)).center()
        QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=point)
        QTest.keyClick(table,Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClick(table,Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClick(table,Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier)
        expected=[e['id'] for e in self.window._view['history'][3:7]]
        self.until(lambda:self.window._view.get('selection')==expected)
        return expected

    def test_keyboard_selection_loop_play_and_stop_leave_rng_history_unchanged(self):
        self.generated()
        expected=self.select_range()
        before=copy.deepcopy(self.window._view['engine'])
        QTest.keyClick(self.window.timeline,Qt.Key.Key_L,Qt.KeyboardModifier.ControlModifier)
        self.until(lambda:self.window._view.get('mode')=='loop')
        QTest.mouseClick(self.window.play_btn,Qt.MouseButton.LeftButton)
        self.until(lambda:self.window._view.get('phase')=='Holding')
        QTest.qWait(200)
        QTest.mouseClick(self.window.stop_btn,Qt.MouseButton.LeftButton)
        self.until(lambda:self.window._view.get('phase')=='Idle')
        self.assertEqual(self.window._view['mode'],'loop')
        self.assertEqual(self.window._view['playback_ids'],expected)
        self.assertEqual(self.window._view['engine'],before)
        self.assertEqual(len(self.window._view['history']),12)

    def test_queued_replay_then_immediate_play_keeps_worker_mode(self):
        self.generated()
        expected=self.select_range()
        history_size=len(self.window._view['history'])
        # Do not process the queued view publication between these two user actions.
        self.window._replay_selection()
        QTest.mouseClick(self.window.play_btn,Qt.MouseButton.LeftButton)
        self.until(lambda:self.window._view.get('mode')=='replay'
                   and self.window._view.get('phase') in ('Holding','Gap'))
        self.assertEqual(self.window._view.get('playback_ids'),expected)
        self.assertEqual(len(self.window._view.get('history',[])),history_size)
        QTest.mouseClick(self.window.stop_btn,Qt.MouseButton.LeftButton)
        self.until(lambda:self.window._view.get('phase')=='Idle')
        self.window._loop_selection()
        QTest.mouseClick(self.window.play_btn,Qt.MouseButton.LeftButton)
        self.until(lambda:self.window._view.get('mode')=='loop'
                   and self.window._view.get('phase') in ('Holding','Gap'))
        self.assertEqual(self.window._view.get('playback_ids'),expected)
        self.assertEqual(len(self.window._view.get('history',[])),history_size)

    def test_shift_selection_survives_new_history_event(self):
        self.generated()
        expected=self.select_range()
        # Explicit Generate command is distinct from Play/resume.
        command=self.window.worker.command('generate')
        self.until(lambda:len(self.window._view.get('history',[]))>=13)
        QTest.mouseClick(self.window.stop_btn,Qt.MouseButton.LeftButton)
        self.until(lambda:self.window._view.get('phase')=='Idle')
        self.assertEqual(self.window._view['selection'],expected)
        self.assertEqual(self.window._selected_ids(),expected)

    def test_invalid_weights_apply_is_atomic_real_button_path(self):
        self.generated()
        before=copy.deepcopy(self.window._view['config'])
        self.window.d_weights.setText('0,0,0')
        QTest.mouseClick(self.window.apply_btn,Qt.MouseButton.LeftButton)
        QTest.qWait(20)
        self.assertIn('Validation',self.window.status.text())
        self.assertEqual(self.window._view['config'],before)
        self.assertIsNone(self.window._view.get('pending_config'))

    def test_voice_lanes_follow_ids_after_crossing(self):
        model=self.window.timeline_model
        model.replace([dict(id='crossing',voices=[dict(id=0,pitch=67),dict(id=1,pitch=60),dict(id=2,pitch=72)],
                            key=0,hold=1,silence=1,decision=dict(status='moved'))])
        self.assertIn('G4',model.data(model.index(0,1)))
        self.assertIn('C4',model.data(model.index(0,2)))

    def test_inspector_survives_phase_updates_and_progress_uses_worker_deadline(self):
        self.generated()
        self.select_range()
        text=self.window.inspect.text()
        self.assertIn('Reason:',text)
        self.window.worker.command('pause')
        QTest.qWait(30)
        self.assertEqual(self.window.inspect.text(),text)
        cfg=self.window._view['config']|dict(hold=.6,silence=.4,chords=1)
        self.window.worker.command('new_phrase',config=cfg)
        self.until(lambda:self.window._view.get('phase')=='Idle')
        QTest.mouseClick(self.window.play_btn,Qt.MouseButton.LeftButton)
        self.until(lambda:self.window._view.get('phase')=='Holding')
        QTest.qWait(150)
        self.assertIn('remaining',self.window.phase_display.text())
        QTest.mouseClick(self.window.stop_btn,Qt.MouseButton.LeftButton)

    def test_policy_locks_and_invalid_weights_during_live_hold(self):
        cfg=self.window._config.to_dict()|dict(hold=.3,silence=.03,chords=0)
        self.window.worker.command('new_phrase',config=cfg)
        self.until(lambda:self.window._view.get('engine') is not None)
        QTest.mouseClick(self.window.play_btn,Qt.MouseButton.LeftButton)
        self.until(lambda:self.window._view.get('phase')=='Holding')
        first=copy.deepcopy(self.window._view['history'][0])
        self.window.d_weights.setText('0,0,0')
        QTest.mouseClick(self.window.apply_btn,Qt.MouseButton.LeftButton)
        self.assertIn('Validation',self.window.status.text())
        self.window.d_weights.setText('.1,.6,.3')
        self.window.policy.setCurrentIndex(self.window.policy.findData('off'))
        for lock in self.window.lock_checks:lock.setChecked(True)
        QTest.mouseClick(self.window.apply_btn,Qt.MouseButton.LeftButton)
        self.until(lambda:len(self.window._view['history'])>=2)
        event=self.window._view['history'][1]
        self.assertEqual(event['snapshot']['config']['policy'],'off')
        self.assertEqual(event['snapshot']['config']['locks'],[0,1,2])
        self.assertIn(event['decision']['status'],('repeat','blocked'))
        self.assertEqual(self.window._view['history'][0],first)
        QTest.mouseClick(self.window.stop_btn,Qt.MouseButton.LeftButton)

    def test_cleared_selection_cannot_silently_reuse_old_passage(self):
        self.generated()
        self.select_range()
        self.window.timeline.clearSelection()
        QTest.mouseClick(self.window.loop_btn,Qt.MouseButton.LeftButton)
        self.assertIn('Select a contiguous',self.window.status.text())
        self.assertEqual(self.window._view['mode'],'generate')

    def test_mouse_drag_selects_contiguous_passage(self):
        self.generated()
        table=self.window.timeline
        start=table.visualRect(self.window.timeline_model.index(3,1)).center()
        end=table.visualRect(self.window.timeline_model.index(6,1)).center()
        QTest.mousePress(table.viewport(),Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(table.viewport(),end,20)
        QTest.mouseRelease(table.viewport(),Qt.MouseButton.LeftButton,pos=end)
        expected=[e['id'] for e in self.window._view['history'][3:7]]
        self.until(lambda:self.window._view['selection']==expected)

    def test_old_worker_view_cannot_rollback_new_selection_gesture(self):
        self.generated()
        old=dict(self.window._view)
        table=self.window.timeline
        table.selectRow(3)
        QTest.keyClick(table,Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier)
        expected=[e['id'] for e in old['history'][3:5]]
        self.window._update_view(old)
        self.assertEqual(self.window._selected_ids(),expected)
        QTest.keyClick(table,Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier)
        QTest.keyClick(table,Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier)
        expected=[e['id'] for e in old['history'][3:7]]
        self.until(lambda:self.window._view['selection']==expected)
