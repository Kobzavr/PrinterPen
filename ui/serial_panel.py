"""
serial_panel.py — Bottom dock panel for USB connection and G-code streaming.

Serial communication runs in a background worker thread.
UI updates are handled via Qt Queued Signals to guarantee thread safety.
"""
from __future__ import annotations
from typing import Optional, List, Callable

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QGroupBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QSize
from PyQt5.QtGui import QColor

from core.serial_sender import SerialSender, list_ports, find_printer_port
from core.canvas_model import PrinterSettings
from core.i18n import tr, register_listener
from ui.icons import get_icon


class SerialPanel(QWidget):
    """
    Bottom panel managing USB printer connection and G-code streaming.

    Uses internal signals (_sig_*) for thread-safe cross-thread UI updates:
    the worker thread calls signal.emit(), which Qt queues to the GUI thread.
    """

    compile_requested = pyqtSignal()
    print_started = pyqtSignal()
    print_finished = pyqtSignal(bool)

    # Internal signals for worker thread -> main thread marshaling
    _sig_progress = pyqtSignal(int, int)    # (current, total)
    _sig_log = pyqtSignal(str)              # message
    _sig_done = pyqtSignal(bool)            # success

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumHeight(200)
        self._sender: Optional[SerialSender] = None
        self._gcode_lines: List[str] = []
        self._total_cmds = 0
        self._total_est_seconds: float = 0.0
        self._connected_port: Optional[str] = None
        self._settings_provider: Optional[Callable[[], PrinterSettings]] = None
        self._gcode_provider: Optional[Callable[[], List[str]]] = None
        self._is_custom_gcode: bool = False

        self._init_ui()
        self._connect_internal_signals()
        register_listener(self.retranslate_ui)

    def set_settings_provider(self, provider: Callable[[], PrinterSettings]):
        """Sets a callback returning active PrinterSettings."""
        self._settings_provider = provider

    def set_gcode_provider(self, provider: Callable[[], List[str]]):
        """Sets a callback that generates fresh G-code lines right before printing."""
        self._gcode_provider = provider

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # ── Left: Status & Controls ───────────────────────────────
        left = QVBoxLayout()

        self.lbl_status = QLabel(f"● {tr('status_not_connected')}")
        self.lbl_status.setStyleSheet("color: #e53935; font-weight: bold;")
        left.addWidget(self.lbl_status)

        conn_row = QHBoxLayout()
        self.btn_connect = QPushButton(tr("btn_connect"))
        self.btn_connect.clicked.connect(self._on_connect)
        self.btn_disconnect = QPushButton(tr("btn_disconnect"))
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        self.btn_disconnect.setEnabled(False)
        conn_row.addWidget(self.btn_connect)
        conn_row.addWidget(self.btn_disconnect)
        left.addLayout(conn_row)

        print_row = QHBoxLayout()
        self.btn_compile = QPushButton(tr("btn_compile_gcode"))
        self.btn_compile.setIcon(get_icon("compile"))
        self.btn_compile.setIconSize(QSize(16, 16))
        self.btn_compile.setToolTip(tr("tip_compile_gcode"))
        self.btn_compile.clicked.connect(self._on_compile)

        self.btn_print = QPushButton(tr("btn_print"))
        self.btn_print.setIcon(get_icon("play"))
        self.btn_print.setIconSize(QSize(16, 16))
        self.btn_print.setEnabled(False)
        self.btn_print.clicked.connect(self._on_start_print)

        self.btn_pause = QPushButton(tr("btn_pause"))
        self.btn_pause.setIcon(get_icon("pause"))
        self.btn_pause.setIconSize(QSize(16, 16))
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._on_pause)

        self.btn_stop = QPushButton(tr("btn_stop"))
        self.btn_stop.setIcon(get_icon("stop"))
        self.btn_stop.setIconSize(QSize(16, 16))
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("background-color: #e53935; color: white;")
        self.btn_stop.clicked.connect(self._on_stop)

        print_row.addWidget(self.btn_compile)
        print_row.addWidget(self.btn_print)
        print_row.addWidget(self.btn_pause)
        print_row.addWidget(self.btn_stop)
        left.addLayout(print_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.lbl_progress = QLabel(tr("lbl_progress_initial"))

        prog_info = QHBoxLayout()
        prog_info.addWidget(self.lbl_progress)
        prog_info.addStretch()

        left.addWidget(self.progress)
        left.addLayout(prog_info)

        layout.addLayout(left, 1)

        # ── Right: Serial Log ─────────────────────────────────────
        self.log_group = QGroupBox(tr("group_log"))
        log_layout = QVBoxLayout(self.log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        log_layout.addWidget(self.log_text)
        layout.addWidget(self.log_group, 2)

    def _connect_internal_signals(self):
        self._sig_progress.connect(self._slot_progress)
        self._sig_log.connect(self._slot_log)
        self._sig_done.connect(self._slot_done)

    # ── Public API ────────────────────────────────────────────

    @staticmethod
    def _format_time(sec: float) -> str:
        """Formats duration into human-friendly string (e.g. '2:34 min', '1h 05m', '45s')."""
        sec = max(0.0, sec)
        if sec >= 3600:
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            return f"{h}h {m:02d}m"
        elif sec >= 60:
            m = int(sec // 60)
            s = int(sec % 60)
            return f"{m}:{s:02d} min"
        else:
            return f"{int(sec)}s"

    def _estimate_time_from_lines(self, lines: List[str]) -> float:
        """Fallback estimator parsing G0/G1 travel and draw moves from raw G-code lines."""
        import re, math
        cur_x, cur_y, cur_z = 0.0, 0.0, 0.0
        cur_f = 1500.0  # default feedrate mm/min
        total_time_sec = 0.0

        for line in lines:
            line = line.strip()
            if not line or line.startswith(";"):
                continue

            mf = re.search(r"[Ff]([-+]?\d*\.?\d+)", line)
            if mf:
                cur_f = max(100.0, float(mf.group(1)))

            if line.startswith(("G0 ", "G0\t", "G1 ", "G1\t", "G00 ", "G01 ")):
                mx = re.search(r"[Xx]([-+]?\d*\.?\d+)", line)
                my = re.search(r"[Yy]([-+]?\d*\.?\d+)", line)
                mz = re.search(r"[Zz]([-+]?\d*\.?\d+)", line)

                nx = float(mx.group(1)) if mx else cur_x
                ny = float(my.group(1)) if my else cur_y
                nz = float(mz.group(1)) if mz else cur_z

                dx = nx - cur_x
                dy = ny - cur_y
                dz = nz - cur_z
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dist > 0:
                    total_time_sec += dist / (cur_f / 60.0)

                cur_x, cur_y, cur_z = nx, ny, nz

        return total_time_sec

    def set_estimated_time(self, seconds: float):
        """Deprecated: estimated time display removed as inaccurate."""
        pass

    def set_gcode(self, lines: List[str], est_time_sec: Optional[float] = None, is_custom: bool = False):
        """Sets G-code lines for transmission and updates command count display."""
        self._gcode_lines = lines
        self._is_custom_gcode = is_custom
        total = sum(1 for l in lines if l.strip() and not l.strip().startswith(";"))
        self._total_cmds = total
        self.btn_print.setEnabled(
            self._sender is not None and self._sender.is_connected
        )
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(0)
        self.lbl_progress.setText(tr("lbl_progress_format", current=0, total=total, percent=0))
        self._log(f"G-code loaded: {total} commands")

    # ── Internal Slots (executed on main GUI thread) ──────────

    @pyqtSlot(int, int)
    def _slot_progress(self, current: int, total: int):
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(current)
        pct = int((current / max(1, total)) * 100) if total > 0 else 0
        self.lbl_progress.setText(tr("lbl_progress_format", current=current, total=total, percent=pct))

    @pyqtSlot(str)
    def _slot_log(self, message: str):
        self.log_text.append(message)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    @pyqtSlot(bool)
    def _slot_done(self, success: bool):
        self.btn_compile.setEnabled(True)
        self.btn_print.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText(tr("btn_pause"))
        self.btn_pause.setIcon(get_icon("pause"))
        if success:
            self._log("✅ Print job completed successfully!")
            self.progress.setValue(self.progress.maximum())
        else:
            self._log("❌ Print job interrupted or stopped")
        self.print_finished.emit(success)

    def _log(self, message: str):
        """Must only be called from main GUI thread."""
        self.log_text.append(message)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Button Handlers ───────────────────────────────────────

    def _on_connect(self):
        port = None
        baud = 115200
        if self._settings_provider:
            try:
                s = self._settings_provider()
                port = s.port
                baud = s.baudrate
            except Exception:
                pass

        if not port:
            port = find_printer_port()
        if not port:
            ports = list_ports()
            if ports:
                port = ports[0]

        if not port:
            self._log("❌ No printer port found. Please check USB connection.")
            return

        try:
            self._sender = SerialSender(port, baud)
            self._sender.connect()
            self._connected_port = port
            self.lbl_status.setText(f"● {tr('status_connected', port=port)}")
            self.lbl_status.setStyleSheet("color: #43a047; font-weight: bold;")
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            if self._gcode_lines:
                self.btn_print.setEnabled(True)
            self._log(f"✅ Connected: {port} @ {baud}")
        except ConnectionError as e:
            self._log(f"❌ {e}")

    def _on_disconnect(self):
        if self._sender:
            self._sender.disconnect()
            self._sender = None
        self._connected_port = None
        self.lbl_status.setText(f"● {tr('status_not_connected')}")
        self.lbl_status.setStyleSheet("color: #e53935; font-weight: bold;")
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.btn_print.setEnabled(False)
        self._log("🔌 Disconnected")

    def _on_start_print(self):
        if not self._sender or not self._sender.is_connected:
            return

        if self._gcode_provider and not self._is_custom_gcode:
            try:
                fresh_lines = self._gcode_provider()
                if fresh_lines:
                    self.set_gcode(fresh_lines)
            except Exception as e:
                self._log(f"❌ Error generating G-code: {e}")

        # Reset custom flag once print job starts
        self._is_custom_gcode = False

        if not self._gcode_lines:
            return

        self.btn_compile.setEnabled(False)
        self.btn_print.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.progress.setValue(0)
        self.print_started.emit()

        z_info = ""
        if self._settings_provider:
            try:
                s = self._settings_provider()
                z_info = f" (Z draw: {s.z_down:.2f} mm [fine-tune: {s.z_draw_offset:+.2f} mm], Z lift: {s.z_up:.2f} mm)"
            except Exception:
                pass
        self._log(f"▶ Streaming G-code{z_info}...")

        self._sender.send_gcode(
            self._gcode_lines,
            on_progress=self._sig_progress.emit,
            on_log=self._sig_log.emit,
            on_finished=self._sig_done.emit,
        )

    def _on_pause(self):
        if not self._sender:
            return
        if self._sender._paused:
            self._sender.resume()
            self.btn_pause.setText(tr("btn_pause"))
            self.btn_pause.setIcon(get_icon("pause"))
            self._log("▶ Resumed")
        else:
            self._sender.pause()
            self.btn_pause.setText(tr("btn_resume"))
            self.btn_pause.setIcon(get_icon("play"))
            self._log("⏸ Paused")

    def _on_stop(self):
        if self._sender:
            z_up = 4.0
            feed = 3000.0
            if self._settings_provider:
                try:
                    s = self._settings_provider()
                    z_up = s.z_up
                    feed = s.feed_travel
                except Exception:
                    pass
            self._sender.stop(z_up=z_up, feed=feed)
        self._log("⏹ Stop signal sent...")

    def _on_compile(self):
        """Emits signal to trigger on-demand G-code compilation and command count calculation."""
        self.compile_requested.emit()

    # ── Retranslate UI ────────────────────────────────────────

    def retranslate_ui(self):
        if self._connected_port:
            self.lbl_status.setText(f"● {tr('status_connected', port=self._connected_port)}")
        else:
            self.lbl_status.setText(f"● {tr('status_not_connected')}")

        self.btn_connect.setText(tr("btn_connect"))
        self.btn_disconnect.setText(tr("btn_disconnect"))
        self.btn_compile.setText(tr("btn_compile_gcode"))
        self.btn_compile.setToolTip(tr("tip_compile_gcode"))
        self.btn_print.setText(tr("btn_print"))
        if self._sender and self._sender._paused:
            self.btn_pause.setText(tr("btn_resume"))
            self.btn_pause.setIcon(get_icon("play"))
        else:
            self.btn_pause.setText(tr("btn_pause"))
            self.btn_pause.setIcon(get_icon("pause"))
        self.btn_stop.setText(tr("btn_stop"))
        self.log_group.setTitle(tr("group_log"))
