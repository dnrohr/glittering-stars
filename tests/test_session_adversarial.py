"""Independent boundary cases for session durability and export inputs."""
import copy
import tempfile
import unittest
from pathlib import Path

from glittering_stars.domain import Engine
from glittering_stars.sessions import export_midi, validate_session
from tests.test_sessions import fixture


class SessionAdversarialTests(unittest.TestCase):
    def test_event_snapshot_must_describe_the_same_recorded_chord_and_key(self):
        session = fixture()
        session["history"][1]["voices"][0]["pitch"] += 1
        with self.assertRaises(ValueError):
            validate_session(session)

        session = fixture()
        session["history"][1]["key"] = (session["history"][1]["key"] + 1) % 12
        with self.assertRaises(ValueError):
            validate_session(session)

    def test_malformed_voice_and_cursor_are_rejected_as_schema_errors(self):
        session = fixture()
        session["history"][0]["voices"][0] = "not-a-voice-record"
        with self.assertRaises(ValueError):
            validate_session(session)

        session = fixture()
        session["cursor"] = -1
        with self.assertRaises(ValueError):
            validate_session(session)

    def test_active_branch_and_event_id_references_are_validated(self):
        session = fixture()
        session["active_branch"] = "missing"
        with self.assertRaises(ValueError):
            validate_session(session)

        session = fixture()
        session["history"][0]["id"] = ""
        with self.assertRaises(ValueError):
            validate_session(session)

    def test_export_rejects_invalid_direct_channel_and_key_inputs(self):
        events = fixture()["history"][:1]
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                export_midi(Path(folder) / "bad-channel.mid", events, channel=16)
            bad = copy.deepcopy(events)
            bad[0]["key"] = 99
            with self.assertRaises(ValueError):
                export_midi(Path(folder) / "bad-key.mid", bad)
            with self.assertRaises(ValueError):
                export_midi(Path(folder) / "bad-override.mid", events,
                            override={"hold": 1, "silence": 0, "velocity": 128})
            bad = copy.deepcopy(events)
            bad[0]["channel"] = True
            with self.assertRaises(ValueError):
                export_midi(Path(folder) / "bad-event-channel.mid", bad)

    def test_recorded_snapshots_remain_independently_resumable(self):
        session = fixture()
        for event in session["history"]:
            engine = Engine.restore(event["snapshot"])
            self.assertEqual(event["voices"], engine.snapshot()["voices"])
            self.assertEqual(event["key"], engine.snapshot()["key"])


if __name__ == "__main__":
    unittest.main()
