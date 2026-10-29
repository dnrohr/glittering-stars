"""Interruptible, single-owner playback state machine.

The controller is deliberately independent of Qt. A worker calls ``tick`` and
``command`` serially; tests can inject a clock and MIDI sink directly.
"""
from __future__ import annotations

import copy
import math
import queue
import threading
import time
import uuid
from dataclasses import asdict, is_dataclass
from typing import Any, Callable

import mido


class MidiSink:
    """Owns one opened mido output and exposes the output name."""

    def __init__(self, port_name: str):
        self.port_name = port_name
        self.port = mido.open_output(port_name)

    def send(self, message: mido.Message) -> None:
        self.port.send(message)

    def close(self) -> None:
        self.port.close()


def _dict(value: Any) -> dict:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    return copy.deepcopy(value)


def _voices(engine: Any) -> list[dict]:
    result = []
    for voice in engine.voices:
        if isinstance(voice, dict):
            result.append({"id": int(voice["id"]), "pitch": int(voice["pitch"])})
        else:
            result.append({"id": int(voice.id), "pitch": int(voice.pitch)})
    return result


def _decision_payload(result: Any) -> dict:
    return copy.deepcopy(result) if isinstance(result, dict) else {"status": str(result)}


class Controller:
    """Authoritative transport/history state; invoke only from its owner thread."""

    def __init__(self, config: Any, sink: Any = None,
                 clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.sink = sink
        self._lock = threading.RLock()
        self._active_notes: dict[int, int] = {}
        self._deadline: float | None = None
        self._hold = 0.0
        self._gap = 0.0
        self._event: dict | None = None
        self._next_command = 0
        self._last_command = 0
        self._cancel_generation = 0
        self._applied_config = config
        self._pending_config = None
        self._output_channel = int(getattr(config, "channel", 0))
        self._revision = 0
        self._engine = None
        self._history: list[dict] = []
        self._events_by_id: dict[str, dict] = {}
        self._branches = [{"id": "main", "parent_id": None, "anchor_id": None, "name": "Main"}]
        self._branches_with_events: set[str] = set()
        self._branch = "main"
        self._selection: tuple[str, ...] = ()
        self._frozen_ids: tuple[str, ...] = ()
        self._frozen_index: dict[str, int] = {}
        self._mode = "generate"
        self._phase = "Idle"
        self._error: str | None = None
        self._pause_pending = False
        self._single_event = False
        self._loop_replacement: tuple[str, ...] | None = None
        self._playback_replacement: tuple[str, tuple[str, ...]] | None = None
        self._override = False
        self._current_key: int | str | None = None
        self._cursor = 0
        self._event_counter = 0
        self._run_events = 0
        self._run_complete = False
        self._pending_reseed: int | None = None
        self._pending_key: int | str | None = None
        self._start_from_anchor = False
        self._context_log: list[dict] = []
        self._continuation_supported = True
        self._audition_restore: tuple[str, tuple[str, ...], int] | None = None

    def _ensure_engine(self):
        if self._engine is None:
            from glittering_stars.domain import Engine
            seed = getattr(self._applied_config, "seed", None)
            self._engine = Engine(self._applied_config, seed=seed)
            self._current_key = self._engine.key

    @property
    def next_deadline(self) -> float | None:
        return self._deadline

    def _send(self, message: mido.Message) -> None:
        if self.sink is not None:
            self.sink.send(message)

    def _channel(self) -> int:
        return self._output_channel

    def _freeze_events(self, ids) -> None:
        self._frozen_ids = tuple(ids)
        self._frozen_index = {event_id: index for index, event_id in enumerate(self._frozen_ids)}

    def _release(self) -> None:
        first_error = None
        try:
            for note, note_channel in sorted(self._active_notes.items()):
                try:
                    self._send(mido.Message("note_off", channel=note_channel, note=note, velocity=0))
                except Exception as exc:
                    first_error = first_error or exc
        finally:
            self._active_notes.clear()
        if first_error is not None:
            raise first_error

    def _panic(self) -> None:
        first_error = None
        channel = self._channel()
        try:
            self._send(mido.Message("control_change", channel=channel, control=64, value=0))
        except Exception as exc:
            first_error = exc
        try:
            self._release()
        except Exception as exc:
            first_error = first_error or exc
        for control in (123, 120):
            try:
                self._send(mido.Message("control_change", channel=channel,
                                        control=control, value=0))
            except Exception as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error

    def _begin_event(self, source: dict | None = None) -> None:
        """Emit one event. Generation appends; replay uses immutable stored data."""
        if source is None:
            self._apply_pending()
            self._ensure_engine()
            if self._pending_reseed is not None:
                self._engine.reseed(self._pending_reseed)
                self._context_log.append({"kind": "reseed", "seed": self._pending_reseed,
                                          "before_event": len(self._history)})
                self._pending_reseed = None
                self._revision += 1
            if self._pending_key is not None:
                previous_key = self._engine.key
                self._engine.set_key(self._pending_key)
                self._context_log.append({"kind": "set_key", "key_before": previous_key,
                                          "key_after": self._engine.key, "before_event": len(self._history)})
                self._revision += 1
                self._pending_key = None
            has_branch_events = self._branch in self._branches_with_events
            if not has_branch_events and not self._start_from_anchor and self._engine.counter == 0:
                decision = _decision_payload(self._engine.initial())
            else:
                decision = _decision_payload(self._engine.advance())
            self._start_from_anchor = False
            snapshot = self._engine.snapshot()
            event = {
                "id": str(uuid.uuid4()), "branch_id": self._branch,
                "voices": _voices(self._engine), "key": self._engine.key,
                "hold": float(getattr(self._applied_config, "hold", 3.0)),
                "silence": float(getattr(self._applied_config, "silence", 3.0)),
                "velocity": int(getattr(self._applied_config, "velocity", 55)),
                "channel": self._channel(), "revision": self._revision,
                "decision": decision, "snapshot": snapshot,
            }
            self._history.append(event)
            self._events_by_id[event["id"]] = event
            self._branches_with_events.add(self._branch)
            self._cursor = len(self._history) - 1
            self._event_counter += 1
            self._run_events += 1
        else:
            event = source
            self._cursor = self._frozen_index.get(event["id"], self._cursor)
        self._event = event
        self._hold = float(event["hold"])
        self._gap = float(event["silence"])
        if self._override:
            timing_config = self._pending_config or self._applied_config
            self._hold = float(getattr(timing_config, "hold", self._hold))
            self._gap = float(getattr(timing_config, "silence", self._gap))
        now = self.clock()
        notes = [int(v["pitch"]) for v in event["voices"]]
        # Stored event channels describe the generation-time route. Playback
        # follows the currently selected route without rewriting that record.
        channel = self._channel()
        timing_config = self._pending_config or self._applied_config
        velocity = int(getattr(timing_config, "velocity", event["velocity"])) if self._override else int(event["velocity"])
        try:
            for note in notes:
                self._send(mido.Message("note_on", channel=channel, note=note, velocity=velocity))
                self._active_notes[note] = channel
        except Exception:
            self._release()
            raise
        self._phase = "Holding"
        self._deadline = now + self._hold
        self._current_key = event["key"]

    def _apply_pending(self) -> None:
        if self._pending_config is None:
            return
        new_config = self._pending_config
        old_config = self._applied_config
        if self._engine is not None:
            next_revision = max(self._revision, self._engine.revision) + 1
            self._engine.apply_config(new_config, next_revision)
        if (isinstance(self.sink, MidiSink) and
                getattr(new_config, "port", None) != getattr(old_config, "port", None)):
            self._release()
            self.sink.close()
            self.sink = MidiSink(new_config.port)
        self._output_channel = max(0, min(15, int(new_config.channel)))
        self._applied_config = new_config
        self._revision = max(self._revision + 1, getattr(self._engine, "revision", self._revision))
        self._pending_config = None

    def _event_source(self) -> dict | None:
        if self._mode == "generate":
            return None
        if not self._frozen_ids:
            raise ValueError("Select one or more history events before replay")
        if self._mode == "replay" and self._cursor >= len(self._frozen_ids):
            return None
        if self._mode == "loop":
            self._cursor %= len(self._frozen_ids)
        event_id = self._frozen_ids[self._cursor]
        return self._events_by_id.get(event_id)

    def _start_next(self) -> None:
        if self._mode == "generate":
            self._begin_event()
            return
        source = self._event_source()
        if source is None:
            self._phase = "Paused"
            self._deadline = None
            self._single_event = False
            return
        self._begin_event(source)

    def _complete_boundary(self, now: float) -> None:
        if self._phase == "Holding":
            self._release()
            self._phase = "Gap"
            self._deadline = now + self._gap
            return
        if self._phase != "Gap":
            return
        if self._loop_replacement is not None:
            self._playback_replacement = ("loop", self._loop_replacement)
            self._loop_replacement = None
        replacement_boundary = self._playback_replacement is not None
        if self._playback_replacement is not None:
            self._mode, ids = self._playback_replacement
            self._freeze_events(ids)
            self._playback_replacement = None
            self._cursor = 0
        if replacement_boundary:
            if self._pause_pending:
                self._pause_pending = False
                self._phase = "Paused"
                self._deadline = None
                return
            self._single_event = False
            self._start_next()
            return
        if self._pause_pending or self._mode == "idle":
            if self._pause_pending and not replacement_boundary:
                if self._mode == "replay" and self._frozen_ids:
                    self._cursor = min(self._cursor + 1, len(self._frozen_ids))
                elif self._mode == "loop" and self._frozen_ids:
                    self._cursor = (self._cursor + 1) % len(self._frozen_ids)
            self._pause_pending = False
            self._phase = "Paused" if self._mode != "idle" else "Idle"
            self._deadline = None
            return
        if self._single_event:
            if self._audition_restore is not None:
                self._mode, ids, self._cursor = self._audition_restore
                self._freeze_events(ids)
                self._audition_restore = None
                self._single_event = False
                self._phase = "Paused"
                self._deadline = None
                return
            if not replacement_boundary:
                if self._mode == "replay" and self._frozen_ids:
                    self._cursor = min(self._cursor + 1, len(self._frozen_ids))
                elif self._mode == "loop" and self._frozen_ids:
                    self._cursor = (self._cursor + 1) % len(self._frozen_ids)
            self._single_event = False
            self._phase = "Paused"
            self._deadline = None
            return
        if self._mode == "replay":
            self._cursor += 1
            if self._cursor >= len(self._frozen_ids):
                self._phase = "Paused"
                self._deadline = None
                return
        elif self._mode == "loop":
            self._cursor = (self._cursor + 1) % len(self._frozen_ids)
        elif self._mode == "generate" and getattr(self._applied_config, "chords", 0) > 0:
            if self._run_events >= self._applied_config.chords:
                self._phase = "Paused"
                self._deadline = None
                self._run_complete = True
                return
        self._start_next()

    def tick(self, now: float | None = None) -> bool:
        """Advance deadline transitions; excess lateness never compresses a gap."""
        with self._lock:
            now = self.clock() if now is None else now
            if self._deadline is None or now < self._deadline:
                return False
            # At most two phases are crossed per tick. A late scheduler starts
            # the gap at actual note-off, then gives the entire configured gap.
            try:
                self._complete_boundary(now)
            except Exception as exc:
                try:
                    self._release()
                except Exception:
                    pass
                self._phase, self._mode = "Error", "idle"
                self._deadline = None
                self._error = str(exc)
            return True

    def command(self, name: str, **payload) -> dict:
        """Process one numbered command synchronously on the state owner."""
        with self._lock:
            self._next_command += 1
            command_id = self._next_command
            try:
                result = self._command(name.lower(), payload)
                self._last_command = command_id
                self._error = None
            except (ValueError, TypeError) as exc:
                self._error = str(exc)
                result = {"ok": False, "error": self._error}
            except (OSError, RuntimeError) as exc:
                self._error = str(exc)
                self._phase, self._mode = "Error", "idle"
                self._deadline = None
                try:
                    self._release()
                except Exception:
                    pass
                result = {"ok": False, "error": self._error}
            self._last_command = command_id
            result.setdefault("ok", True)
            result["command_id"] = command_id
            return result

    def _command(self, name: str, p: dict) -> dict:
        if name == "connect":
            if self._phase in ("Holding", "Gap"):
                raise ValueError("Stop playback before connecting an output")
            port = p.get("port", getattr(self._applied_config, "port", ""))
            available = mido.get_output_names()
            if port not in available:
                raise OSError(f"MIDI output {port!r} is unavailable. Available outputs: {available}")
            candidate_sink = MidiSink(port)
            try:
                self._release()
            except Exception:
                candidate_sink.close()
                raise
            old_sink = self.sink
            self.sink = candidate_sink
            if old_sink is not None and hasattr(old_sink, "close"):
                old_sink.close()
            self._phase = "Idle"
            return {"status": "Connected", "port": port}
        if name == "disconnect":
            if self._phase in ("Holding", "Gap"):
                raise ValueError("Stop playback before disconnecting the output")
            self._release()
            if self.sink is not None and hasattr(self.sink, "close"):
                self.sink.close()
            self.sink = None
            self._phase = "Idle"
            return {"status": "Disconnected"}
        if name == "config":
            from glittering_stars.domain import Config
            candidate = p.get("config")
            if isinstance(candidate, dict):
                candidate = Config.from_dict(candidate)
            candidate.validate()
            if (self._phase in ("Holding", "Gap") and
                    (candidate.channel != self._applied_config.channel or candidate.port != self._applied_config.port)):
                raise ValueError("Output port or channel can change only while idle")
            if self._engine is not None:
                # Validate against the current state now, but apply at boundary.
                candidate_check = self._engine.snapshot()
                self._engine.apply_config(candidate, max(self._revision, self._engine.revision) + 1)
                self._engine = type(self._engine).restore(candidate_check)
            # Channel selection is transport state. It can change while
            # replay is paused, independently of the generation config that
            # remains pending until the next generated event.
            if self._phase not in ("Holding", "Gap"):
                if candidate.channel != self._output_channel:
                    self._release()
                    self._output_channel = int(candidate.channel)
            self._pending_config = candidate
            return {"status": "Pending next chord", "revision": self._revision + 1}
        if name in ("play", "generate"):
            if self._mode == "generate" and not self._continuation_supported:
                raise ValueError("This session can be replayed but its engine version cannot continue")
            if self._run_complete and self._mode == "generate":
                self._run_events = 0
                self._run_complete = False
            if self._phase in ("Holding", "Gap"):
                if name == "generate":
                    self._mode = "generate"
                self._pause_pending = False
                return {"status": "Generating"}
            if name == "generate" or self._mode == "idle":
                self._mode = "generate"
            self._pause_pending = False
            self._single_event = False
            self._start_next()
            return {"status": "Playing"}
        if name == "pause":
            if self._phase in ("Holding", "Gap"):
                self._pause_pending = True
                return {"status": "Pause pending"}
            self._phase = "Paused"
            self._mode = "generate" if self._mode == "idle" else self._mode
            return {"status": "Paused"}
        if name == "next":
            if p.get("mode", self._mode) == "generate" and not self._continuation_supported:
                raise ValueError("This session can be replayed but its engine version cannot continue")
            target_mode = p.get("mode", self._mode if self._mode != "idle" else "generate")
            if self._run_complete and target_mode == "generate":
                self._run_events = 0
                self._run_complete = False
            if self._phase in ("Holding", "Gap"):
                raise ValueError("Next Chord is available only while idle or paused")
            self._mode = p.get("mode", self._mode if self._mode != "idle" else "generate")
            self._pause_pending = False
            self._single_event = True
            self._start_next()
            return {"status": "Next event"}
        if name in ("stop", "panic"):
            self._cancel_generation += 1
            self._pause_pending = False
            self._single_event = False
            self._deadline = None
            self._release() if name == "stop" else self._panic()
            if self._audition_restore is not None:
                self._mode, ids, self._cursor = self._audition_restore
                self._freeze_events(ids)
                self._audition_restore = None
            self._phase = "Idle"
            return {"status": "Stopped"}
        if name == 'clear_selection':
            self._selection = ()
            return {'status':'Selection cleared; frozen playback unchanged'}
        if name == "select":
            ids = tuple(str(i) for i in p.get("event_ids", ()))
            if not ids or len(ids) != len(set(ids)):
                raise ValueError("Selection must contain distinct history event IDs")
            positions = [next((i for i,e in enumerate(self._history) if e["id"] == x), -1) for x in ids]
            if any(i < 0 for i in positions) or positions != list(range(min(positions), max(positions) + 1)):
                raise ValueError("Selection must be a contiguous range of existing events")
            self._selection = ids
            if self._mode == "loop" and self._phase in ("Holding", "Gap"):
                self._loop_replacement = ids
            elif self._mode in ("loop", "replay"):
                self._freeze_events(ids)
                self._cursor = 0
            return {"status": "Selection updated", "event_ids": list(ids)}
        if name == "branch":
            if self._phase in ("Holding", "Gap"):
                raise ValueError("Stop playback before switching branches")
            branch_id = str(p.get("branch_id", ""))
            branch = next((item for item in self._branches if item.get("id") == branch_id), None)
            if branch is None:
                raise ValueError("Unknown branch ID")
            candidates = [i for i, event in enumerate(self._history) if event["branch_id"] == branch_id]
            anchor_id = candidates[-1] if candidates else next(
                (i for i, event in enumerate(self._history) if event["id"] == branch.get("anchor_id")), None)
            if anchor_id is None:
                from glittering_stars.domain import Engine
                engine = Engine(self._applied_config, seed=getattr(self._applied_config, "seed", None))
                self._start_from_anchor = False
                self._cursor = len(self._history)
            else:
                event = self._history[anchor_id]
                from glittering_stars.domain import Engine
                engine = Engine.restore(event["snapshot"])
                self._start_from_anchor = True
                self._cursor = anchor_id
            self._engine = engine
            self._applied_config = engine.config
            self._pending_config = None
            self._revision = max(self._revision, engine.revision)
            self._branch = branch_id
            self._run_events = 0
            self._run_complete = False
            self._mode = "generate"
            self._phase = "Paused"
            self._deadline = None
            return {"status": "Branch selected", "branch_id": branch_id}
        if name == "audition":
            if self._phase in ("Holding", "Gap"):
                raise ValueError("Stop playback before auditioning a stored event")
            event_id = str(p.get("event_id") or (self._selection[0] if len(self._selection) == 1 else ""))
            event = self._events_by_id.get(event_id)
            if event is None:
                raise ValueError("Audition requires one stored event")
            self._audition_restore = (self._mode, self._frozen_ids, self._cursor)
            self._freeze_events((event_id,))
            self._cursor = 0
            self._mode = "replay"
            self._single_event = True
            self._phase = "Paused"
            self._start_next()
            return {"status": "Auditioning stored event", "event_id": event_id}
        if name in ("loop", "replay"):
            ids = tuple(str(i) for i in p.get("event_ids", self._selection))
            if not ids:
                raise ValueError("Select one or more history events before replay")
            # Validate before changing current playback mode.
            events = {e["id"]: e for e in self._history}
            if any(i not in events for i in ids):
                raise ValueError("Selection contains unknown history events")
            positions = [next(i for i,e in enumerate(self._history) if e["id"] == x) for x in ids]
            if positions != list(range(min(positions), max(positions) + 1)):
                raise ValueError("Replay range must be a contiguous history range")
            self._selection = ids
            if self._phase in ("Holding", "Gap"):
                # Finish active event and its gap before switching data source.
                self._playback_replacement = (name, ids)
            else:
                self._freeze_events(ids)
                self._cursor = 0
                self._mode = name
            self._pause_pending = False
            return {"status": "Loop queued" if self._phase in ("Holding", "Gap") else "Replay ready"}
        if name == "loop_off":
            if self._mode == "loop":
                self._mode = "replay"
                self._pause_pending = True
                if self._phase not in ("Holding", "Gap"):
                    self._phase = "Paused"
                    self._deadline = None
            return {"status": "Replay paused at boundary"}
        if name == "override":
            self._override = bool(p.get("enabled", False))
            return {"status": "Timing/velocity override enabled" if self._override else "Recorded timing"}
        if name == "reseed":
            if type(p.get("seed")) is not int:
                raise ValueError("seed must be an integer")
            self._pending_reseed = p["seed"]
            return {"status": "Reseed pending next generated event", "revision": self._revision + 1}
        if name == "set_key":
            from glittering_stars.domain import key_number
            tonic = key_number(p["key"])
            cfg = self._pending_config or self._applied_config
            if cfg.allowed_keys and tonic not in cfg.allowed_keys:
                raise ValueError("key is outside allowed destination keys")
            if cfg.max_fifths is not None:
                from glittering_stars.domain.engine import Engine
                from glittering_stars.domain import key_number as normalize_key
                start_key = self._engine.start_key if self._engine is not None else normalize_key(cfg.starting_key)
                if Engine._fifths_distance(start_key, tonic) > cfg.max_fifths:
                    raise ValueError("key is outside the configured fifths distance")
            self._pending_key = tonic
            return {"status": "Set current key pending next generated event", "key": tonic}
        if name in ("new_phrase", "regenerate"):
            from glittering_stars.domain import Engine
            requested_config = p.get("config")
            if requested_config is not None:
                from glittering_stars.domain import Config
                new_config = Config.from_dict(requested_config) if isinstance(requested_config, dict) else requested_config
            elif self._pending_config is not None:
                new_config = self._pending_config
            else:
                new_config = self._applied_config
            if name == 'regenerate':
                import secrets
                from dataclasses import replace
                seed = secrets.randbits(64)
                while seed in (getattr(self._engine, 'effective_seed', None), new_config.seed):
                    seed = (seed + 1) % (2**64)
                new_config = replace(new_config, seed=seed, channel=self._output_channel,
                                     port=getattr(self.sink, 'port_name', new_config.port))
            # Stage every fallible operation before mutating the current
            # session, so an impossible chord range leaves it intact.
            new_config.validate()
            new_engine = Engine(new_config, seed=getattr(new_config, "seed", None))
            replacement_sink = None
            if (isinstance(self.sink, MidiSink) and
                    getattr(new_config, "port", None) != getattr(self.sink, "port_name", None)):
                replacement_sink = MidiSink(new_config.port)

            self._release()
            self._deadline = None
            self._phase = "Idle"
            if replacement_sink is not None:
                old_sink = self.sink
                self.sink = replacement_sink
                old_sink.close()
            self._applied_config = new_config
            self._pending_config = None
            self._revision += 1
            self._engine = new_engine
            self._output_channel = int(new_config.channel)
            self._mode = "generate"
            self._continuation_supported = True
            branch_id = str(uuid.uuid4())
            self._branches.append({"id": branch_id, "parent_id": self._branch,
                                   "anchor_id": None, "name": "New phrase"})
            self._branch = branch_id
            self._run_events = 0
            self._run_complete = False
            self._start_from_anchor = False
            self._pending_reseed = None
            self._pending_key = None
            self._selection = ()
            self._freeze_events(())
            self._phase = "Idle"
            self._deadline = None
            if name == 'regenerate':
                self._history = []
                self._events_by_id = {}
                self._branches = [{'id':'main','parent_id':None,'anchor_id':None,'name':'Main'}]
                self._branches_with_events = set()
                self._branch = 'main'
                self._cursor = 0
                self._event_counter = 0
                self._event = None
                self._pause_pending = False
                self._single_event = False
                self._loop_replacement = None
                self._playback_replacement = None
                self._audition_restore = None
                self._context_log = []
                self._engine.revision = self._revision
                self._start_next()
                return {'status':'Regenerated with fresh seed and cleared history','seed':new_config.seed}
            return {"status": "New phrase ready"}
        if name == "load":
            # File reads/schema validation belong on the I/O side. The caller
            # supplies the already validated session snapshot.
            incoming = p.get("session")
            if not isinstance(incoming, dict):
                raise ValueError("Load requires an already validated session snapshot")
            from glittering_stars.domain import Config
            loaded_config = (incoming["config"] if not isinstance(incoming["config"], dict)
                             else Config.from_dict(incoming["config"]))
            pending = incoming.get("pending_config")
            loaded_pending = Config.from_dict(pending) if isinstance(pending, dict) else pending
            output_channel = incoming.get("output_channel", loaded_config.channel)
            if type(output_channel) is not int or not 0 <= output_channel <= 15:
                raise ValueError("Session output channel must be an integer from 0 to 15")
            if incoming.get("continuation_supported", True) and incoming.get("engine"):
                from glittering_stars.domain import Engine
                restored_engine = Engine.restore(incoming["engine"])
            else:
                restored_engine = None
            detach_midi = isinstance(self.sink, MidiSink)
            self._release()
            if detach_midi:
                self.sink.close()
                self.sink = None
            self._deadline = None
            self._phase, self._mode = "Idle", "idle"
            self._engine = restored_engine
            self._applied_config = loaded_config
            self._pending_config = loaded_pending
            self._output_channel = output_channel
            self._history = incoming.get("history", [])
            self._events_by_id = {event["id"]: event for event in self._history}
            self._branches = incoming.get("branches", [])
            self._branches_with_events = {event["branch_id"] for event in self._history}
            self._branch = incoming.get("active_branch", "main")
            self._selection = tuple(incoming.get("selection", []))
            self._freeze_events(incoming.get("playback_ids", []))
            self._cursor = int(incoming.get("cursor", 0))
            self._mode = incoming.get("mode", "generate")
            if self._mode not in ("generate", "replay", "loop"):
                self._mode = "generate"
            self._override = bool(incoming.get("override", False))
            self._revision = int(incoming.get("applied_revision", 0))
            self._pending_reseed = incoming.get("pending_reseed")
            self._pending_key = incoming.get("pending_key")
            self._context_log = copy.deepcopy(incoming.get("context_log", []))
            self._start_from_anchor = bool(incoming.get("start_from_anchor", False))
            self._continuation_supported = bool(incoming.get("continuation_supported", True))
            self._audition_restore = None
            self._run_events = int(incoming.get("run_events", 0))
            self._run_complete = bool(incoming.get("run_complete", False))
            self._event_counter = len(self._history)
            self._current_key = self._engine.key if self._engine is not None else None
            return {"status": "Session loaded silently"}
        if name in ("continue", "explore"):
            if not self._continuation_supported:
                raise ValueError("This session can be replayed but its engine version cannot continue")
            if self._phase in ("Holding", "Gap"):
                raise ValueError("Stop playback before continuing or exploring a branch")
            anchor_id = str(p.get("anchor_id") or (self._selection[0] if len(self._selection) == 1 else ""))
            anchor = next((event for event in self._history if event["id"] == anchor_id), None)
            if anchor is None:
                raise ValueError("Continue or Explore requires one existing anchor event")
            from glittering_stars.domain import Engine
            engine = Engine.restore(anchor["snapshot"])
            if name == "explore":
                import secrets
                current_config = self._pending_config or self._applied_config
                engine.apply_config(current_config, max(engine.revision, self._revision) + 1)
                fresh_seed = secrets.randbits(64)
                engine.reseed(fresh_seed)
            elif p.get("current_settings", False):
                current_config = self._pending_config or self._applied_config
                engine.apply_config(current_config, max(engine.revision, self._revision) + 1)
            self._engine = engine
            parent = anchor["branch_id"]
            branch_id = str(uuid.uuid4())
            self._branches.append({"id": branch_id, "parent_id": parent,
                                   "anchor_id": anchor_id, "name": f"{name.title()} from {anchor_id[:8]}"})
            self._branch = branch_id
            self._applied_config = engine.config
            self._pending_config = None
            self._revision += 1
            self._mode = "generate"
            self._start_from_anchor = True
            self._run_events = 0
            self._run_complete = False
            self._cursor = next(i for i,event in enumerate(self._history) if event["id"] == anchor_id)
            self._phase = "Paused"
            self._deadline = None
            return {"status": f"{name.title()} branch ready", "branch_id": branch_id,
                    "seed": getattr(engine, "effective_seed", None)}
        if name == "edit":
            if not self._continuation_supported:
                raise ValueError("This session's engine version cannot create edited anchors")
            if self._phase in ("Holding", "Gap"):
                raise ValueError("Stop playback before editing a historical event")
            anchor_id = str(p.get("anchor_id") or (self._selection[0] if len(self._selection) == 1 else ""))
            anchor = next((event for event in self._history if event["id"] == anchor_id), None)
            if anchor is None:
                raise ValueError("Edit requires one existing anchor event")
            values = copy.deepcopy(anchor)
            edits = p.get("values", {})
            if not isinstance(edits, dict):
                raise ValueError("Edit values must be an object")
            for key in ("voices", "key", "hold", "silence", "velocity"):
                if key in edits:
                    values[key] = edits[key]
            if len(values["voices"]) != 3 or len({v["pitch"] for v in values["voices"]}) != 3:
                raise ValueError("Edited chord must contain three distinct voices")
            pitches = [int(v["pitch"]) for v in values["voices"]]
            if max(pitches) - min(pitches) < 7 or any(not 0 <= n <= 127 for n in pitches):
                raise ValueError("Edited chord violates MIDI range or seven-semitone span floor")
            if (isinstance(values["hold"], bool) or not isinstance(values["hold"], (int, float)) or
                    not math.isfinite(values["hold"]) or values["hold"] <= 0 or
                    isinstance(values["silence"], bool) or not isinstance(values["silence"], (int, float)) or
                    not math.isfinite(values["silence"]) or values["silence"] < 0 or
                    type(values["velocity"]) is not int or not 1 <= values["velocity"] <= 127):
                raise ValueError("Edited timing or velocity is invalid")
            from glittering_stars.domain import Engine
            engine = Engine.restore(anchor["snapshot"])
            engine.set_voices(values["voices"])
            engine.set_key(values["key"])
            values["key"] = engine.key
            engine.cooldown = int(anchor["snapshot"]["cooldown"])
            edited_config = engine.config
            if (values["hold"] != edited_config.hold or values["silence"] != edited_config.silence or
                    values["velocity"] != edited_config.velocity):
                from dataclasses import replace
                edited_config = replace(edited_config, hold=float(values["hold"]),
                                        silence=float(values["silence"]), velocity=int(values["velocity"]))
                engine.config = edited_config
            values["snapshot"] = engine.snapshot()
            values["revision"] = max(self._revision, engine.revision)
            branch_id = str(uuid.uuid4())
            values["id"], values["branch_id"] = str(uuid.uuid4()), branch_id
            values["decision"] = {"status": "edited anchor", "parent_event_id": anchor_id}
            self._history.append(values)
            self._events_by_id[values["id"]] = values
            self._branches_with_events.add(branch_id)
            self._branches.append({"id": branch_id, "parent_id": anchor["branch_id"],
                                   "anchor_id": anchor_id, "name": f"Edit of {anchor_id[:8]}"})
            self._branch = branch_id
            self._engine = engine
            self._applied_config = engine.config
            self._pending_config = None
            self._revision = max(self._revision, engine.revision)
            self._mode = "generate"
            self._start_from_anchor = True
            self._cursor = len(self._history) - 1
            self._selection = (values["id"],)
            self._phase = "Paused"
            return {"status": "Edited child anchor created", "event_id": values["id"]}
        raise ValueError(f"Unknown playback command: {name}")

    def view(self) -> dict:
        with self._lock:
            engine_snapshot = self._engine.snapshot() if self._engine is not None else None
            result = {
                "config": _dict(self._applied_config), "applied_revision": self._revision,
                "pending_config": _dict(self._pending_config) if self._pending_config is not None else None,
                "engine": engine_snapshot, "engine_snapshot": engine_snapshot, "schema_version": 1,
                "branches": list(self._branches), "active_branch": self._branch,
                "selection": list(self._selection), "frozen_ids": list(self._frozen_ids),
                "playback_ids": list(self._frozen_ids),
                "cursor": self._cursor, "mode": self._mode, "phase": self._phase,
                "error": self._error, "pause_pending": self._pause_pending,
                "context_log": copy.deepcopy(self._context_log),
                "override": self._override, "current_key": self._current_key,
                "output_channel": self._output_channel,
                "connected": self.sink is not None,
                "port_name": getattr(self.sink, "port_name", None),
                "deadline": self._deadline, "command_id": self._last_command,
            }
            # History events are immutable after append. Copy only the list so
            # large histories never block MIDI deadlines on a deep traversal.
            # Consumers treat the published history and event records as
            # read-only. Sessions deep-copy this view on their I/O thread.
            result["history"] = list(self._history)
            result["pending_reseed"] = self._pending_reseed
            result["pending_key"] = self._pending_key
            result["start_from_anchor"] = self._start_from_anchor
            result["run_events"] = self._run_events
            result["run_complete"] = self._run_complete
            result["continuation_supported"] = self._continuation_supported
            return result

    def close(self) -> None:
        with self._lock:
            self._deadline = None
            self._pause_pending = False
            self._release()
            self._phase = "Idle"
            self._mode = "idle"
            if self.sink is not None and hasattr(self.sink, "close"):
                self.sink.close()


class Worker:
    """Wakeable command/timer thread that owns a Controller and its MIDI sink."""

    def __init__(self, controller: Controller, on_view: Callable[[dict], None] | None = None):
        self.controller = controller
        self.on_view = on_view
        self._queue: queue.Queue = queue.Queue()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._closing = False
        self._sequence = 0
        self._published_sequence = 0
        self._submit_lock = threading.Lock()
        self._ack_condition = threading.Condition()
        self._ack_results: dict[int, dict] = {}

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._closing = False
        self._thread = threading.Thread(target=self._run, name="GlitteringStarsPlayback", daemon=False)
        self._thread.start()

    def command(self, name: str, **payload) -> int:
        with self._submit_lock:
            self._sequence += 1
            sequence = self._sequence
            self._queue.put((sequence, name, payload))
            self._wake.set()
            return sequence

    def _publish(self):
        if self.on_view is not None:
            try:
                view=self.controller.view()
                view['command_id']=self._published_sequence
                self.on_view(view)
            except Exception:
                pass

    def wait_ack(self, sequence: int, timeout: float | None = None) -> dict | None:
        """Wait for a numbered command acknowledgement; UI should use events."""
        with self._ack_condition:
            ready = self._ack_condition.wait_for(lambda: sequence in self._ack_results, timeout)
            return copy.deepcopy(self._ack_results[sequence]) if ready else None

    def _run(self) -> None:
        while not self._closing:
            deadline = self.controller.next_deadline
            timeout = None if deadline is None else max(0.0, deadline - self.controller.clock())
            self._wake.wait(timeout)
            self._wake.clear()
            batch = []
            while True:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            barriers = [seq for seq, name, _ in batch if name.lower() in ("stop", "panic", "regenerate")]
            latest_barrier = max(barriers, default=-1)
            for sequence, name, payload in batch:
                if sequence < latest_barrier and name.lower() in (
                        "play", "generate", "next", "loop", "replay", "loop_off", "regenerate"):
                    result = {"ok": False, "error": "Cancelled by a later Stop/Panic/Regenerate",
                              "command_id": sequence}
                    with self._ack_condition:
                        self._ack_results[sequence] = result
                        self._ack_condition.notify_all()
                    continue
                result = self.controller.command(name, **payload)
                result['command_id'] = sequence
                self._published_sequence = sequence
                with self._ack_condition:
                    self._ack_results[sequence] = result
                    self._ack_condition.notify_all()
                self._publish()
            transitioned = self.controller.tick()
            if transitioned:
                self._publish()
        self.controller.close()

    def close(self, timeout: float | None = 5.0) -> None:
        self._closing = True
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                raise TimeoutError("Playback worker did not stop before timeout")
