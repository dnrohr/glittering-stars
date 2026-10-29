"""Independent transport acceptance cases."""
import copy
import os
import tempfile
import time
import unittest

from glittering_stars.domain import Config, KEY_NAMES
from glittering_stars.playback import Controller, Worker
from glittering_stars.sessions import validate_session

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop import MainWindow


class FakeClock:
    def __init__(self): self.now = 50.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class Sink:
    def __init__(self, clock):
        self.clock, self.messages, self.closed = clock, [], False
    def send(self, message): self.messages.append((self.clock(), message.copy()))
    def close(self): self.closed = True


class FailingSink(Sink):
    def __init__(self, clock):
        super().__init__(clock)
        self.disconnected = False
    def send(self, message):
        if self.disconnected: raise OSError("MIDI endpoint disconnected")
        super().send(message)


def messages(sink, kind):
    return [(t, m) for t, m in sink.messages if m.type == kind]


class TransportAdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make(self, **changes):
        clock = FakeClock()
        sink = Sink(clock)
        values = dict(low="C3", high="C5", hold=1, silence=2, seed=27,
                      diatonic_steps=(1,), diatonic_probabilities=(1,), channel=2)
        values.update(changes)
        config = Config(**values)
        return clock, sink, config, Controller(config, sink, clock)

    def test_stop_ack_cancels_old_play_intention_and_later_play_is_deliberate(self):
        clock = FakeClock()
        sink = Sink(clock)
        controller = Controller(Config(hold=30, silence=30, seed=5), sink, clock)
        worker = Worker(controller)
        worker.start()
        try:
            play_id = worker.command("play")
            stop_id = worker.command("stop")
            self.assertIn("Cancelled", worker.wait_ack(play_id, 2)["error"])
            self.assertTrue(worker.wait_ack(stop_id, 2)["ok"])
            on_count = len(messages(sink, "note_on"))
            self.assertEqual(controller.view()["phase"], "Idle")
            time.sleep(.03)
            self.assertEqual(len(messages(sink, "note_on")), on_count)
            deliberate = worker.command("play")
            self.assertTrue(worker.wait_ack(deliberate, 2)["ok"])
            self.assertEqual(len(messages(sink, "note_on")), on_count + 3)
            stopped = worker.command("stop")
            self.assertTrue(worker.wait_ack(stopped, 2)["ok"])
        finally:
            worker.close(timeout=2)

    def test_device_loss_during_hold_reports_error_without_escaping_scheduler(self):
        clock = FakeClock()
        sink = FailingSink(clock)
        controller = Controller(Config(hold=1, silence=2, seed=9), sink, clock)
        self.assertTrue(controller.command("play")["ok"])
        self.assertEqual(len(messages(sink, "note_on")), 3)
        sink.disconnected = True
        clock.advance(1)
        try:
            controller.tick()
        except OSError as exc:
            self.fail(f"device error escaped scheduler: {exc}")
        self.assertEqual(controller.view()["phase"], "Error")
        self.assertIsNone(controller.next_deadline)
        self.assertFalse(controller._active_notes)

    def test_channel_change_during_replay_rejects_and_releases_original_channel(self):
        clock, sink, config, controller = self.make()
        controller.command("play")
        event = copy.deepcopy(controller.view()["history"][0])
        controller.command("stop")
        controller.command("select", event_ids=[event["id"]])
        controller.command("loop", event_ids=[event["id"]])
        controller.command("play")
        self.assertEqual({m.channel for _, m in messages(sink, "note_on")}, {2})
        result = controller.command("config", config={**config.to_dict(), "channel": 5})
        self.assertFalse(result["ok"])
        controller.command("stop")
        self.assertEqual({m.channel for _, m in messages(sink, "note_off")}, {2})
        self.assertEqual(controller.view()["phase"], "Idle")

    def test_finite_count_stops_after_full_final_gap(self):
        clock, sink, config, controller = self.make(chords=2, hold=.2, silence=.4)
        controller.command("play")
        self.assertEqual(len(controller.view()["history"]), 1)
        clock.advance(.2); controller.tick()
        self.assertEqual(controller.view()["phase"], "Gap")
        self.assertEqual(controller.next_deadline, clock.now + .4)
        clock.advance(.4); controller.tick()
        self.assertEqual(len(controller.view()["history"]), 2)
        clock.advance(.2); controller.tick()
        self.assertEqual(controller.view()["phase"], "Gap")
        clock.advance(.4); controller.tick()
        self.assertEqual(controller.view()["phase"], "Paused")
        self.assertEqual(len(messages(sink, "note_on")), 6)
        self.assertIsNone(controller.next_deadline)

    def test_config_reseed_and_key_apply_before_next_snapshot(self):
        clock, sink, config, controller = self.make(hold=.2, silence=.4)
        controller.command("play")
        initial = copy.deepcopy(controller.view()["history"][0])
        changed = Config.from_dict({**config.to_dict(), "hold": .7, "silence": .8})
        self.assertTrue(controller.command("config", config=changed)["ok"])
        self.assertTrue(controller.command("reseed", seed=999)["ok"])
        self.assertTrue(controller.command("set_key", key="G")["ok"])
        clock.advance(.2); controller.tick()
        self.assertEqual(controller.next_deadline, clock.now + .4)
        clock.advance(.4); controller.tick()
        event = controller.view()["history"][1]
        self.assertEqual((event["key"], event["hold"], event["silence"]), (7, .7, .8))
        self.assertEqual((event["snapshot"]["effective_seed"], event["snapshot"]["key"]), (999, 7))
        self.assertEqual(event["revision"], 3)
        self.assertEqual(initial["key"], 0)

    def test_edit_continue_and_silent_load_preserve_parent_history(self):
        clock, sink, config, controller = self.make(hold=.2, silence=.4)
        controller.command("play")
        parent = copy.deepcopy(controller.view()["history"][0])
        controller.command("stop")
        edited = controller.command("edit", anchor_id=parent["id"], values={"key": 7, "hold": .3})
        self.assertTrue(edited["ok"])
        view = controller.view()
        child = next(e for e in view["history"] if e["id"] == edited["event_id"])
        self.assertEqual(view["history"][0], parent)
        self.assertEqual(child["branch_id"], view["active_branch"])
        self.assertEqual((child["snapshot"]["key"], child["hold"]), (7, .3))
        self.assertTrue(controller.command("continue", anchor_id=child["id"])["ok"])
        controller.command("play")
        self.assertEqual(len(controller.view()["history"]), 3)
        controller.command("stop")
        loaded = validate_session(controller.view())
        note_count = len(messages(sink, "note_on"))
        self.assertTrue(controller.command("load", session=loaded)["ok"])
        self.assertEqual(controller.view()["phase"], "Idle")
        self.assertEqual(controller.view()["history"], loaded["history"])
        self.assertEqual(len(messages(sink, "note_on")), note_count)

    def test_ten_thousand_event_view_is_bounded_and_complete(self):
        clock, sink, config, controller = self.make()
        controller.command("play")
        sample = copy.deepcopy(controller.view()["history"][0])
        controller._history = [dict(sample, id=f"fixture-{i}") for i in range(10_000)]
        started = time.perf_counter()
        view = controller.view()
        elapsed = time.perf_counter() - started
        self.assertEqual(len(view["history"]), 10_000)
        self.assertLess(elapsed, 2.0, f"10k history snapshot took {elapsed:.3f}s")

    def test_real_qt_keyboard_selection_and_loop_preserve_rng_and_history(self):
        old_local = os.environ.get("LOCALAPPDATA")
        isolated = tempfile.TemporaryDirectory(prefix="GlitteringStars-QA-")
        os.environ["LOCALAPPDATA"] = isolated.name
        config = Config(low="C3", high="C5", hold=.01, silence=.01, chords=16, seed=12345,
                        fourth_modulation_probability=1, seventh_modulation_probability=1)
        window = MainWindow(config, preview=True)
        window.show()

        def wait_for(condition, timeout=3):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                self.app.processEvents()
                if condition():
                    return
                time.sleep(.001)
            self.fail("Timed out waiting for Qt transport state")

        try:
            window.play_btn.click()
            wait_for(lambda: len(window._view.get("history", [])) == 16 and
                     window._view.get("phase") == "Paused", timeout=5)
            events = list(window._view["history"])
            expected = [event["id"] for event in events[3:7]]
            self.assertGreaterEqual(len({event["key"] for event in events[3:7]}), 2)
            target = window.timeline_model.index(3, 0)
            QTest.mouseClick(window.timeline.viewport(), Qt.MouseButton.LeftButton,
                             pos=window.timeline.visualRect(target).center())
            for _ in range(3):
                QTest.keyClick(window.timeline, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
                self.app.processEvents()
            self.app.processEvents()
            self.assertEqual(window._selected_ids(), expected)
            wait_for(lambda: window.controller.view()["selection"] == expected)
            engine_before = copy.deepcopy(window.controller.view()["engine"])
            count_before = len(window.controller.view()["history"])
            QTest.keyClick(window, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
            wait_for(lambda: window._view.get("mode") == "loop" and
                     window._view.get("playback_ids") == expected)
            window.play_btn.click()
            wait_for(lambda: window._view.get("phase") == "Holding" and
                     window._view.get("cursor") == 0 and
                     window._view.get("current_key") == events[3]["key"])
            self.assertEqual(window.key_display.text(),
                             f"Key: {KEY_NAMES[events[3]['key']]} major")
            for _ in range(3):
                wait_for(lambda: window._view.get("phase") == "Holding" and
                         window._view.get("cursor") == 3, timeout=2)
                wait_for(lambda: window._view.get("phase") == "Holding" and
                         window._view.get("cursor") == 0 and
                         window._view.get("current_key") == events[3]["key"], timeout=2)
            self.assertEqual(window.controller.view()["engine"], engine_before)
            self.assertEqual(len(window.controller.view()["history"]), count_before)
            self.assertEqual(window.timeline_model.playhead_id, expected[0])
            window.stop_btn.click()
            wait_for(lambda: window._view.get("phase") == "Idle")
        finally:
            window.close()
            window._io_pool.shutdown(wait=True, cancel_futures=False)
            self.app.processEvents()
            if old_local is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_local
            isolated.cleanup()


if __name__ == "__main__":
    unittest.main()
