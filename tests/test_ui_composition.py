"""Widget-driven branch, audition, and MIDI export acceptance paths."""

import os
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from desktop import MainWindow, read_config


class DesktopCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.old_local = os.environ.get("LOCALAPPDATA")
        cls.data = tempfile.TemporaryDirectory(prefix="glittering-stars-composition-")
        os.environ["LOCALAPPDATA"] = cls.data.name

    @classmethod
    def tearDownClass(cls):
        if cls.old_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = cls.old_local
        cls.data.cleanup()

    def setUp(self):
        self.window = MainWindow(read_config(), preview=True)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window._io_pool.shutdown(wait=True, cancel_futures=False)
        self.app.processEvents()

    def until(self, predicate, timeout=5):
        end = time.monotonic() + timeout
        while time.monotonic() < end and not predicate():
            QTest.qWait(5)
        self.assertTrue(predicate(), self.window._view.get("error"))

    def generate_and_select(self):
        cfg = read_config()
        cfg = type(cfg).from_dict({**cfg.to_dict(), "hold": .005, "silence": 0, "chords": 3, "seed": 91})
        self.window.worker.command("new_phrase", config=cfg.to_dict())
        QTest.qWait(20)
        QTest.mouseClick(self.window.play_btn, Qt.MouseButton.LeftButton)
        self.until(lambda: len(self.window._view.get("history", [])) == 3
                   and self.window._view.get("phase") == "Paused")
        self.window.timeline.selectRow(0)
        QTest.qWait(20)
        self.assertEqual(len(self.window._selected_ids()), 1)

    def test_branch_actions_and_edit_dialog_use_real_worker(self):
        self.generate_and_select()
        def accept_recorded():
            dialog=QApplication.activeModalWidget()
            for button in dialog.buttons():
                if button.text()=='Recorded Settings':
                    button.click()
                    return
        QTimer.singleShot(0,accept_recorded)
        QTest.mouseClick(self.window.continue_btn, Qt.MouseButton.LeftButton)
        self.until(lambda: len(self.window._view.get("branches", [])) >= 2)
        self.window.worker.command("stop")
        self.until(lambda: self.window._view.get("phase") == "Idle")
        self.window.timeline.selectRow(0)
        QTest.qWait(10)
        before = len(self.window._view.get("branches", []))
        QTest.mouseClick(self.window.explore_btn, Qt.MouseButton.LeftButton)
        self.until(lambda: len(self.window._view.get("branches", [])) > before)
        self.window.worker.command("stop")
        self.until(lambda: self.window._view.get("phase") == "Idle")
        self.window.timeline.selectRow(0)
        QTest.qWait(10)
        before = len(self.window._view.get("branches", []))
        with patch("desktop.QDialog.exec", return_value=QDialog.DialogCode.Accepted):
            QTest.mouseClick(self.window.edit_btn, Qt.MouseButton.LeftButton)
        self.until(lambda: len(self.window._view.get("branches", [])) > before)

    def test_audition_and_selection_midi_export_buttons(self):
        self.generate_and_select()
        with patch.object(self.window.worker, "command", wraps=self.window.worker.command) as command:
            QTest.mouseClick(self.window.audition_btn, Qt.MouseButton.LeftButton)
            self.until(lambda: command.called)
            self.assertEqual(command.call_args.args[0], "audition")
        self.window.worker.command("stop")
        self.until(lambda: self.window._view.get("phase") == "Idle")
        self.window.timeline.selectRow(0)
        QTest.qWait(10)
        target = os.path.join(self.data.name, "selection.mid")
        with patch("desktop.QInputDialog.getInt", return_value=(2, True)), \
             patch("desktop.QFileDialog.getSaveFileName", return_value=(target, "MIDI")):
            QTest.mouseClick(self.window.export_btn, Qt.MouseButton.LeftButton)
            self.until(lambda: os.path.isfile(target) and 'export complete' in self.window.io_status.text().lower())
        self.assertGreater(os.path.getsize(target), 30)


if __name__ == "__main__":
    unittest.main()
