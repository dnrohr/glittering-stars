"""Real Qt widget and model smoke tests for the desktop surface."""

import os
import tempfile
import time
import unittest
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from desktop import MainWindow, TimelineModel, read_config
from glittering_stars.sessions import load, load_preset


class DesktopWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls._old_local_app_data = os.environ.get("LOCALAPPDATA")
        cls._test_app_data = tempfile.TemporaryDirectory(prefix="glittering-stars-ui-")
        os.environ["LOCALAPPDATA"] = cls._test_app_data.name

    @classmethod
    def tearDownClass(cls):
        if cls._old_local_app_data is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = cls._old_local_app_data
        cls._test_app_data.cleanup()

    def setUp(self):
        self.window = MainWindow(read_config(), preview=True)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window._io_pool.shutdown(wait=True, cancel_futures=False)
        self.app.processEvents()

    def test_native_transport_controls_and_full_config_form_exist(self):
        self.assertEqual(self.window.windowTitle(), "Glittering Stars")
        self.assertEqual(self.window.play_btn.text(), "Play")
        self.assertEqual(self.window.generate_btn.text(), "Generate")
        self.assertEqual(self.window.timeline_model.columnCount(), 8)
        draft = self.window._read_draft()
        self.assertEqual(draft.low, "C3")
        self.assertEqual(draft.high, "C5")
        self.assertEqual(draft.diatonic_steps, (0, 1, 2))
        self.assertEqual(draft.diatonic_probabilities, (0.1, 0.6, 0.3))
        self.assertEqual(draft.locks, ())

    def test_invalid_draft_keeps_error_visible_without_dispatch(self):
        self.window.d_weights.setText("0,0,0")
        before = self.window._view.get("pending_config")
        self.window._apply_config()
        self.assertIn("Validation error", self.window.status.text())
        self.assertEqual(self.window._view.get("pending_config"), before)

    def test_timeline_model_shows_event_voices_and_key(self):
        model = TimelineModel()
        model.replace([{"id": "e1", "voices": [{"id": 0, "pitch": 48},
                                                    {"id": 1, "pitch": 64},
                                                    {"id": 2, "pitch": 67}],
                       "key": 0, "hold": 2, "silence": 4,
                       "decision": {"status": "initial"}}])
        self.assertEqual(model.rowCount(), 1)
        self.assertIn("C3", model.data(model.index(0, 1)))
        self.assertEqual(model.data(model.index(0, 4)), "C major")
        model.replace(model.events + [{"id": "e2", "voices": model.events[0]["voices"],
                                       "key": 7, "hold": 2, "silence": 4,
                                       "decision": {"status": "moved"}}])
        self.assertEqual(model.rowCount(), 2)
        self.assertEqual(model.event_id(1), "e2")

    def _until(self, predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(5)
        self.assertTrue(predicate(), self.window._view.get("error"))

    def test_session_buttons_save_and_restore_a_real_worker_history(self):
        cfg = replace(read_config(), hold=.005, silence=0, chords=3, seed=101)
        self.window.worker.command("new_phrase", config=cfg.to_dict())
        QTest.qWait(30)
        QTest.mouseClick(self.window.play_btn, Qt.MouseButton.LeftButton)
        self._until(lambda: len(self.window._view.get("history", [])) == 3 and self.window._view.get("phase") == "Paused")
        expected = [event["id"] for event in self.window._view["history"]]
        session_path = os.path.join(self._test_app_data.name, "roundtrip.gstars.json")
        with patch("desktop.QFileDialog.getSaveFileName", return_value=(session_path, "")):
            QTest.mouseClick(self.window.save_btn, Qt.MouseButton.LeftButton)
            self._until(lambda: os.path.isfile(session_path))
        self.assertEqual([event["id"] for event in load(session_path)["history"]], expected)
        self.window.worker.command("stop")
        QTest.qWait(30)
        self.window.worker.command('next',mode='generate')
        self._until(lambda:len(self.window._view.get('history',[]))==4 and self.window._view.get('phase')=='Paused')
        with patch("desktop.QFileDialog.getOpenFileName", return_value=(session_path, "")):
            QTest.mouseClick(self.window.open_btn, Qt.MouseButton.LeftButton)
            self._until(lambda: [event["id"] for event in self.window._view.get("history", [])] == expected
                        and self.window._view.get("phase") == "Idle")
        self.assertEqual(self.window._view.get("phase"), "Idle")
        self.assertNotIn('Loading',self.window.status.text())

    def test_preset_buttons_roundtrip_configuration(self):
        self.window.hold.setValue(1.25)
        preset_path = os.path.join(self._test_app_data.name, "roundtrip.gstarspreset.json")
        with patch("desktop.QFileDialog.getSaveFileName", return_value=(preset_path, "")):
            QTest.mouseClick(self.window.save_preset_btn, Qt.MouseButton.LeftButton)
            self._until(lambda: os.path.isfile(preset_path))
        saved = load_preset(preset_path)
        self.assertEqual(saved.hold, 1.25)
        self.window.hold.setValue(3.5)
        with patch("desktop.QFileDialog.getOpenFileName", return_value=(preset_path, "")):
            QTest.mouseClick(self.window.load_preset_btn, Qt.MouseButton.LeftButton)
            self._until(lambda: self.window.hold.value() == 1.25)


if __name__ == "__main__":
    unittest.main()
