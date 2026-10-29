"""Glittering Stars native Windows chord exploration application."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import mido
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal, QObject, QItemSelection, QItemSelectionModel
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QBrush, QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QDialog,
    QSpinBox, QSplitter, QTableView, QVBoxLayout, QWidget, QScrollArea, QInputDialog, QTabWidget,
)

from glittering_stars.domain import Config, KEY_NAMES, key_number, note_name
from glittering_stars.playback import Controller, Worker

ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = ROOT / "settings.json"


def read_config() -> Config:
    from glittering_stars.sessions import app_data_dir
    user_file = app_data_dir() / "settings.json"
    bundled_file = Path(getattr(sys, "_MEIPASS", ROOT)) / "settings.json"
    source = user_file if user_file.is_file() else (SETTINGS_FILE if SETTINGS_FILE.is_file() else bundled_file)
    values = json.loads(source.read_text(encoding="utf-8"))
    return Config.from_dict(values)


def parse_list(text: str, cast):
    return tuple(cast(part.strip()) for part in text.split(",") if part.strip())


class ViewBridge(QObject):
    updated = Signal(object)
    io_done = Signal(str, str)


class TimelineModel(QAbstractTableModel):
    headers = ("#", "Voice ID 0", "Voice ID 1", "Voice ID 2", "Key", "Hold", "Gap", "Decision")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.events: list[dict] = []
        self.row_by_id: dict[str, int] = {}
        self.playhead_id: str | None = None
        self.last_reset = False

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.events)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.headers[section]
            return str(section + 1)
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        event = self.events[index.row()]
        if role == Qt.ItemDataRole.BackgroundRole and event.get("id") == self.playhead_id:
            return QBrush(QColor("#d9eafa"))
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        voices = sorted(event.get("voices", []), key=lambda v: v["id"])
        decision = event.get("decision", {})
        values = (
            str(index.row() + 1),
            *(f"{note_name(v['pitch'], event.get('key'))} ({v['pitch']})" for v in voices),
            KEY_NAMES[event.get("key", 0)] + " major",
            f"{event.get('hold', 0):g}s", f"{event.get('silence', 0):g}s",
            decision.get("reason") or decision.get("status", ""),
        )
        return values[index.column()]

    def replace(self, events: list[dict]):
        self.last_reset = False
        old = len(self.events)
        if len(events) == old and (not old or events[-1].get("id") == self.events[-1].get("id")):
            return False
        append_only = (len(events) >= old and
                       (old == 0 or (events[0].get("id") == self.events[0].get("id") and
                                     events[old-1].get("id") == self.events[-1].get("id"))))
        if append_only:
            if len(events) > old:
                self.beginInsertRows(QModelIndex(), old, len(events) - 1)
                self.events.extend(events[old:])
                self.row_by_id.update({event.get("id"): i for i, event in enumerate(self.events[old:], start=old)})
                self.endInsertRows()
        else:
            self.last_reset = True
            self.beginResetModel()
            self.events = list(events)
            self.row_by_id = {event.get("id"): i for i, event in enumerate(self.events)}
            self.endResetModel()
        return True

    def event_id(self, row: int) -> str | None:
        return self.events[row].get("id") if 0 <= row < len(self.events) else None


class MainWindow(QMainWindow):
    def __init__(self, config: Config | None = None, preview: bool = False):
        super().__init__()
        self.setWindowTitle("Glittering Stars")
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        if available:
            self.resize(min(1320, max(560, available.width() - 32)),
                        min(850, max(480, available.height() - 32)))
        else:
            self.resize(1320, 850)
        self._config = config or read_config()
        self._view: dict = {"history": [], "selection": [], "mode": "idle", "phase": "Idle"}
        self._syncing = False
        self._selection_guard = False
        self._io_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="GlitteringStarsFiles")
        self._draft_error: str | None = None
        self._preview = preview
        self.bridge = ViewBridge(self)
        self.bridge.updated.connect(self._update_view)
        self.bridge.io_done.connect(self._io_finished)
        self._load_controls_after_session = False
        self._last_autosave_marker = None
        self._autosave_dirty = False
        self._autosave_in_flight = False
        self._displayed_selection: tuple[str, ...] = ()
        self._pending_selection: tuple[str, ...] | None = None
        self._selection_command = 0
        self._regenerate_command = None
        self._displayed_branch_signature = None
        self._displayed_playhead_id = None
        self._displayed_current_key = None
        self._displayed_phase = None
        self._displayed_status = None
        self._displayed_connected = None
        self.controller = Controller(self._config)
        self.worker = Worker(self.controller, on_view=self.bridge.updated.emit)
        self.worker.start()

        root = QWidget(self)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.addLayout(self._make_transport())
        split = QSplitter(Qt.Orientation.Horizontal)
        control_scroll = QScrollArea()
        control_scroll.setWidgetResizable(True)
        control_scroll.setWidget(self._make_controls())
        split.addWidget(control_scroll)
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setWidget(self._make_inspector())
        self.content_tabs = QTabWidget()
        self.content_tabs.addTab(self._make_timeline(), "Timeline")
        self.content_tabs.addTab(inspector_scroll, "Inspector")
        split.addWidget(self.content_tabs)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        outer.addWidget(split, 1)
        self.status = QLabel("Ready · connect MIDI output or enable Preview")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        self.io_status = QLabel("")
        outer.addWidget(self.io_status)
        self._make_actions()
        self._refresh_ports()
        self._load_controls(self._config)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(15000)
        self.autosave_timer.timeout.connect(self._autosave_tick)
        self.autosave_timer.start()
        self.transport_timer = QTimer(self)
        self.transport_timer.setInterval(100)
        self.transport_timer.timeout.connect(self._refresh_transport_progress)
        self.transport_timer.start()

    def _refresh_transport_progress(self):
        phase=self._view.get('phase','Idle')
        text=f"{self._view.get('mode','generate').title()} · {phase}"
        deadline=self._view.get('deadline')
        if phase in ('Holding','Gap') and deadline is not None:
            text+=f" · {max(0, deadline-time.monotonic()):.1f}s remaining"
        if self._view.get('pause_pending'):
            text+=' · Pause pending'
        self.phase_display.setText(text)

    def _make_transport(self):
        bar = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.generate_btn = QPushButton("Generate")
        self.regenerate_btn = QPushButton('Regenerate (clear history)')
        self.regenerate_btn.setToolTip('Fresh seed, clear all history and branches, then generate again with current settings.')
        self.pause_btn = QPushButton("Pause")
        self.next_btn = QPushButton("Next Chord")
        self.stop_btn = QPushButton("Stop")
        self.panic_btn = QPushButton("Panic")
        self.loop_btn = QPushButton("Loop Selection")
        self.replay_btn = QPushButton("Replay Selection")
        self.loop_off_btn = QPushButton("Loop Off")
        for btn in (self.play_btn, self.generate_btn, self.pause_btn, self.next_btn, self.stop_btn,
                    self.panic_btn, self.loop_btn, self.replay_btn, self.loop_off_btn):
            bar.addWidget(btn)
        self.key_display = QLabel("Key: C major")
        bar.addWidget(self.key_display)
        self.phase_display = QLabel("Idle")
        bar.addWidget(self.phase_display)
        self.play_btn.clicked.connect(self._play)
        self.generate_btn.clicked.connect(lambda: self._send("generate"))
        self.regenerate_btn.clicked.connect(self._regenerate)
        self.pause_btn.clicked.connect(lambda: self._send("pause"))
        self.next_btn.clicked.connect(lambda: self._send("next"))
        self.stop_btn.clicked.connect(lambda: self._send("stop"))
        self.panic_btn.clicked.connect(lambda: self._send("panic"))
        self.loop_btn.clicked.connect(self._loop_selection)
        self.replay_btn.clicked.connect(self._replay_selection)
        self.loop_off_btn.clicked.connect(lambda: self._send("loop_off"))
        return bar

    def _make_controls(self):
        box = QWidget()
        layout = QVBoxLayout(box)
        conn = QFormLayout()
        self.port = QComboBox()
        self.port.setEditable(True)
        self.refresh_ports_btn = QPushButton("Refresh")
        port_row = QWidget()
        port_layout = QHBoxLayout(port_row)
        port_layout.setContentsMargins(0, 0, 0, 0)
        port_layout.addWidget(self.port, 1)
        port_layout.addWidget(self.refresh_ports_btn)
        self.refresh_ports_btn.clicked.connect(self._refresh_ports)
        self.channel = QSpinBox(); self.channel.setRange(1, 16)
        self.connect_btn = QPushButton("Connect MIDI")
        self.connection_status = QLabel('Disconnected · Preview available')
        self.connection_status.setWordWrap(True)
        self.loopmidi_path = QLineEdit(); self.loopmidi_path.setPlaceholderText("Optional loopMIDI executable path")
        self.launch_loopmidi = QPushButton("Launch loopMIDI")
        self.launch_loopmidi.clicked.connect(self._launch_loopmidi)
        self.preview_check = QCheckBox("Preview only (no MIDI output)")
        self.preview_check.setChecked(self._preview)
        self.connect_btn.clicked.connect(self._toggle_connection)
        self.preview_check.toggled.connect(self._preview_toggled)
        conn.addRow("Output", port_row)
        conn.addRow("MIDI channel", self.channel)
        conn.addRow(self.connect_btn)
        conn.addRow(self.connection_status)
        conn.addRow(self.preview_check)
        conn.addRow(self.regenerate_btn)
        conn.addRow(self.loopmidi_path)
        conn.addRow(self.launch_loopmidi)
        layout.addLayout(conn)

        form = QFormLayout()
        self.mode = QComboBox(); self.mode.addItems(["diatonic", "chromatic"])
        self.low = QLineEdit(); self.high = QLineEdit()
        self.hold = QDoubleSpinBox(); self.hold.setRange(.01, 3600); self.hold.setDecimals(2); self.hold.setSuffix(" s")
        self.gap = QDoubleSpinBox(); self.gap.setRange(0, 3600); self.gap.setDecimals(2); self.gap.setSuffix(" s")
        self.chords = QSpinBox(); self.chords.setRange(0, 100000); self.chords.setSpecialValueText("Continuous")
        self.seed = QLineEdit(); self.seed.setPlaceholderText("Random")
        self.velocity = QSpinBox(); self.velocity.setRange(1, 127)
        self.start_key = QComboBox(); self.start_key.addItems(KEY_NAMES)
        self.current_key = QComboBox(); self.current_key.addItems(KEY_NAMES)
        self.current_key_btn = QPushButton("Set Current Key")
        self.current_key_btn.clicked.connect(lambda: self._send("set_key", key=self.current_key.currentIndex()))
        self.policy = QComboBox()
        self.policy.addItem("Off", "off"); self.policy.addItem("Moving note", "moving_note")
        self.policy.addItem("Whole chord fits", "whole_chord"); self.policy.addItem("Pivot chord", "pivot")
        self.fourth = QDoubleSpinBox(); self.seventh = QDoubleSpinBox(); self.upward = QDoubleSpinBox()
        for control in (self.fourth, self.seventh, self.upward):
            control.setRange(0, 1); control.setSingleStep(.05); control.setDecimals(2)
        self.d_steps = QLineEdit(); self.d_weights = QLineEdit()
        self.c_steps = QLineEdit(); self.c_weights = QLineEdit()
        self.add_diatonic = QPushButton("Add diatonic step")
        self.remove_diatonic = QPushButton("Remove last diatonic step")
        self.add_chromatic = QPushButton("Add chromatic step")
        self.remove_chromatic = QPushButton("Remove last chromatic step")
        self.d_pct = QLabel(); self.c_pct = QLabel()
        self.d_weights.textChanged.connect(lambda value: self._show_percentages(value, self.d_pct))
        self.c_weights.textChanged.connect(lambda value: self._show_percentages(value, self.c_pct))
        self.allowed = QLineEdit(); self.allowed.setPlaceholderText("Any, or C,G,Bb")
        self.max_fifths = QComboBox(); self.max_fifths.addItems(["Unrestricted", "0", "1", "2", "3", "4", "5", "6"])
        self.cooldown = QSpinBox(); self.cooldown.setRange(0, 10000)
        self.min_span = QSpinBox(); self.min_span.setRange(7, 127)
        self.max_span = QSpinBox(); self.max_span.setRange(0, 127); self.max_span.setSpecialValueText("None")
        self.min_gap = QSpinBox(); self.min_gap.setRange(1, 127)
        self.octaves = QCheckBox("Allow octave doublings")
        self.lock_checks = [QCheckBox(f"Lock voice ID {voice_id}") for voice_id in range(3)]
        self.apply_btn = QPushButton("Apply settings")
        self.cancel_btn = QPushButton("Cancel draft")
        self.new_phrase_btn = QPushButton("New Phrase with These Settings")
        self.reseed_btn = QPushButton("Reseed at next chord")
        for label, widget in (
            ("Mode", self.mode), ("Low pitch", self.low), ("High pitch", self.high),
            ("Hold", self.hold), ("Silence", self.gap), ("Chord count (0=continuous)", self.chords),
            ("Seed", self.seed), ("Velocity", self.velocity), ("Starting key", self.start_key),
            ("Current key", self.current_key), ("Policy", self.policy),
            ("Fourth chance", self.fourth), ("Seventh chance", self.seventh),
            ("Diatonic steps", self.d_steps), ("Diatonic relative weights", self.d_weights),
            ("Diatonic step rows", self._button_row(self.add_diatonic, self.remove_diatonic)),
            ("Diatonic derived percentages", self.d_pct),
            ("Chromatic steps", self.c_steps), ("Chromatic relative weights", self.c_weights),
            ("Chromatic step rows", self._button_row(self.add_chromatic, self.remove_chromatic)),
            ("Chromatic derived percentages", self.c_pct),
            ("Upward probability", self.upward), ("Allowed keys", self.allowed),
            ("Max fifths distance", self.max_fifths), ("Cooldown events", self.cooldown),
            ("Minimum span", self.min_span), ("Maximum span (0=none)", self.max_span),
            ("Minimum neighboring gap", self.min_gap), ("Octave doubling", self.octaves),
        ):
            form.addRow(label, widget)
        for lock_check in self.lock_checks:
            form.addRow("Voice lock", lock_check)
        form.addRow(self.current_key_btn)
        form.addRow(self.apply_btn, self.cancel_btn)
        form.addRow(self.reseed_btn)
        form.addRow(self.new_phrase_btn)
        self.apply_btn.clicked.connect(self._apply_config)
        self.add_diatonic.clicked.connect(lambda: self._change_step_row(self.d_steps, self.d_weights, True))
        self.remove_diatonic.clicked.connect(lambda: self._change_step_row(self.d_steps, self.d_weights, False))
        self.add_chromatic.clicked.connect(lambda: self._change_step_row(self.c_steps, self.c_weights, True))
        self.remove_chromatic.clicked.connect(lambda: self._change_step_row(self.c_steps, self.c_weights, False))
        self.cancel_btn.clicked.connect(self._cancel_draft)
        self.reseed_btn.clicked.connect(self._reseed)
        self.new_phrase_btn.clicked.connect(self._new_phrase)
        layout.addLayout(form)
        layout.addStretch(1)
        box.setMinimumWidth(260)
        box.setMaximumWidth(440)
        return box

    @staticmethod
    def _button_row(*buttons):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        for button in buttons:
            layout.addWidget(button)
        return widget

    def _change_step_row(self, steps_field: QLineEdit, weights_field: QLineEdit, add: bool):
        try:
            steps = list(parse_list(steps_field.text(), int))
            weights = list(parse_list(weights_field.text(), float))
            if not steps or len(steps) != len(weights):
                raise ValueError("Step rows need one weight per distinct step")
            if add:
                steps.append(max(steps) + 1)
                weights.append(1.0)
            elif len(steps) > 1:
                steps.pop(); weights.pop()
            steps_field.setText(",".join(map(str, steps)))
            weights_field.setText(",".join(map(str, weights)))
        except (ValueError, TypeError) as exc:
            self._draft_error = f"Validation error · {exc}"
            self.status.setText(self._draft_error)

    def _make_timeline(self):
        box = QWidget(); layout = QVBoxLayout(box)
        self.timeline = QTableView()
        self.timeline_model = TimelineModel(self.timeline)
        self.timeline.setModel(self.timeline_model)
        self.timeline.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.timeline.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.timeline.setAlternatingRowColors(True)
        self.timeline.setSortingEnabled(False)
        self.timeline.selectionModel().selectionChanged.connect(self._selection_changed)
        self.override = QCheckBox("Live timing / velocity override for Replay and Loop")
        self.override.toggled.connect(lambda enabled: self._send("override", enabled=enabled))
        self.selection_label = QLabel("Select a contiguous chord range. Shift selects to the anchor; Ctrl+L loops it.")
        self.selection_label.setWordWrap(True)
        layout.addWidget(QLabel("Chord history · pitches are shown in voice lanes by stable voice ID"))
        layout.addWidget(self.timeline, 1)
        layout.addWidget(self.selection_label)
        layout.addWidget(self.override)
        return box

    def _make_inspector(self):
        box = QWidget(); layout = QVBoxLayout(box)
        self.inspect = QLabel("Select a chord to inspect its notes and decision.")
        self.inspect.setWordWrap(True)
        self.progress = QLabel("No chord generated")
        self.branch_picker = QComboBox()
        self.branch_picker.currentIndexChanged.connect(self._branch_changed)
        layout.addWidget(QLabel("Inspector")); layout.addWidget(QLabel("Active branch")); layout.addWidget(self.branch_picker)
        layout.addWidget(self.inspect)
        layout.addWidget(self.progress)
        self.surge_path = QLineEdit()
        self.surge_path.setPlaceholderText("Optional Surge XT executable path")
        self.launch_surge = QPushButton("Launch Surge XT")
        self.launch_surge.clicked.connect(self._launch_surge)
        layout.addWidget(self.surge_path); layout.addWidget(self.launch_surge)
        self.save_btn = QPushButton("Save Session…")
        self.open_btn = QPushButton("Open Session…")
        self.export_btn = QPushButton("Export Selection MIDI…")
        self.export_branch_btn = QPushButton("Export Active Branch MIDI…")
        self.continue_btn = QPushButton("Continue from Here…")
        self.explore_btn = QPushButton("Explore from Here")
        self.edit_btn = QPushButton("Edit as Child Variation…")
        self.audition_btn = QPushButton("Audition Selected Once")
        self.save_preset_btn = QPushButton("Save Preset…")
        self.load_preset_btn = QPushButton("Load Preset…")
        self.import_settings_btn = QPushButton("Import legacy settings…")
        for btn in (self.continue_btn, self.explore_btn, self.edit_btn, self.audition_btn,
                    self.save_btn, self.open_btn, self.save_preset_btn, self.load_preset_btn,
                    self.import_settings_btn, self.export_btn, self.export_branch_btn):
            layout.addWidget(btn)
        self.continue_btn.clicked.connect(self._continue_from_here)
        self.explore_btn.clicked.connect(self._explore_from_here)
        self.edit_btn.clicked.connect(self._edit_selected)
        self.audition_btn.clicked.connect(self._audition_selected)
        self.save_btn.clicked.connect(self._save_session)
        self.open_btn.clicked.connect(self._open_session)
        self.export_btn.clicked.connect(self._export_selection)
        self.export_branch_btn.clicked.connect(lambda: self._export_selection(branch=True))
        self.save_preset_btn.clicked.connect(self._save_preset)
        self.load_preset_btn.clicked.connect(self._load_preset)
        self.import_settings_btn.clicked.connect(self._import_legacy)
        layout.addStretch(1)
        box.setMinimumWidth(190)
        box.setMaximumWidth(330)
        return box

    def _make_actions(self):
        loop_action = QAction("Loop selection", self)
        loop_action.setShortcut(QKeySequence("Ctrl+L"))
        loop_action.triggered.connect(self._loop_selection)
        stop_action = QAction("Stop", self)
        stop_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        stop_action.triggered.connect(lambda: self._send("stop"))
        self.addAction(loop_action); self.addAction(stop_action)
        zoom_in = QAction("Zoom timeline in", self)
        zoom_in.setShortcut(QKeySequence("Ctrl++"))
        zoom_in.triggered.connect(lambda: self._zoom_timeline(1))
        self.addAction(zoom_in)
        zoom_out = QAction("Zoom timeline out", self)
        zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out.triggered.connect(lambda: self._zoom_timeline(-1))
        self.addAction(zoom_out)
        file_menu = self.menuBar().addMenu("File")
        for label, slot in (("Save session…", self._save_session), ("Open session…", self._open_session)):
            action = file_menu.addAction(label); action.triggered.connect(slot)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Exit"); quit_action.triggered.connect(self.close)
        help_menu = self.menuBar().addMenu("Help")
        help_action = help_menu.addAction("Using Glittering Stars")
        help_action.triggered.connect(self._show_help)

    def _show_help(self):
        QMessageBox.information(
            self, "Using Glittering Stars",
            "Generate creates a chord history. Play resumes the worker's current mode. Select a contiguous range, then Loop Selection or Replay Selection. "
            "Play resumes the selected replay or loop; Loop Off switches to one-pass replay. Stop preserves history, "
            "and Panic sends immediate cleanup. Settings are drafts until Apply; valid revisions take effect at a "
            "generation boundary. Preview sends no MIDI. Connect MIDI explicitly to use a selected output. "
            "Sessions preserve events and branches; exported MIDI contains notes and key markers, not the Surge patch or reverb.",
        )

    def _zoom_timeline(self, delta: int):
        font = self.timeline.font()
        font.setPointSize(max(7, min(24, font.pointSize() + delta)))
        self.timeline.setFont(font)
        self.timeline.resizeRowsToContents()

    def _branch_changed(self, index: int):
        if index < 0:
            return
        branch_id = self.branch_picker.itemData(index)
        if branch_id and branch_id != self._view.get("active_branch"):
            self.worker.command("branch", branch_id=branch_id)

    def _refresh_ports(self):
        current = self.port.currentText() if hasattr(self, "port") else self._config.port
        try:
            names = mido.get_output_names()
            self.port.clear(); self.port.addItems(names)
            self.port.setCurrentText(current)
            self.status.setText(f"Found {len(names)} MIDI output(s).")
        except (OSError, RuntimeError) as exc:
            self.status.setText(f"MIDI unavailable: {exc}. Enable Preview or refresh after connecting a device.")

    def _connect_midi(self):
        self.preview_check.setChecked(False)
        try:
            cfg = self._read_draft()
            available=[self.port.itemText(i) for i in range(self.port.count())]
            chosen=self.port.currentText()
            matches=[name for name in available if name==chosen] or [name for name in available if chosen.casefold() in name.casefold()]
            if len(matches)!=1:
                raise ValueError('Choose one available MIDI output from the picker, then Connect MIDI.')
            self.port.setCurrentText(matches[0])
            cfg=Config.from_dict(cfg.to_dict()|{'port':matches[0]})
            self.worker.command("config", config=cfg.to_dict())
            self._send("connect", port=self.port.currentText())
        except (ValueError, TypeError) as exc:
            self.status.setText(f"Validation error · {exc}")

    def _toggle_connection(self):
        if self._view.get("connected"):
            self._send("disconnect")
        else:
            self._connect_midi()

    def _preview_toggled(self, enabled: bool):
        if enabled:
            self._send("disconnect")
            self.status.setText("Preview mode · no MIDI messages are sent.")
        elif not self._view.get("connected"):
            self.status.setText("Choose an output and press Connect MIDI before playback.")

    def _load_controls(self, cfg: Config):
        self._syncing = True
        try:
            self.port.setCurrentText(cfg.port); self.channel.setValue(cfg.channel + 1)
            self.mode.setCurrentText(cfg.mode); self.low.setText(str(cfg.low)); self.high.setText(str(cfg.high))
            self.hold.setValue(cfg.hold); self.gap.setValue(cfg.silence); self.chords.setValue(cfg.chords)
            self.seed.setText("" if cfg.seed is None else str(cfg.seed)); self.velocity.setValue(cfg.velocity)
            self.start_key.setCurrentIndex(key_number(cfg.starting_key)); self.current_key.setCurrentIndex(key_number(cfg.starting_key))
            self.policy.setCurrentIndex(self.policy.findData(cfg.policy))
            self.fourth.setValue(cfg.fourth_modulation_probability); self.seventh.setValue(cfg.seventh_modulation_probability)
            self.d_steps.setText(",".join(map(str, cfg.diatonic_steps)))
            self.d_weights.setText(",".join(map(str, cfg.diatonic_probabilities)))
            self.c_steps.setText(",".join(map(str, cfg.chromatic_steps)))
            self.c_weights.setText(",".join(map(str, cfg.chromatic_probabilities)))
            self.upward.setValue(cfg.upward_probability)
            self.allowed.setText(",".join(KEY_NAMES[k] for k in cfg.allowed_keys))
            self.max_fifths.setCurrentIndex(0 if cfg.max_fifths is None else cfg.max_fifths + 1)
            self.cooldown.setValue(cfg.cooldown_events); self.min_span.setValue(cfg.min_span)
            self.max_span.setValue(cfg.max_span or 0); self.min_gap.setValue(cfg.min_gap)
            self.octaves.setChecked(cfg.octave_doubling)
            for voice_id, lock_check in enumerate(self.lock_checks):
                lock_check.setChecked(voice_id in cfg.locks)
        finally:
            self._syncing = False
        self._show_percentages(self.d_weights.text(), self.d_pct)
        self._show_percentages(self.c_weights.text(), self.c_pct)

    @staticmethod
    def _show_percentages(text: str, label: QLabel):
        try:
            values = parse_list(text, float)
            total = sum(values)
            if total <= 0:
                raise ValueError("no positive weights")
            label.setText(" · ".join(f"{100 * value / total:.1f}%" for value in values))
        except (ValueError, TypeError):
            label.setText("Invalid weights")

    def _read_draft(self) -> Config:
        seed_text = self.seed.text().strip()
        allowed_text = self.allowed.text().strip()
        return Config(
            port=self.port.currentText().strip(), mode=self.mode.currentText(), low=self.low.text().strip(),
            high=self.high.text().strip(), hold=self.hold.value(), silence=self.gap.value(),
            chords=self.chords.value(), seed=int(seed_text) if seed_text else None,
            velocity=self.velocity.value(), starting_key=KEY_NAMES[self.start_key.currentIndex()],
            fourth_modulation_probability=self.fourth.value(), seventh_modulation_probability=self.seventh.value(),
            diatonic_steps=parse_list(self.d_steps.text(), int),
            diatonic_probabilities=parse_list(self.d_weights.text(), float),
            chromatic_steps=parse_list(self.c_steps.text(), int),
            chromatic_probabilities=parse_list(self.c_weights.text(), float), channel=self.channel.value() - 1,
            policy=self.policy.currentData(), upward_probability=self.upward.value(),
            allowed_keys=tuple(key_number(k) for k in parse_list(allowed_text, str)) if allowed_text else (),
            max_fifths=None if self.max_fifths.currentIndex() == 0 else self.max_fifths.currentIndex() - 1,
            cooldown_events=self.cooldown.value(), min_span=self.min_span.value(),
            max_span=self.max_span.value() or None, min_gap=self.min_gap.value(),
            octave_doubling=self.octaves.isChecked(),
            locks=tuple(i for i, check in enumerate(self.lock_checks) if check.isChecked()),
        )

    def _apply_config(self):
        try:
            cfg = self._read_draft()
            self.worker.command("config", config=cfg.to_dict())
            self._draft_error = None
            self.status.setText("Pending next chord · settings were validated as one revision.")
        except (ValueError, TypeError) as exc:
            self._draft_error = f"Validation error · {exc}"
            self.status.setText(self._draft_error)

    def _cancel_draft(self):
        applied = self._view.get("config")
        if applied:
            self._config = Config.from_dict(applied)
            self._load_controls(self._config)
            self.status.setText("Draft cancelled · showing applied settings.")

    def _reseed(self):
        try:
            seed = int(self.seed.text())
        except ValueError:
            self.status.setText("Enter an integer seed before reseeding.")
            return
        self._send("reseed", seed=seed)

    def _new_phrase(self):
        try:
            cfg = self._read_draft()
            self.worker.command("new_phrase", config=cfg.to_dict())
            self.status.setText("New phrase requested with validated settings.")
        except (ValueError, TypeError) as exc:
            self.status.setText(f"Validation error · {exc}")

    def _regenerate(self):
        try:
            cfg = self._read_draft()
            if not self.preview_check.isChecked() and not self._view.get('connected'):
                self.status.setText('Connect MIDI or enable Preview before regenerating.')
                return
            self._draft_error = None
            self._pending_selection = None
            self._regenerate_command = self.worker.command('regenerate',config=cfg.to_dict())
        except (ValueError,TypeError) as exc:
            self._draft_error = f'Validation error · {exc}'
            self.status.setText(self._draft_error)

    def _send(self, name: str, **payload):
        if hasattr(self, "worker"):
            if name in ("generate", "play", "next") and not self.preview_check.isChecked() and not self._view.get("connected"):
                self.status.setText("No MIDI output is connected. Connect one or enable Preview.")
                return
            self.worker.command(name, **payload)

    def _play(self):
        self._send("play")

    def _selected_ids(self) -> list[str]:
        rows = sorted({index.row() for index in self.timeline.selectionModel().selectedRows()})
        if not rows or rows != list(range(rows[0], rows[-1] + 1)):
            return []
        return [self.timeline_model.event_id(row) for row in rows]

    def _selection_changed(self, *_):
        if self._selection_guard:
            return
        ids = self._selected_ids()
        self._pending_selection = tuple(ids)
        if ids:
            self._selection_command = self.worker.command("select", event_ids=ids)
            self.selection_label.setText(f"{len(ids)} chord(s) selected · events {self.timeline.selectionModel().selectedRows()[0].row()+1}–{self.timeline.selectionModel().selectedRows()[-1].row()+1}")
        else:
            self._selection_command = self.worker.command('clear_selection')
            self.selection_label.setText('No contiguous passage selected. Existing playback is unchanged.')

    def _loop_selection(self):
        ids = self._selected_ids()
        if not ids:
            self.status.setText("Select a contiguous passage before looping.")
            return
        self.worker.command("select", event_ids=ids)
        self.worker.command("loop", event_ids=ids)

    def _replay_selection(self):
        ids = self._selected_ids()
        if not ids:
            self.status.setText("Select a contiguous passage before replaying.")
            return
        self.worker.command("select", event_ids=ids)
        self.worker.command("replay", event_ids=ids)

    def _update_view(self, view: dict):
        self._view = view
        if self._regenerate_command is not None and view.get('command_id',0) >= self._regenerate_command:
            self._regenerate_command = None
            if not view.get('error'):
                self.seed.setText(str(view['config']['seed']))
        if view.get("preset_config"):
            self._load_controls(Config.from_dict(view["preset_config"]))
            self.status.setText("Validated preset shown as a draft. Apply settings to use it.")
        if self._load_controls_after_session and view.get("config"):
            self._pending_selection = None
            self._load_controls(Config.from_dict(view.get('pending_config') or view["config"]))
            self.channel.setValue(view.get('output_channel',self.channel.value()-1)+1)
            self._load_controls_after_session = False
        branches = view.get("branches", [])
        branch_signature = (tuple((b.get("id"), b.get("name"), b.get("parent_id"), b.get("anchor_id")) for b in branches), view.get("active_branch"))
        if branch_signature != self._displayed_branch_signature:
            self.branch_picker.blockSignals(True)
            self.branch_picker.clear()
            for branch in branches:
                parent_id = branch.get("parent_id")
                lineage = f"  ↳ {parent_id[:8]}" if parent_id else ""
                self.branch_picker.addItem(f"{branch.get('name', branch.get('id'))}{lineage}", branch.get("id"))
            branch_index = self.branch_picker.findData(view.get("active_branch"))
            self.branch_picker.setCurrentIndex(max(0, branch_index))
            self.branch_picker.setToolTip(f"Active branch: {view.get('active_branch', 'main')}")
            self.branch_picker.blockSignals(False)
            self._displayed_branch_signature = branch_signature
        history = view.get("history", [])
        selected_ids = list(view.get("selection", []))
        self._selection_guard = True
        try:
            model_changed = self.timeline_model.replace(history)
        finally:
            self._selection_guard = False
        if self._pending_selection is not None:
            if view.get('command_id',0) >= self._selection_command:
                self._pending_selection = None
            elif all(item in self.timeline_model.row_by_id for item in self._pending_selection):
                # Older queued worker views must not roll back a newer gesture.
                selected_ids = list(self._pending_selection)
            else:
                self._pending_selection = None
        selected_tuple = tuple(selected_ids)
        selection_changed = selected_tuple != self._displayed_selection
        if selection_changed or self.timeline_model.last_reset:
            self._selection_guard = True
            try:
                selection_model = self.timeline.selectionModel()
                selection_model.clearSelection()
                positions = [self.timeline_model.row_by_id[item] for item in selected_ids if item in self.timeline_model.row_by_id]
                if positions:
                    selection = QItemSelection()
                    for row in positions:
                        selection.select(self.timeline_model.index(row, 0), self.timeline_model.index(row, self.timeline_model.columnCount()-1))
                    selection_model.select(selection, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
            finally:
                self._selection_guard = False
            self._displayed_selection = selected_tuple
        positions = [self.timeline_model.row_by_id[item] for item in selected_ids if item in self.timeline_model.row_by_id]
        cfg = view.get("config", {})
        if view.get("engine"):
            tonic = view.get("current_key")
            if tonic is None:
                tonic = cfg.get("starting_key", 0) if isinstance(cfg, dict) else 0
            tonic = key_number(tonic)
            if tonic != self._displayed_current_key:
                self.key_display.setText(f"Key: {KEY_NAMES[tonic]} major")
                self.current_key.blockSignals(True)
                self.current_key.setCurrentIndex(tonic)
                self.current_key.blockSignals(False)
                self._displayed_current_key = tonic
        phase_text = f"{view.get('mode', 'idle').title()} · {view.get('phase', 'Idle')}" + (" · Pause pending" if view.get("pause_pending") else "")
        if phase_text != self._displayed_phase:
            self.phase_display.setText(phase_text)
            self._displayed_phase = phase_text
        pending = view.get("pending_config")
        status_text = self._draft_error or (
            view.get('compatibility_warning', 'Inspection/replay only: unsupported engine version') if not view.get('continuation_supported',True) else
            'Pending next chord · reseed/key context' if view.get('pending_reseed') is not None or view.get('pending_key') is not None else
            f"Pending next chord · revision {view.get('applied_revision',0)+1}" if pending else
            f"Error · {view['error']}" if view.get("error") else
            f"Applied revision {view.get('applied_revision',0)} · {len(history)} stored chord events" if history else
            self.status.text()
        )
        if status_text != self.status.text():
            self.status.setText(status_text)
            self._displayed_status = status_text
        if history:
            cursor = view.get("cursor", 0)
            playback_ids = view.get("playback_ids", [])
            if view.get("mode") in ("replay", "loop") and playback_ids:
                playhead_id = playback_ids[cursor % len(playback_ids)]
                pos = self.timeline_model.row_by_id.get(playhead_id, -1)
            else:
                pos = min(cursor, len(history) - 1)
                playhead_id = history[pos].get("id") if pos >= 0 else None
            if playhead_id != self._displayed_playhead_id:
                previous_row = self.timeline_model.row_by_id.get(self._displayed_playhead_id)
                self.timeline_model.playhead_id = playhead_id
                self._displayed_playhead_id = playhead_id
                for row in (previous_row, pos):
                    if row is not None and row >= 0:
                        self.timeline_model.dataChanged.emit(self.timeline_model.index(row, 0), self.timeline_model.index(row, self.timeline_model.columnCount()-1), [Qt.ItemDataRole.BackgroundRole])
                self.progress.setText(f"Playhead: event {pos+1} of {len(history)}")
        elif self._displayed_playhead_id is not None:
            self._displayed_playhead_id = None
            self.timeline_model.playhead_id = None
        if positions and (selection_changed or model_changed or self._load_controls_after_session):
            event = self.timeline_model.events[positions[0]]
            notes = sorted(v["pitch"] for v in event.get("voices", []))
            decision = event.get("decision", {})
            self.inspect.setText(
                f"Event {positions[0]+1}\n" + " · ".join(note_name(n, event.get("key")) + f" ({n})" for n in notes) +
                f"\nKey: {KEY_NAMES[event.get('key',0)]} major · Hold {event.get('hold',0):g}s · Gap {event.get('silence',0):g}s"+
                f"\nDecision: {decision.get('status', decision.get('reason','recorded event'))}"
                f"\nReason: {decision.get('reason','Recorded/edited event')}"
                f"\nStep: {decision.get('step','—')} · Voice ID: {decision.get('voice_id','—')} · Direction: {decision.get('direction','—')}"
            )
        elif not positions:
            self.inspect.setText("Select a chord to inspect its notes and decision.")
        marker = (len(history), view.get("applied_revision", 0), tuple(view.get("selection", [])), view.get("active_branch"),
                  view.get('mode'), view.get('cursor'), view.get('override'), view.get('pending_reseed'), view.get('pending_key'),
                  json.dumps(pending,sort_keys=True))
        if history and marker != self._last_autosave_marker:
            self._last_autosave_marker = marker
            self._autosave_dirty = True
            self.io_status.setText('Unsaved session changes · autosave pending')
        connected = bool(view.get("connected"))
        self.connection_status.setText(
            f"Connected · {view.get('port_name') or 'MIDI'} · channel {view.get('output_channel',0)+1}" if connected else
            'Disconnected · Preview available')
        if connected != self._displayed_connected:
            self.connect_btn.setText("Disconnect MIDI" if connected else "Connect MIDI")
            self.preview_check.blockSignals(True)
            self.preview_check.setChecked(not connected)
            self.preview_check.blockSignals(False)
            self._displayed_connected = connected
        if not connected and view.get("error"):
            self.connect_btn.setText("Connect MIDI")
        if view.get("mode") in ("loop", "replay"):
            self.override.blockSignals(True)
            self.override.setChecked(bool(view.get("override")))
            self.override.blockSignals(False)

    def _launch_surge(self):
        path = self.surge_path.text().strip()
        if not path or not Path(path).is_file():
            self.status.setText("Choose the installed Surge XT executable path first.")
            return
        try:
            os.startfile(path)
            self.status.setText("Surge XT launch requested.")
        except OSError as exc:
            self.status.setText(f"Could not launch Surge XT: {exc}")

    def _launch_loopmidi(self):
        path = self.loopmidi_path.text().strip()
        if not path or not Path(path).is_file():
            self.status.setText("Choose the installed loopMIDI executable path first.")
            return
        try:
            os.startfile(path)
            self.status.setText("loopMIDI launch requested. Create or enable the configured MIDI port there.")
        except OSError as exc:
            self.status.setText(f"Could not launch loopMIDI: {exc}")

    def _one_selected_event(self):
        ids = self._selected_ids()
        if len(ids) != 1:
            self.status.setText("Select exactly one chord for this action.")
            return None
        return ids[0]

    def _continue_from_here(self):
        anchor = self._one_selected_event()
        if not anchor:
            return
        choice = QMessageBox(self)
        choice.setWindowTitle("Continue from Here")
        choice.setText("Choose which settings the new branch should use.")
        recorded = choice.addButton("Recorded Settings", QMessageBox.ButtonRole.AcceptRole)
        current = choice.addButton("Current Settings", QMessageBox.ButtonRole.ActionRole)
        choice.addButton(QMessageBox.StandardButton.Cancel)
        choice.setDefaultButton(recorded)
        choice.exec()
        if choice.clickedButton() not in (recorded, current):
            return
        self.worker.command("continue", anchor_id=anchor, current_settings=choice.clickedButton() is current)

    def _explore_from_here(self):
        anchor = self._one_selected_event()
        if anchor:
            try:
                cfg = self._read_draft()
                self.worker.command("config", config=cfg.to_dict())
                self.worker.command("explore", anchor_id=anchor)
            except (ValueError, TypeError) as exc:
                self.status.setText(f"Validation error · {exc}")

    def _edit_selected(self):
        anchor_id = self._one_selected_event()
        if not anchor_id:
            return
        event = next((e for e in self._view.get("history", []) if e.get("id") == anchor_id), None)
        if event is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Edited Child Anchor")
        form = QFormLayout(dialog)
        voices = sorted(event["voices"], key=lambda v: v["id"])
        pitch_inputs = []
        for voice in voices:
            field = QLineEdit(str(voice["pitch"]))
            form.addRow(f"Voice ID {voice['id']} pitch (MIDI)", field)
            pitch_inputs.append((voice["id"], field))
        tonic = QComboBox(); tonic.addItems(KEY_NAMES); tonic.setCurrentIndex(int(event.get("key", 0)))
        hold = QDoubleSpinBox(); hold.setRange(.01, 3600); hold.setValue(float(event.get("hold", 2)))
        gap = QDoubleSpinBox(); gap.setRange(0, 3600); gap.setValue(float(event.get("silence", 0)))
        velocity = QSpinBox(); velocity.setRange(1, 127); velocity.setValue(int(event.get("velocity", 55)))
        form.addRow("Key", tonic); form.addRow("Hold (s)", hold); form.addRow("Gap (s)", gap); form.addRow("Velocity", velocity)
        okay = QPushButton("Create variation")
        okay.clicked.connect(dialog.accept)
        form.addRow(okay)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            values = {"voices": [{"id": voice_id, "pitch": int(field.text())} for voice_id, field in pitch_inputs],
                      "key": tonic.currentIndex(), "hold": hold.value(), "silence": gap.value(), "velocity": velocity.value()}
            self.worker.command("edit", anchor_id=anchor_id, values=values)
        except (ValueError, TypeError) as exc:
            self.status.setText(f"Edit rejected · {exc}")

    def _audition_selected(self):
        event_id = self._one_selected_event()
        if event_id:
            self.worker.command("audition", event_id=event_id)

    def _io_finished(self, operation: str, result: str):
        if operation == "autosave":
            self._autosave_in_flight = False
            if "failed" in result.lower():
                self.io_status.setText(result)
            else:
                self.io_status.setText("Autosave current")
        else:
            self.io_status.setText(result)

    def _io_task(self, operation: str, path: str, function, *args):
        future = self._io_pool.submit(function, *args)
        def done(completed):
            try:
                completed.result()
                message = f"{operation.title()} complete · {path}"
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                message = f"{operation.title()} failed · {exc}"
            self.bridge.io_done.emit(operation, message)
        future.add_done_callback(done)

    def _autosave_tick(self, force: bool = False):
        if not self._autosave_dirty:
            return
        if self._autosave_in_flight:
            if force:
                from glittering_stars.sessions import app_data_dir, save
                path = app_data_dir() / "autosave.gstars.json"
                view = self._view
                self._autosave_dirty = False
                future = self._io_pool.submit(save, path, view)
                future.add_done_callback(lambda completed: self._emit_autosave_result(completed))
            return
        if not force and not self._view.get("history"):
            return
        from glittering_stars.sessions import app_data_dir, save
        path = app_data_dir() / "autosave.gstars.json"
        view = self._view
        self._autosave_dirty = False
        self._autosave_in_flight = True
        future = self._io_pool.submit(save, path, view)
        future.add_done_callback(self._emit_autosave_result)

    def _emit_autosave_result(self, completed):
        try:
            completed.result()
            message = "Autosave current"
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            message = f"Autosave failed · {exc}"
        self.bridge.io_done.emit("autosave", message)

    def _save_session(self):
        from glittering_stars.sessions import save
        path, _ = QFileDialog.getSaveFileName(self, "Save session", str(ROOT), "Glittering Stars (*.gstars.json);;JSON (*.json)")
        if not path:
            return
        view = self._view
        self._io_task("save", path, save, path, view)

    def _offer_autosave_recovery(self):
        from glittering_stars.sessions import app_data_dir, load
        path = app_data_dir() / "autosave.gstars.json"
        if not path.is_file():
            return
        answer = QMessageBox.question(
            self, "Recover last session?",
            "A recoverable autosave is available. Restore it stopped and silent?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.status.setText("Checking autosave…")
        future = self._io_pool.submit(load, path)
        def done(completed):
            try:
                session = completed.result()
                self._load_controls_after_session = True
                self.worker.command("load", session=session)
                message = "Autosave restored stopped and silent."
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                self._load_controls_after_session = False
                message = f"Autosave could not be restored · {exc}"
            self.bridge.io_done.emit("load", message)
        future.add_done_callback(done)

    def _open_session(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open session", str(ROOT), "Glittering Stars (*.gstars.json *.json)")
        if not path:
            return
        from glittering_stars.sessions import load
        self.status.setText("Loading and validating session…")
        future = self._io_pool.submit(load, path)
        def done(completed):
            try:
                session = completed.result()
                self._load_controls_after_session = True
                self.worker.command("load", session=session)
                message = f"Session loaded stopped and silent · {path}"
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                self._load_controls_after_session = False
                message = f"Open failed · {exc}"
            self.bridge.io_done.emit("load", message)
        future.add_done_callback(done)

    def _save_preset(self):
        try:
            config = self._read_draft()
        except (ValueError, TypeError) as exc:
            self.status.setText(f"Preset not saved · {exc}")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save configuration preset", str(ROOT), "Preset (*.gstarspreset.json);;JSON (*.json)")
        if path:
            from glittering_stars.sessions import save_preset
            self._io_task("save", path, save_preset, path, config)

    def _load_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load configuration preset", str(ROOT), "Preset (*.gstarspreset.json *.json)")
        if not path:
            return
        from glittering_stars.sessions import load_preset
        future = self._io_pool.submit(load_preset, path)
        def done(completed):
            try:
                config = completed.result()
                if not isinstance(config, Config):
                    config = Config.from_dict(config)
                self.bridge.updated.emit({**self._view, "preset_config": config.to_dict()})
                message = f"Preset validated · apply it when ready · {path}"
            except (OSError, ValueError, TypeError) as exc:
                message = f"Preset load failed · {exc}"
            self.bridge.io_done.emit("preset", message)
        future.add_done_callback(done)

    def _import_legacy(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import legacy settings.json", str(ROOT), "JSON (*.json)")
        if not path:
            return
        def import_file():
            values = json.loads(Path(path).read_text(encoding="utf-8"))
            return Config.from_dict(values).to_dict()
        future = self._io_pool.submit(import_file)
        def done(completed):
            try:
                config = Config.from_dict(completed.result())
                self.bridge.updated.emit({**self._view, "preset_config": config.to_dict()})
                message = f"Legacy settings imported as a draft · {path}"
            except (OSError, ValueError, TypeError) as exc:
                message = f"Import failed · {exc}"
            self.bridge.io_done.emit("import", message)
        future.add_done_callback(done)

    def _export_selection(self, branch=False):
        from glittering_stars.sessions import export_midi
        ids = [] if branch else self._selected_ids()
        if not branch and not ids:
            self.status.setText('Select a contiguous passage to export, or choose Export Active Branch MIDI.')
            return
        history = list(self._view.get("history", []))
        rows = {event.get("id"): event for event in history}
        if ids:
            events = [rows[key] for key in ids if key in rows]
            description = "selection"
        else:
            active = self._view.get("active_branch", "main")
            branches = {b.get("id"): b for b in self._view.get("branches", [])}
            history_index = {event.get("id"): i for i, event in enumerate(history)}

            def path_to_event(event_id: str, seen: set[str] | None = None):
                seen = set() if seen is None else seen
                if event_id in seen or event_id not in rows:
                    return []
                seen.add(event_id)
                event = rows[event_id]
                branch_id = event.get("branch_id")
                branch = branches.get(branch_id, {})
                own = [candidate for candidate in history[:history_index[event_id] + 1]
                       if candidate.get("branch_id") == branch_id]
                anchor_id = branch.get("anchor_id")
                prefix = path_to_event(anchor_id, seen) if anchor_id else []
                return prefix + own

            active_branch = branches.get(active, {})
            anchor_id = active_branch.get("anchor_id")
            prefix = path_to_event(anchor_id) if anchor_id else []
            events = prefix + [event for event in history if event.get("branch_id") == active]
            unique = {}
            for event in events:
                unique[event.get("id")] = event
            events = list(unique.values())
            description = f"branch {active}"
        if not events:
            self.status.setText("The selection and active branch contain no exportable events.")
            return
        repetitions, okay = QInputDialog.getInt(self, "MIDI loop export", f"Number of passes for {description} (1 exports once):", 1, 1, 1000)
        if not okay:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export selected chords", str(ROOT / "selection.mid"), "MIDI (*.mid)")
        if not path:
            return
        override = None
        if self.override.isChecked():
            answer = QMessageBox.question(self, "Export timing", "Use current live hold, gap and velocity overrides?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                draft = self._read_draft(); override = {"hold": draft.hold, "silence": draft.silence, "velocity": draft.velocity}
        try:
            self._io_task("export", path, export_midi, path, events, repetitions, override, self.channel.value()-1)
        except (OSError, ValueError, TypeError) as exc:
            self.status.setText(f"Export failed · {exc}")

    def closeEvent(self, event: QCloseEvent):
        self.worker.command("stop")
        try:
            self.worker.close(timeout=5)
            self.autosave_timer.stop()
            self._autosave_tick(force=True)
            self._io_pool.shutdown(wait=False, cancel_futures=False)
            event.accept()
        except TimeoutError:
            QMessageBox.warning(self, "Playback still active", "The playback worker did not stop yet.")
            event.ignore()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="Start with silent preview transport")
    parser.add_argument("--close-after-ms", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--screenshot", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(Path(tempfile.gettempdir()) / "GlitteringStars.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "Glittering Stars is open", "Only one Glittering Stars playback app can run at a time.")
        return 2
    try:
        config = read_config()
    except (OSError, ValueError, TypeError) as exc:
        QMessageBox.critical(None, "Settings error", f"Could not read settings.json: {exc}")
        return 1
    window = MainWindow(config, preview=True)
    window.show()
    QTimer.singleShot(800, window._offer_autosave_recovery)
    if args.screenshot:
        def capture():
            window.grab().save(args.screenshot)
            window.close()
        QTimer.singleShot(600, capture)
    if args.close_after_ms is not None:
        QTimer.singleShot(args.close_after_ms, window.close)
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
