import copy
import unittest
import threading
import time

import mido
from unittest.mock import patch

from glittering_stars.domain import Config
from glittering_stars.playback import Controller, Worker


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Sink:
    def __init__(self, clock):
        self.clock = clock
        self.messages = []
        self.closed = False

    def send(self, message):
        self.messages.append((self.clock(), message.copy()))

    def close(self):
        self.closed = True


def chord_messages(sink, kind):
    return [message for _, message in sink.messages if message.type == kind]


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sink = Sink(self.clock)
        self.config = Config(low="C3", high="C5", hold=1, silence=2, chords=0,
                             seed=123, diatonic_steps=(0,), diatonic_probabilities=(1,), channel=2)
        self.controller = Controller(self.config, self.sink, self.clock)

    def boundary(self):
        self.clock.advance(1)
        self.controller.tick()
        self.clock.advance(2)
        self.controller.tick()

    def test_regenerate_reseeds_clears_branches_and_releases_active_loop(self):
        self.controller.command('play')
        self.boundary()
        self.controller.command('stop')
        old=self.controller.view()
        anchor=old['history'][0]['id']
        self.controller.command('continue',anchor_id=anchor)
        self.controller.command('next')
        self.boundary()
        self.controller.command('loop',event_ids=[anchor])
        self.controller.command('play')
        old_seed=old['engine']['effective_seed']
        self.controller.command('set_key',key='G')
        self.controller.command('reseed',seed=999)
        start=len(self.sink.messages)
        with patch('secrets.randbits',return_value=777):
            reply=self.controller.command('regenerate')
        self.assertTrue(reply['ok'],reply)
        view=self.controller.view()
        self.assertEqual(view['engine']['effective_seed'],777)
        self.assertNotEqual(view['engine']['effective_seed'],old_seed)
        self.assertEqual(view['config']['seed'],777)
        self.assertEqual(len(view['history']),1)
        self.assertEqual(view['history'][0]['decision']['status'],'initial')
        self.assertNotIn(view['history'][0]['id'],[e['id'] for e in old['history']])
        self.assertEqual(len(view['branches']),1)
        self.assertEqual(view['selection'],[])
        self.assertEqual(view['playback_ids'],[])
        self.assertIsNone(view['pending_key'])
        self.assertIsNone(view['pending_reseed'])
        self.assertEqual(view['context_log'],[])
        self.assertEqual((view['mode'],view['phase']),('generate','Holding'))
        self.assertEqual(view['output_channel'],self.config.channel)
        self.assertIs(self.controller.sink,self.sink)
        self.assertFalse(self.sink.closed)
        messages=[m for _,m in self.sink.messages[start:]]
        self.assertEqual([m.type for m in messages],['note_off']*3+['note_on']*3)
        self.assertFalse(any(m.type=='control_change' and m.control==120 for m in messages))

    def test_invalid_regenerate_keeps_existing_history_and_engine(self):
        self.controller.command('play')
        old=copy.deepcopy(self.controller.view())
        invalid=self.config.to_dict()|dict(low='C4',high='F#4')
        result=self.controller.command('regenerate',config=invalid)
        self.assertFalse(result['ok'])
        new=self.controller.view()
        for key in ('history','engine','branches','config','phase'):
            self.assertEqual(new[key],old[key])

    def test_stop_cancels_queued_regenerate(self):
        worker=Worker(self.controller)
        regeneration=worker.command('regenerate')
        stopped=worker.command('stop')
        worker.start()
        try:
            self.assertTrue(worker.wait_ack(stopped,2)['ok'])
            self.assertFalse(worker.wait_ack(regeneration,2)['ok'])
            self.assertEqual(self.controller.view()['history'],[])
            self.assertEqual(chord_messages(self.sink,'note_on'),[])
        finally:
            worker.close()

    def test_generation_pause_next_stop_and_panic_cleanup(self):
        self.controller.command("play")
        self.assertEqual(self.controller.view()["phase"], "Holding")
        ons = chord_messages(self.sink, "note_on")
        self.assertEqual(len(ons), 3)
        self.assertEqual({m.channel for m in ons}, {2})
        self.controller.command("pause")
        self.boundary()
        self.assertEqual(self.controller.view()["phase"], "Paused")
        self.controller.command("next")
        self.assertEqual(len(chord_messages(self.sink, "note_on")), 6)
        self.controller.command("stop")
        self.assertEqual(self.controller.view()["phase"], "Idle")
        self.assertEqual(len(chord_messages(self.sink, "note_off")), 6)
        self.assertFalse(any(m.type == "control_change" and m.control in (120, 123)
                             for _, m in self.sink.messages))
        self.controller.command("play")
        self.controller.command("panic")
        controls = [m.control for _, m in self.sink.messages if m.type == "control_change"]
        self.assertEqual(controls[-3:], [64, 123, 120])
        sustain_index = next(i for i, (_, m) in enumerate(self.sink.messages)
                             if m.type == "control_change" and m.control == 64)
        noteoff_indexes = [i for i, (_, m) in enumerate(self.sink.messages)
                           if i > sustain_index and m.type == "note_off"]
        reset_indexes = [i for i, (_, m) in enumerate(self.sink.messages)
                         if m.type == "control_change" and m.control in (123, 120)]
        self.assertLess(sustain_index, min(noteoff_indexes))
        self.assertLess(max(noteoff_indexes), min(reset_indexes))

    def test_idle_replay_uses_new_output_channel_without_mutating_history_or_engine(self):
        self.controller.command("play")
        self.controller.command("stop")
        before = self.controller.view()
        event = before["history"][0]
        changed = Config.from_dict({**self.config.to_dict(), "channel": 7})
        self.assertTrue(self.controller.command("config", config=changed.to_dict())["ok"])
        self.assertEqual(self.controller.view()["output_channel"], 7)
        self.controller.command("replay", event_ids=[event["id"]])
        self.controller.command("play")
        replay_ons = chord_messages(self.sink, "note_on")[-3:]
        self.assertEqual({m.channel for m in replay_ons}, {7})
        after = self.controller.view()
        self.assertEqual(after["engine"], before["engine"])
        self.assertEqual(after["history"][0]["channel"], 2)
        self.assertEqual(after["history"][0], event)

    def test_late_hold_does_not_shorten_full_gap_and_stop_interrupts(self):
        self.controller.command("play")
        self.clock.advance(9)
        self.controller.tick()
        self.assertEqual(self.controller.view()["phase"], "Gap")
        self.assertEqual(self.controller.next_deadline, self.clock.now + 2)
        self.controller.command("stop")
        self.clock.advance(30)
        self.controller.tick()
        self.assertEqual(len(chord_messages(self.sink, "note_on")), 3)
        self.assertFalse(self.controller.view()["history"][-1].get("active", False))

    def test_loop_freezes_events_and_never_advances_generator(self):
        self.controller.command("play")
        for _ in range(2):
            self.boundary()
        view = self.controller.view()
        ids = [e["id"] for e in view["history"][:2]]
        self.assertEqual(len(ids), 2)
        self.controller.command("select", event_ids=ids)
        before = copy.deepcopy(self.controller.view()["engine"])
        event_count = len(self.controller.view()["history"])
        self.controller.command("loop", event_ids=ids)
        # Let the currently sounding generated event and full gap finish.
        self.boundary()
        self.assertEqual(self.controller.view()["mode"], "loop")
        expected = [tuple(v["pitch"] for v in e["voices"]) for e in view["history"][:2]]
        # The first loop chord has started. Run through multiple full cycles.
        for _ in range(12):
            self.boundary()
        after = self.controller.view()
        self.assertEqual(after["engine"], before)
        self.assertEqual(len(after["history"]), event_count)
        loop_onsets = chord_messages(self.sink, "note_on")[9:]
        actual = [tuple(m.note for m in loop_onsets[i:i+3]) for i in range(0, len(loop_onsets), 3)]
        self.assertTrue(actual)
        self.assertEqual(actual[:4], expected * 2)
        # Every onset pair has a complete hold plus the configured gap,
        # including the wrap from the last selected event to the first.
        on_times = [t for t, m in self.sink.messages if m.type == "note_on"]
        chord_times = on_times[::3]
        self.assertTrue(all(b - a >= 3 for a, b in zip(chord_times[-len(actual)-1:], chord_times[-len(actual):])))

    def test_invalid_or_noncontiguous_selection_leaves_loop_unchanged(self):
        self.controller.command("play")
        for _ in range(2):
            self.boundary()
        ids = [e["id"] for e in self.controller.view()["history"]]
        self.controller.command("select", event_ids=ids)
        before = self.controller.view()["selection"]
        result = self.controller.command("select", event_ids=[ids[0], ids[-1]])
        self.assertFalse(result["ok"])
        self.assertEqual(self.controller.view()["selection"], before)

    def test_invalid_config_is_rejected_without_pending_revision(self):
        result = self.controller.command("config", config={**self.config.to_dict(),
                                                              "diatonic_probabilities": [0]})
        self.assertFalse(result["ok"])
        self.assertIsNone(self.controller.view()["pending_config"])

    def test_selection_replacement_during_gap_restarts_at_first_new_event(self):
        self.controller.command("play")
        for _ in range(3):
            self.boundary()
        history = self.controller.view()["history"]
        first = [e["id"] for e in history[:2]]
        replacement = [e["id"] for e in history[1:3]]
        self.controller.command("loop", event_ids=first)
        self.boundary()  # current generated event completes and first loop event starts
        # Current loop event is now sounding. Queue a new contiguous range.
        result = self.controller.command("select", event_ids=replacement)
        self.assertTrue(result["ok"])
        self.boundary()  # current event and its full gap, then replacement starts
        ons = chord_messages(self.sink, "note_on")
        # Four generated events and one old loop event precede replacement.
        self.assertEqual(tuple(m.note for m in ons[15:18]),
                         tuple(v["pitch"] for v in history[1]["voices"]))
        self.assertEqual(self.controller.view()["cursor"], 0)

    def test_timing_override_does_not_rewrite_history(self):
        self.controller.command("play")
        event = copy.deepcopy(self.controller.view()["history"][0])
        draft = Config.from_dict({**self.config.to_dict(), "hold": 5, "silence": 7, "velocity": 99})
        self.controller.command("config", config=draft)
        self.controller.command("override", enabled=True)
        # The already-started event keeps its onset timing; the next loop pass
        # uses the explicit override without changing its saved record.
        self.controller.command("select", event_ids=[event["id"]])
        self.controller.command("loop", event_ids=[event["id"]])
        self.boundary()
        self.assertEqual(self.controller.view()["history"][0], event)
        self.assertEqual(self.controller.view()["phase"], "Holding")
        self.assertEqual(self.controller.next_deadline, self.clock.now + 5)

    def test_worker_acknowledges_commands_and_closes_cleanly(self):
        worker = Worker(self.controller)
        worker.start()
        sequence = worker.command("play")
        ack = worker.wait_ack(sequence, timeout=1)
        self.assertIsNotNone(ack)
        self.assertTrue(ack["ok"])
        stopped = worker.command("stop")
        self.assertTrue(worker.wait_ack(stopped, timeout=1)["ok"])
        worker.close(timeout=2)
        self.assertFalse(worker._thread.is_alive())
        self.assertTrue(self.sink.closed)

    def test_invalid_draft_does_not_interrupt_existing_event(self):
        self.controller.command("play")
        result = self.controller.command("config", config={**self.config.to_dict(), "velocity": 0})
        self.assertFalse(result["ok"])
        self.assertEqual(self.controller.view()["phase"], "Holding")
        self.assertIsNone(self.controller.view()["pending_config"])

    def test_finite_run_stops_after_final_full_gap(self):
        config = Config.from_dict({**self.config.to_dict(), "chords": 1})
        controller = Controller(config, self.sink, self.clock)
        controller.command("play")
        self.assertEqual(len(controller.view()["history"]), 1)
        self.clock.advance(1)
        controller.tick()
        self.assertEqual(controller.view()["phase"], "Gap")
        self.clock.advance(1.99)
        controller.tick()
        self.assertEqual(controller.view()["phase"], "Gap")
        self.clock.advance(0.01)
        controller.tick()
        self.assertEqual(controller.view()["phase"], "Paused")
        controller.command("play")
        self.assertEqual(len(controller.view()["history"]), 2)

    def test_set_key_is_queued_until_generation_resumes(self):
        self.controller.command("play")
        snapshot = copy.deepcopy(self.controller.view()["engine"])
        result = self.controller.command("set_key", key="G")
        self.assertTrue(result["ok"])
        self.assertEqual(self.controller.view()["engine"], snapshot)
        self.controller.command("stop")
        self.controller.command("play")
        self.assertEqual(self.controller.view()["history"][-1]["key"], 7)

    def test_audition_isolated_from_history_rng_and_previous_mode(self):
        self.controller.command("play")
        self.boundary()
        self.controller.command("stop")
        before = self.controller.view()
        event_id = before["history"][0]["id"]
        result = self.controller.command("audition", event_id=event_id)
        self.assertTrue(result["ok"])
        self.boundary()
        after = self.controller.view()
        self.assertEqual(after["engine"], before["engine"])
        self.assertEqual(len(after["history"]), len(before["history"]))
        self.assertEqual(after["mode"], "generate")
        self.assertEqual(after["phase"], "Paused")

    def test_branch_switch_restores_terminal_snapshot_without_deleting_events(self):
        self.controller.command("play")
        self.boundary()
        first = self.controller.view()["history"][0]
        self.controller.command("stop")
        self.controller.command("continue", anchor_id=first["id"])
        branch_view = self.controller.view()
        child_branch = branch_view["active_branch"]
        self.controller.command("next")
        child_event = self.controller.view()["history"][-1]
        self.controller.command("stop")
        self.controller.command("branch", branch_id="main")
        main = self.controller.view()
        self.assertEqual(main["active_branch"], "main")
        second_main = next(event for event in main["history"] if event["branch_id"] == "main" and event["id"] != first["id"])
        self.assertEqual(main["engine"]["voices"], second_main["snapshot"]["voices"])
        self.assertEqual(len(main["history"]), 3)
        self.assertNotEqual(child_branch, "main")
        self.assertEqual(child_event["branch_id"], child_branch)

    def test_impossible_new_phrase_is_transactional(self):
        self.controller.command("play")
        before = self.controller.view()
        active_notes = dict(self.controller._active_notes)
        impossible = {**self.config.to_dict(), "low": "C4", "high": "F#4"}
        result = self.controller.command("new_phrase", config=impossible)
        self.assertFalse(result["ok"])
        after = self.controller.view()
        self.assertEqual(after["engine"], before["engine"])
        self.assertEqual(after["config"], before["config"])
        self.assertEqual(after["history"], before["history"])
        self.assertEqual(after["phase"], before["phase"])
        self.assertEqual(self.controller._active_notes, active_notes)

    def test_session_load_detaches_real_midi_sink(self):
        class Port:
            def __init__(self):
                self.closed = False
            def send(self, message):
                pass
            def close(self):
                self.closed = True

        port = Port()
        from glittering_stars.playback.controller import MidiSink
        loaded_config = Config.from_dict({**self.config.to_dict(), "port": "saved-port"})
        with patch("glittering_stars.playback.controller.mido.open_output", return_value=port):
            real_sink = MidiSink("saved-port")
        controller = Controller(loaded_config, real_sink, self.clock)
        snapshot = controller.view()
        result = controller.command("load", session=snapshot)
        self.assertTrue(result["ok"])
        self.assertTrue(port.closed)
        self.assertIsNone(controller.sink)
        self.assertFalse(controller.view()["connected"])
        self.assertEqual(controller.view()["config"]["port"], "saved-port")

    def test_failed_connect_keeps_existing_sink_open(self):
        with patch("glittering_stars.playback.controller.mido.get_output_names", return_value=[]):
            result = self.controller.command("connect", port="missing")
        self.assertFalse(result["ok"])
        self.assertIs(self.controller.sink, self.sink)
        self.assertFalse(self.sink.closed)


if __name__ == "__main__":
    unittest.main()
