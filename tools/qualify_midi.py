"""Finite loopMIDI -> Surge receipt/timing qualification using the real Qt window.

Safe by default: --list-ports only inventories devices. The finite audio/MIDI
run requires --run and explicit exact input/output port names. This script
measures MIDI receipt only; it cannot establish that audio was heard.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter, deque
from datetime import datetime, timezone
import json
import os
import platform
import queue
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import mido
from PySide6.QtCore import QTimer
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desktop import MainWindow
from glittering_stars.domain import Config, KEY_NAMES


def percentile(values, percent):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percent / 100
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def summary_ms(seconds):
    values = [abs(float(value)) * 1000 for value in seconds]
    return {
        "samples": len(values),
        "p50_ms": round(percentile(values, 50), 3) if values else None,
        "p95_ms": round(percentile(values, 95), 3) if values else None,
        "max_ms": round(max(values), 3) if values else None,
    }


def exact_port(requested, available, kind):
    if requested not in available:
        raise SystemExit(f"{kind} port {requested!r} not found exactly. Available: {available}")
    return requested


def wait_with_qt(app, condition, timeout, description):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(.002)
    raise TimeoutError(f"Timed out waiting for {description}")


def receipt_callback(destination):
    def callback(*args):
        message = args[0]
        if isinstance(message, tuple):
            message = message[0]
        if isinstance(message, mido.Message):
            destination.put((time.perf_counter(), message.copy()))
    return callback


def pump_messages(app, inbox, collected):
    app.processEvents()
    while True:
        try:
            collected.append(inbox.get_nowait())
        except queue.Empty:
            return


def raw_capture(received, origin):
    result = []
    for stamp, message in received:
        item = {"time_seconds": round(stamp - origin, 6), "type": message.type}
        for field in ("channel", "note", "velocity", "control", "value"):
            if hasattr(message, field):
                item[field] = getattr(message, field)
        result.append(item)
    return result


def write_report(path, report):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")


def run(args):
    outputs = mido.get_output_names()
    inputs = mido.get_input_names()
    output_name = exact_port(args.output, outputs, "MIDI output")
    input_name = exact_port(args.input or args.output, inputs, "MIDI input")
    print(f"Opening exact loopMIDI output {output_name!r} and receive port {input_name!r}.")
    print("The app window will be visible. Stop/Panic trials are finite; no audio is heard by this script.")

    inbox = queue.Queue()
    received = []
    capture_origin = time.perf_counter()
    input_port = mido.open_input(input_name, callback=receipt_callback(inbox))
    previous_local_data = os.environ.get("LOCALAPPDATA")
    isolated_data = tempfile.TemporaryDirectory(prefix="GlitteringStars-qualification-")
    os.environ["LOCALAPPDATA"] = isolated_data.name
    app = QApplication.instance() or QApplication([sys.argv[0]])
    config = Config(port=output_name, low="C3", high="C5", hold=.03, silence=.03,
                    chords=args.events, seed=args.seed, velocity=args.velocity,
                    fourth_modulation_probability=1.0, seventh_modulation_probability=1.0)
    window = MainWindow(config, preview=False)
    window.port.setCurrentText(output_name)
    window._load_controls(config)
    timer_count = [0]
    ui_timer = QTimer(window)
    ui_timer.setInterval(16)
    ui_timer.timeout.connect(lambda: timer_count.__setitem__(0, timer_count[0] + 1))
    ui_timer.start()
    window.show()
    report = {"label": "IN_PROGRESS"}

    try:
        window.connect_btn.click()
        wait_with_qt(app, lambda: bool(window._view.get("connected")), 10, "MIDI connection")
        start_index = len(received)
        # Polling drains the callback queue while the actual main window and its
        # normal 16 ms Qt timer continue to run.
        window.play_btn.click()
        end_by = time.monotonic() + args.events * .06 + 20
        while time.monotonic() < end_by:
            pump_messages(app, inbox, received)
            if (len(window._view.get("history", [])) >= args.events and
                    window._view.get("phase") == "Paused"):
                break
            time.sleep(.002)
        else:
            raise TimeoutError("Finite generation did not finish within its bounded deadline")
        pump_messages(app, inbox, received)
        generated = received[start_index:]
        ons = [(stamp, msg) for stamp, msg in generated
               if msg.type == "note_on" and msg.velocity > 0]
        offs = [(stamp, msg) for stamp, msg in generated
                if msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0)]
        expected_count = args.events * 3
        report.update({
            "revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                      capture_output=True, text=True).stdout.strip(),
            "environment": {"platform": platform.platform(), "python": sys.version,
                            "qt": __import__("PySide6").__version__,
                            "mido": getattr(mido, "__version__", "unknown"),
                            "timestamp_utc": datetime.now(timezone.utc).isoformat()},
            "route": {"output": output_name, "input": input_name, "events": args.events,
                      "hold_seconds": .03, "gap_seconds": .03, "velocity": args.velocity},
            "observed": {"history_events": len(window._view.get("history", [])),
                         "note_on_count": len(ons), "note_off_count": len(offs),
                         "qt_timer_ticks": timer_count[0], "audio_heard": False,
                         "app_data_isolated": True},
            "generated_history": [{
                "id": event["id"], "branch_id": event["branch_id"],
                "voices": [{"id": voice["id"], "pitch": voice["pitch"]} for voice in event["voices"]],
                "key": event["key"], "hold": event["hold"], "silence": event["silence"],
                "velocity": event["velocity"], "channel": event["channel"], "revision": event["revision"],
            } for event in window._view.get("history", [])],
            "midi_receipt_capture": raw_capture(received, capture_origin),
        })
        if len(ons) != expected_count or len(offs) != expected_count:
            raise RuntimeError(f"Expected {expected_count} note-ons and offs; received {len(ons)} and {len(offs)}")

        cleanup_config = Config.from_dict({**config.to_dict(), "hold": 5.0, "silence": .03, "chords": 0})
        config_sequence = window.worker.command("config", config=cleanup_config.to_dict())
        config_ack = window.worker.wait_ack(config_sequence, timeout=2)
        if not config_ack or not config_ack.get("ok"):
            raise RuntimeError(f"Could not stage long-hold cleanup trials: {config_ack}")

        on_groups = [ons[i:i + 3] for i in range(0, len(ons), 3)]
        off_queues = {}
        for stamp, msg in offs:
            off_queues.setdefault((msg.channel, msg.note), deque()).append(stamp)
        duration_errors = []
        final_offs = []
        for group in on_groups:
            group_offs = []
            for stamp, msg in group:
                times = off_queues.get((msg.channel, msg.note))
                if not times:
                    raise RuntimeError(f"Missing note-off for MIDI note {msg.note}")
                off_at = times.popleft()
                duration_errors.append(off_at - stamp - .03)
                group_offs.append(off_at)
            final_offs.append(max(group_offs))
        spreads = [max(stamp for stamp, _ in group) - min(stamp for stamp, _ in group)
                   for group in on_groups]
        gaps = [on_groups[index + 1][0][0] - final_offs[index]
                for index in range(len(on_groups) - 1)]
        gap_errors = [gap - .03 for gap in gaps]
        report["timing"] = {
            "note_on_spread": summary_ms(spreads),
            "hold_absolute_error": summary_ms(duration_errors),
            "gap_absolute_error": summary_ms(gap_errors),
        }
        if any(off_queues.values()):
            raise RuntimeError("Unmatched note-offs remained after matching generated chords")

        # Exercise selection through the visible timeline: click event 4, extend
        # with Shift+Down to event 7, and invoke the real Ctrl+L shortcut.
        history_records = list(window._view.get("history", []))
        selected_events = history_records[3:7]
        if len(selected_events) != 4:
            raise RuntimeError("The generated history does not contain events 4 through 7")
        window.timeline.setFocus()
        target = window.timeline_model.index(3, 0)
        QTest.mouseClick(window.timeline.viewport(), Qt.MouseButton.LeftButton,
                         pos=window.timeline.visualRect(target).center())
        app.processEvents()
        for _ in range(3):
            QTest.keyClick(window.timeline, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
            app.processEvents()
        selected_ids = [event["id"] for event in selected_events]
        if window._selected_ids() != selected_ids:
            raise RuntimeError(f"Qt keyboard selection did not select events 4–7: {window._selected_ids()}")
        wait_with_qt(app, lambda: window.controller.view().get("selection") == selected_ids,
                     3, "keyboard selection acknowledgement")
        engine_before_loop = copy.deepcopy(window.controller.view().get("engine"))
        history_count_before_loop = len(window.controller.view().get("history", []))
        loop_message_index = len(received)
        QTest.keyClick(window, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
        wait_with_qt(app, lambda: window._view.get("mode") == "loop" and
                     window._view.get("playback_ids") == selected_ids, 3, "Loop Selection command")
        window.play_btn.click()
        loop_expected_chords = 4 * 3 + 1  # three full passes and first chord after wrap
        loop_deadline = time.monotonic() + loop_expected_chords * .06 + 10
        while time.monotonic() < loop_deadline:
            pump_messages(app, inbox, received)
            loop_received = received[loop_message_index:]
            loop_ons = [(stamp, msg) for stamp, msg in loop_received
                        if msg.type == "note_on" and msg.velocity > 0]
            if len(loop_ons) >= loop_expected_chords * 3:
                break
            time.sleep(.002)
        else:
            raise TimeoutError("Selection loop did not complete three passes and wrap")
        loop_pitches = [tuple(msg.note for _, msg in loop_ons[i:i + 3])
                        for i in range(0, loop_expected_chords * 3, 3)]
        expected_loop = [tuple(voice["pitch"] for voice in event["voices"])
                         for event in selected_events] * 3
        expected_loop.append(tuple(voice["pitch"] for voice in selected_events[0]["voices"]))
        if loop_pitches != expected_loop:
            raise RuntimeError("Loop MIDI pitches did not match the frozen event sequence")
        first_selected_key = selected_events[0]["key"]
        wait_with_qt(app, lambda: window._view.get("phase") == "Holding" and
                     window._view.get("cursor") == 0 and
                     window._view.get("current_key") == first_selected_key,
                     2, "first selected key on loop start")
        first_selected_key_displayed = window.key_display.text()
        if first_selected_key_displayed != f"Key: {KEY_NAMES[first_selected_key]} major":
            raise RuntimeError(f"Timeline key display disagrees with event 4: {first_selected_key_displayed}")
        loop_input_messages = received[loop_message_index:]
        loop_offs = [(stamp, msg) for stamp, msg in loop_input_messages
                     if msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0)]
        # Twelve completed chords precede the 13th onset; the stop cleanup
        # releases that final, deliberately interrupted chord.
        if len(loop_offs) < 12 * 3:
            raise RuntimeError("Loop did not release all notes from its completed passes")
        loop_gap_errors = []
        for chord_index in range(12):
            onset_group = loop_ons[chord_index * 3:(chord_index + 1) * 3]
            off_group = loop_offs[chord_index * 3:(chord_index + 1) * 3]
            if sorted(msg.note for _, msg in onset_group) != sorted(msg.note for _, msg in off_group):
                raise RuntimeError(f"Loop chord {chord_index} note-offs do not match its onset")
            if chord_index < 12:
                next_onset = loop_ons[(chord_index + 1) * 3][0]
                loop_gap_errors.append(next_onset - max(stamp for stamp, _ in off_group) - .03)
        minimum_loop_gap_ms = round(min(.03 + error for error in loop_gap_errors) * 1000, 3)
        if len({event["key"] for event in selected_events}) < 2:
            raise RuntimeError("Events 4–7 were not mixed-key; the loop key-label check would be incomplete")
        # Stop after the first chord of the fourth pass has arrived.
        window.stop_btn.click()
        wait_with_qt(app, lambda: window._view.get("phase") == "Idle", 3, "loop Stop acknowledgement")
        engine_after_loop = window.controller.view().get("engine")
        history_count_after_loop = len(window.controller.view().get("history", []))
        if engine_after_loop != engine_before_loop or history_count_after_loop != history_count_before_loop:
            raise RuntimeError("Selection replay changed generator state or appended history")

        cleanup_trials = []
        for trial in range(args.cleanup_trials):
            before_on = len(received)
            wait_with_qt(app, lambda: True, 1, "event loop")
            sequence = window.worker.command("next", mode="generate")
            ack = window.worker.wait_ack(sequence, timeout=3)
            if not ack or not ack.get("ok"):
                raise RuntimeError(f"Could not start cleanup trial: {ack}")
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                pump_messages(app, inbox, received)
                fresh_ons = [m for _, m in received[before_on:]
                             if m.type == "note_on" and m.velocity > 0]
                if len(fresh_ons) >= 3:
                    break
                time.sleep(.002)
            else:
                raise TimeoutError("Cleanup trial note-on was not received")
            action = "stop" if trial % 2 == 0 else "panic"
            started = time.perf_counter()
            sequence = window.worker.command(action)
            ack = window.worker.wait_ack(sequence, timeout=2)
            if not ack or not ack.get("ok"):
                raise RuntimeError(f"{action} command failed: {ack}")
            dispatch_seconds = time.perf_counter() - started
            base_received = len(received)
            deadline = time.monotonic() + 2
            needed_controls = 3 if action == "panic" else 0
            while time.monotonic() < deadline:
                pump_messages(app, inbox, received)
                new_messages = [m for _, m in received[base_received:]]
                note_offs = [m for m in new_messages if m.type == "note_off" or
                             (m.type == "note_on" and m.velocity == 0)]
                controls = [m for m in new_messages if m.type == "control_change" and m.control in (64, 123, 120)]
                if len(note_offs) >= 3 and len(controls) >= needed_controls:
                    break
                time.sleep(.002)
            else:
                raise TimeoutError(f"{action} cleanup MIDI was not received")
            cleanup_received = time.perf_counter() - started
            cleanup_trials.append({"action": action, "dispatch_ms": round(dispatch_seconds * 1000, 3),
                                   "receipt_ms": round(cleanup_received * 1000, 3)})

        pump_messages(app, inbox, received)
        history = window._view.get("history", [])
        try:
            revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                      capture_output=True, text=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            revision = "unknown"
        spread_summary = summary_ms(spreads)
        hold_summary = summary_ms(duration_errors)
        gap_summary = summary_ms(gap_errors)
        loop_gap_summary = summary_ms(loop_gap_errors)
        dispatch_summary = summary_ms([x["dispatch_ms"] / 1000 for x in cleanup_trials])
        targets = {"note_on_spread_max_ms": 20, "hold_error_max_ms": 50,
                   "gap_error_max_ms": 50, "loop_gap_min_ms": 25,
                   "loop_gap_error_max_ms": 50, "cleanup_dispatch_max_ms": 100}
        targets["pass"] = (spread_summary["max_ms"] is not None and spread_summary["max_ms"] <= 20 and
                           hold_summary["max_ms"] is not None and hold_summary["max_ms"] <= 50 and
                           gap_summary["max_ms"] is not None and gap_summary["max_ms"] <= 50 and
                           minimum_loop_gap_ms >= 25 and loop_gap_summary["max_ms"] is not None and
                           loop_gap_summary["max_ms"] <= 50 and
                           dispatch_summary["max_ms"] is not None and dispatch_summary["max_ms"] <= 100)
        musical_history = [{
            "id": event["id"], "branch_id": event["branch_id"],
            "voices": [{"id": voice["id"], "pitch": voice["pitch"]} for voice in event["voices"]],
            "key": event["key"], "hold": event["hold"], "silence": event["silence"],
            "velocity": event["velocity"], "channel": event["channel"], "revision": event["revision"],
        } for event in history]
        report.update({
            "label": "PASS" if len(on_groups) == args.events and targets["pass"] else "FAIL",
            "observed": {"history_events": len(history), "note_on_count": len(ons),
                         "note_off_count": len(offs), "qt_timer_ticks": timer_count[0],
                         "audio_heard": False, "app_data_isolated": True,
                         "generator_state_unchanged_by_loop": engine_after_loop == engine_before_loop,
                         "history_count_unchanged_by_loop":
                             history_count_after_loop == history_count_before_loop},
            "timing": {"targets": targets, "note_on_spread": spread_summary,
                       "hold_absolute_error": hold_summary,
                       "gap_absolute_error": gap_summary,
                       "loop_gap_absolute_error": loop_gap_summary,
                       "loop_gap_minimum_ms": minimum_loop_gap_ms,
                       "cleanup_trials": cleanup_trials,
                       "cleanup_dispatch": dispatch_summary,
                       "cleanup_receipt": summary_ms([x["receipt_ms"] / 1000 for x in cleanup_trials])},
            "generated_history": musical_history,
            "midi_receipt_capture": raw_capture(received, capture_origin),
            "selection_loop": {
                "range_event_ids": selected_ids, "range_keys": [event["key"] for event in selected_events],
                "first_selected_key": first_selected_key,
                "first_selected_key_displayed": first_selected_key_displayed,
                "first_selected_key_display_matches": True,
                "full_passes": 3, "wrap_onset_received": True,
                "received_chord_pitch_sequences": [list(pitches) for pitches in loop_pitches],
                "frozen_source_sequence": [
                    {"key": event["key"], "pitches": [v["pitch"] for v in event["voices"]],
                     "velocity": event["velocity"], "hold": event["hold"], "silence": event["silence"]}
                    for event in selected_events],
                "generator_snapshot_before": engine_before_loop,
                "generator_snapshot_after": engine_after_loop,
                "history_count_before": history_count_before_loop,
                "history_count_after": history_count_after_loop,
            },
        })
        print(json.dumps(report, indent=2))
        if args.report:
            write_report(args.report, report)
        return report
    except Exception as exc:
        report["label"] = "FAIL"
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        report["midi_receipt_capture"] = raw_capture(received, capture_origin)
        report.setdefault("observed", {})["qt_timer_ticks"] = timer_count[0]
        if args.report:
            write_report(args.report, report)
        print(json.dumps(report, indent=2))
        raise
    finally:
        ui_timer.stop()
        window.close()
        input_port.close()
        window._io_pool.shutdown(wait=True, cancel_futures=False)
        if previous_local_data is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = previous_local_data
        isolated_data.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument("--run", action="store_true", help="explicitly enable finite MIDI playback")
    parser.add_argument("--output", help="exact mido output port name")
    parser.add_argument("--input", help="exact corresponding loopMIDI input port name")
    parser.add_argument("--events", type=int, default=100)
    parser.add_argument("--velocity", type=int, default=24)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--cleanup-trials", type=int, default=20)
    parser.add_argument("--report", help="optional JSON report path")
    args = parser.parse_args()
    if args.list_ports:
        print(json.dumps({"outputs": mido.get_output_names(), "inputs": mido.get_input_names()}, indent=2))
        return 0
    if not args.run:
        parser.error("Use --list-ports for a safe inventory or --run after route approval.")
    if not args.output:
        parser.error("--output must name the exact MIDI output port")
    if type(args.events) is not int or args.events < 100:
        parser.error("--events must be an integer of at least 100")
    if type(args.cleanup_trials) is not int or args.cleanup_trials != 20:
        parser.error("--cleanup-trials is fixed at exactly 20 (10 Stop, 10 Panic)")
    if type(args.velocity) is not int or not 1 <= args.velocity <= 30:
        parser.error("--velocity must be a low integer in 1..30")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
