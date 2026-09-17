"""
settings_dialog.py — Printer settings dialog.

Tabs:
  1. General & Pen: Machine dimensions, pen offsets, Z-height, pen tip diameter, speeds.
  2. Custom G-code: User-editable G-code Header and Footer templates with format variables.
  3. Connection: Serial COM port and baud rate selection.
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QDoubleSpinBox,
    QSpinBox, QLineEdit, QGroupBox, QVBoxLayout, QComboBox,
    QLabel, QPushButton, QHBoxLayout, QFrame, QTabWidget,
    QWidget, QPlainTextEdit, QScrollArea, QCheckBox,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont

from core.canvas_model import PrinterSettings, DEFAULT_GCODE_HEADER, DEFAULT_GCODE_FOOTER
from core.serial_sender import list_ports, find_printer_port
from core.i18n import tr, register_listener
from ui.icons import get_icon


def _make_readonly_label(text: str = "—") -> QLabel:
    """Creates a read-only styled QLabel mimicking a disabled text input."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "background: #1e1e1e; border: 1px solid #444; border-radius: 3px; "
        "padding: 3px 6px; color: #4fc3f7; font-family: Consolas;"
    )
    return lbl


class SettingsDialog(QDialog):
    """Printer configuration dialog."""

    def __init__(self, settings: PrinterSettings, parent=None):
        super().__init__(parent)
        # Remove context help button (?) from title bar
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle(tr("settings_title"))
        self.setMinimumSize(540, 620)
        self._settings = settings

        self._init_ui()
        self._load_values()
        self._update_derived()
        register_listener(self.retranslate_ui)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        self._tabs = QTabWidget()
        main_layout.addWidget(self._tabs)

        # ── Tab 1: General & Pen ──────────────────────────────────
        tab_general = QWidget()
        tab_gen_scroll = QScrollArea()
        tab_gen_scroll.setWidgetResizable(True)
        tab_gen_scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        gen_layout = QVBoxLayout(scroll_content)
        gen_layout.setSpacing(10)

        # Physical Printer Area
        self.grp_printer_area = QGroupBox(tr("group_printer_area"))
        pf = QFormLayout(self.grp_printer_area)
        self.sb_printer_w = QDoubleSpinBox()
        self.sb_printer_w.setRange(50, 1000)
        self.sb_printer_w.setSuffix(f" {tr('unit_mm')}")
        self.sb_printer_w.setDecimals(1)
        self.sb_printer_w.setToolTip(tr("tip_printer_w"))
        self.sb_printer_w.valueChanged.connect(self._update_derived)
        self.lbl_printer_w_title = QLabel(tr("lbl_printer_w"))
        pf.addRow(self.lbl_printer_w_title, self.sb_printer_w)

        self.sb_printer_h = QDoubleSpinBox()
        self.sb_printer_h.setRange(50, 1000)
        self.sb_printer_h.setSuffix(f" {tr('unit_mm')}")
        self.sb_printer_h.setDecimals(1)
        self.sb_printer_h.setToolTip(tr("tip_printer_h"))
        self.sb_printer_h.valueChanged.connect(self._update_derived)
        self.lbl_printer_h_title = QLabel(tr("lbl_printer_h"))
        pf.addRow(self.lbl_printer_h_title, self.sb_printer_h)
        gen_layout.addWidget(self.grp_printer_area)

        # Pen Offset
        self.grp_pen_offset = QGroupBox(tr("group_pen_offset"))
        of = QFormLayout(self.grp_pen_offset)
        self.lbl_offset_desc = QLabel(tr("offset_description"))
        self.lbl_offset_desc.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_offset_desc.setWordWrap(True)
        of.addRow(self.lbl_offset_desc)

        self.sb_offset_x = QDoubleSpinBox()
        self.sb_offset_x.setRange(-300, 300)
        self.sb_offset_x.setSuffix(f" {tr('unit_mm')}")
        self.sb_offset_x.setDecimals(2)
        self.sb_offset_x.setToolTip(tr("tip_offset_x"))
        self.sb_offset_x.valueChanged.connect(self._update_derived)
        self.lbl_offset_x_title = QLabel(tr("lbl_offset_x"))
        of.addRow(self.lbl_offset_x_title, self.sb_offset_x)

        self.sb_offset_y = QDoubleSpinBox()
        self.sb_offset_y.setRange(-300, 300)
        self.sb_offset_y.setSuffix(f" {tr('unit_mm')}")
        self.sb_offset_y.setDecimals(2)
        self.sb_offset_y.setToolTip(tr("tip_offset_y"))
        self.sb_offset_y.valueChanged.connect(self._update_derived)
        self.lbl_offset_y_title = QLabel(tr("lbl_offset_y"))
        of.addRow(self.lbl_offset_y_title, self.sb_offset_y)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("color: #444;")
        of.addRow(sep1)

        self.lbl_calc_canvas_title = QLabel(tr("lbl_calc_canvas"))
        self.lbl_canvas_size = _make_readonly_label()
        of.addRow(self.lbl_calc_canvas_title, self.lbl_canvas_size)
        gen_layout.addWidget(self.grp_pen_offset)

        # Z-Axis and Pen Tip
        self.grp_z_axis = QGroupBox(tr("group_z_axis"))
        zf = QFormLayout(self.grp_z_axis)

        self.sb_pen_z_offset = QDoubleSpinBox()
        self.sb_pen_z_offset.setRange(0, 30)
        self.sb_pen_z_offset.setSuffix(f" {tr('unit_mm')}")
        self.sb_pen_z_offset.setDecimals(2)
        self.sb_pen_z_offset.setToolTip(tr("tip_pen_z_offset"))
        self.sb_pen_z_offset.valueChanged.connect(self._update_derived)
        self.lbl_pen_z_offset_title = QLabel(tr("lbl_pen_z_offset"))
        zf.addRow(self.lbl_pen_z_offset_title, self.sb_pen_z_offset)

        self.sb_z_draw_offset = QDoubleSpinBox()
        self.sb_z_draw_offset.setRange(-2.0, 5.0)
        self.sb_z_draw_offset.setSuffix(f" {tr('unit_mm')}")
        self.sb_z_draw_offset.setDecimals(2)
        self.sb_z_draw_offset.setSingleStep(0.1)
        self.sb_z_draw_offset.setToolTip(tr("tip_z_draw_offset"))
        self.sb_z_draw_offset.valueChanged.connect(self._update_derived)
        self.lbl_z_draw_offset_title = QLabel(tr("lbl_z_draw_offset"))
        zf.addRow(self.lbl_z_draw_offset_title, self.sb_z_draw_offset)

        self.sb_z_lift = QDoubleSpinBox()
        self.sb_z_lift.setRange(0.1, 20)
        self.sb_z_lift.setSuffix(f" {tr('unit_mm')}")
        self.sb_z_lift.setDecimals(2)
        self.sb_z_lift.setToolTip(tr("tip_z_lift"))
        self.sb_z_lift.valueChanged.connect(self._update_derived)
        self.lbl_z_lift_title = QLabel(tr("lbl_z_lift"))
        zf.addRow(self.lbl_z_lift_title, self.sb_z_lift)

        self.sb_pen_width = QDoubleSpinBox()
        self.sb_pen_width.setRange(0.1, 5.0)
        self.sb_pen_width.setSuffix(f" {tr('unit_mm')}")
        self.sb_pen_width.setDecimals(2)
        self.sb_pen_width.setSingleStep(0.05)
        self.sb_pen_width.setToolTip(tr("tip_pen_width"))
        self.lbl_pen_width_title = QLabel(tr("lbl_pen_width"))
        zf.addRow(self.lbl_pen_width_title, self.sb_pen_width)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #444;")
        zf.addRow(sep2)

        self.lbl_calc_z_down_title = QLabel(tr("lbl_calc_z_down"))
        self.lbl_z_down = _make_readonly_label()
        zf.addRow(self.lbl_calc_z_down_title, self.lbl_z_down)

        self.lbl_calc_z_up_title = QLabel(tr("lbl_calc_z_up"))
        self.lbl_z_up = _make_readonly_label()
        zf.addRow(self.lbl_calc_z_up_title, self.lbl_z_up)
        gen_layout.addWidget(self.grp_z_axis)

        # Orientation
        self.grp_orient = QGroupBox(tr("group_orientation"))
        orient_layout = QVBoxLayout(self.grp_orient)
        self.cb_invert_y = QCheckBox(tr("chk_invert_y"))
        self.cb_invert_y.setToolTip(tr("tip_invert_y"))
        orient_layout.addWidget(self.cb_invert_y)
        gen_layout.addWidget(self.grp_orient)

        # Speeds
        self.grp_speeds = QGroupBox(tr("group_speeds"))
        sf = QFormLayout(self.grp_speeds)

        row_travel = QHBoxLayout()
        self.sb_feed_travel = QDoubleSpinBox()
        self.sb_feed_travel.setRange(100, 15000)
        self.sb_feed_travel.setSuffix(f" {tr('unit_mm')}/min")
        self.sb_feed_travel.setDecimals(0)
        self.sb_feed_travel.valueChanged.connect(self._update_derived)
        self.lbl_travel_mms = QLabel()
        self.lbl_travel_mms.setStyleSheet("color: #888; font-size: 11px;")
        row_travel.addWidget(self.sb_feed_travel)
        row_travel.addWidget(self.lbl_travel_mms)
        row_travel.addStretch()
        self.lbl_speed_travel_title = QLabel(tr("lbl_speed_travel"))
        sf.addRow(self.lbl_speed_travel_title, row_travel)

        row_draw = QHBoxLayout()
        self.sb_feed_draw = QDoubleSpinBox()
        self.sb_feed_draw.setRange(100, 10000)
        self.sb_feed_draw.setSuffix(f" {tr('unit_mm')}/min")
        self.sb_feed_draw.setDecimals(0)
        self.sb_feed_draw.valueChanged.connect(self._update_derived)
        self.lbl_draw_mms = QLabel()
        self.lbl_draw_mms.setStyleSheet("color: #888; font-size: 11px;")
        row_draw.addWidget(self.sb_feed_draw)
        row_draw.addWidget(self.lbl_draw_mms)
        row_draw.addStretch()
        self.lbl_speed_draw_title = QLabel(tr("lbl_speed_draw"))
        sf.addRow(self.lbl_speed_draw_title, row_draw)
        gen_layout.addWidget(self.grp_speeds)

        tab_gen_scroll.setWidget(scroll_content)
        t1_layout = QVBoxLayout(tab_general)
        t1_layout.setContentsMargins(0, 0, 0, 0)
        t1_layout.addWidget(tab_gen_scroll)
        self._tabs.addTab(tab_general, tr("tab_general"))

        # ── Tab 2: Custom G-code ──────────────────────────────────
        tab_gcode = QWidget()
        gcode_layout = QVBoxLayout(tab_gcode)
        gcode_layout.setSpacing(8)

        self.grp_custom_gcode = QGroupBox(tr("group_custom_gcode"))
        cg_layout = QVBoxLayout(self.grp_custom_gcode)

        self.lbl_vars_hint = QLabel(tr("gcode_variables_hint"))
        self.lbl_vars_hint.setStyleSheet("color: #81d4fa; font-size: 11px; font-family: Consolas;")
        self.lbl_vars_hint.setWordWrap(True)
        cg_layout.addWidget(self.lbl_vars_hint)

        self.lbl_gcode_hdr = QLabel(tr("lbl_gcode_header"))
        cg_layout.addWidget(self.lbl_gcode_hdr)
        self.txt_gcode_header = QPlainTextEdit()
        self.txt_gcode_header.setFont(QFont("Consolas", 9))
        self.txt_gcode_header.setMaximumHeight(140)
        cg_layout.addWidget(self.txt_gcode_header)

        self.lbl_gcode_ftr = QLabel(tr("lbl_gcode_footer"))
        cg_layout.addWidget(self.lbl_gcode_ftr)
        self.txt_gcode_footer = QPlainTextEdit()
        self.txt_gcode_footer.setFont(QFont("Consolas", 9))
        self.txt_gcode_footer.setMaximumHeight(140)
        cg_layout.addWidget(self.txt_gcode_footer)

        btn_reset_row = QHBoxLayout()
        self.btn_reset_gcode = QPushButton(tr("btn_reset_gcode"))
        self.btn_reset_gcode.clicked.connect(self._reset_gcode_templates)
        btn_reset_row.addStretch()
        btn_reset_row.addWidget(self.btn_reset_gcode)
        cg_layout.addLayout(btn_reset_row)

        gcode_layout.addWidget(self.grp_custom_gcode)
        self._tabs.addTab(tab_gcode, tr("tab_gcode"))

        # ── Tab 3: Connection ─────────────────────────────────────
        tab_conn = QWidget()
        conn_layout = QVBoxLayout(tab_conn)
        conn_layout.setSpacing(10)

        conn_group = QGroupBox(tr("tab_connection"))
        cf = QFormLayout(conn_group)

        port_row = QHBoxLayout()
        self.cb_port = QComboBox()
        self.cb_port.setEditable(True)
        self.cb_port.setMinimumWidth(120)
        self.btn_refresh = QPushButton()
        self.btn_refresh.setObjectName("btnRefresh")
        self.btn_refresh.setIcon(get_icon("refresh"))
        self.btn_refresh.setIconSize(QSize(16, 16))
        self.btn_refresh.setFixedSize(28, 26)
        self.btn_refresh.setToolTip(tr("btn_refresh_tip"))
        self.btn_refresh.clicked.connect(self._refresh_ports)
        port_row.addWidget(self.cb_port)
        port_row.addWidget(self.btn_refresh)
        self.lbl_port_title = QLabel(tr("lbl_port"))
        cf.addRow(self.lbl_port_title, port_row)

        self.sb_baud = QSpinBox()
        self.sb_baud.setRange(9600, 250000)
        self.sb_baud.setSingleStep(9600)
        self.lbl_baud_title = QLabel(tr("lbl_baudrate"))
        cf.addRow(self.lbl_baud_title, self.sb_baud)

        conn_layout.addWidget(conn_group)
        conn_layout.addStretch()
        self._tabs.addTab(tab_conn, tr("tab_connection"))

        # ── Buttons ───────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self,
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        self._refresh_ports()

    def _reset_gcode_templates(self):
        self.txt_gcode_header.setPlainText(DEFAULT_GCODE_HEADER)
        self.txt_gcode_footer.setPlainText(DEFAULT_GCODE_FOOTER)

    def _refresh_ports(self):
        self.cb_port.clear()
        ports = list_ports()
        self.cb_port.addItems(ports)
        auto = find_printer_port()
        if auto and auto in ports:
            self.cb_port.setCurrentText(auto)
        elif self._settings.port:
            self.cb_port.setCurrentText(self._settings.port)

    def _load_values(self):
        self.sb_printer_w.setValue(self._settings.printer_max_w)
        self.sb_printer_h.setValue(self._settings.printer_max_h)
        self.sb_offset_x.setValue(self._settings.offset_x)
        self.sb_offset_y.setValue(self._settings.offset_y)
        self.sb_pen_z_offset.setValue(self._settings.pen_z_offset)
        self.sb_z_draw_offset.setValue(self._settings.z_draw_offset)
        self.sb_z_lift.setValue(self._settings.z_lift)
        self.sb_pen_width.setValue(self._settings.pen_width)
        self.cb_invert_y.setChecked(self._settings.invert_y)
        self.sb_feed_travel.setValue(self._settings.feed_travel)
        self.sb_feed_draw.setValue(self._settings.feed_draw)
        self.sb_baud.setValue(self._settings.baudrate)

        hdr = self._settings.gcode_header if self._settings.gcode_header else DEFAULT_GCODE_HEADER
        ftr = self._settings.gcode_footer if self._settings.gcode_footer else DEFAULT_GCODE_FOOTER
        self.txt_gcode_header.setPlainText(hdr)
        self.txt_gcode_footer.setPlainText(ftr)

    def _update_derived(self):
        printer_w = self.sb_printer_w.value()
        printer_h = self.sb_printer_h.value()
        ox = self.sb_offset_x.value()
        oy = self.sb_offset_y.value()
        pen_z = self.sb_pen_z_offset.value()
        z_draw_off = self.sb_z_draw_offset.value()
        z_lift = self.sb_z_lift.value()

        canvas_w = max(0.0, printer_w - abs(ox))
        canvas_h = max(0.0, printer_h - abs(oy))
        z_down = pen_z + z_draw_off
        z_up = pen_z + z_draw_off + z_lift

        self.lbl_canvas_size.setText(f"{canvas_w:.1f} × {canvas_h:.1f} {tr('unit_mm')}")

        if z_draw_off > 0:
            pressure_hint = f"(+{z_draw_off:.2f} mm gentle)"
        elif z_draw_off < 0:
            pressure_hint = f"({z_draw_off:.2f} mm firm)"
        else:
            pressure_hint = "(exact contact)"
        self.lbl_z_down.setText(f"{z_down:.2f} mm  {pressure_hint}")
        self.lbl_z_up.setText(f"{z_up:.2f} mm  (lifted)")

        t_mms = self.sb_feed_travel.value() / 60.0
        d_mms = self.sb_feed_draw.value() / 60.0
        self.lbl_travel_mms.setText(f"(≈ {t_mms:.1f} {tr('unit_mm')}/s)")
        self.lbl_draw_mms.setText(f"(≈ {d_mms:.1f} {tr('unit_mm')}/s)")

    def _on_ok(self):
        self._settings.printer_max_w = self.sb_printer_w.value()
        self._settings.printer_max_h = self.sb_printer_h.value()
        self._settings.offset_x = self.sb_offset_x.value()
        self._settings.offset_y = self.sb_offset_y.value()
        self._settings.pen_z_offset = self.sb_pen_z_offset.value()
        self._settings.z_draw_offset = self.sb_z_draw_offset.value()
        self._settings.z_lift = self.sb_z_lift.value()
        self._settings.pen_width = self.sb_pen_width.value()
        self._settings.invert_y = self.cb_invert_y.isChecked()
        self._settings.feed_travel = self.sb_feed_travel.value()
        self._settings.feed_draw = self.sb_feed_draw.value()
        self._settings.port = self.cb_port.currentText()
        self._settings.baudrate = self.sb_baud.value()
        self._settings.gcode_header = self.txt_gcode_header.toPlainText()
        self._settings.gcode_footer = self.txt_gcode_footer.toPlainText()
        self.accept()

    def get_settings(self) -> PrinterSettings:
        return self._settings

    def retranslate_ui(self):
        self.setWindowTitle(tr("settings_title"))
        self._tabs.setTabText(0, tr("tab_general"))
        self._tabs.setTabText(1, tr("tab_gcode"))
        self._tabs.setTabText(2, tr("tab_connection"))

        mm_suf = f" {tr('unit_mm')}"
        self.grp_printer_area.setTitle(tr("group_printer_area"))
        self.lbl_printer_w_title.setText(tr("lbl_printer_w"))
        self.lbl_printer_h_title.setText(tr("lbl_printer_h"))
        self.sb_printer_w.setSuffix(mm_suf)
        self.sb_printer_h.setSuffix(mm_suf)

        self.grp_pen_offset.setTitle(tr("group_pen_offset"))
        self.lbl_offset_desc.setText(tr("offset_description"))
        self.lbl_offset_x_title.setText(tr("lbl_offset_x"))
        self.lbl_offset_y_title.setText(tr("lbl_offset_y"))
        self.sb_offset_x.setSuffix(mm_suf)
        self.sb_offset_y.setSuffix(mm_suf)
        self.lbl_calc_canvas_title.setText(tr("lbl_calc_canvas"))

        self.grp_z_axis.setTitle(tr("group_z_axis"))
        self.lbl_pen_z_offset_title.setText(tr("lbl_pen_z_offset"))
        self.lbl_z_draw_offset_title.setText(tr("lbl_z_draw_offset"))
        self.lbl_z_lift_title.setText(tr("lbl_z_lift"))
        self.lbl_pen_width_title.setText(tr("lbl_pen_width"))
        self.sb_pen_z_offset.setSuffix(mm_suf)
        self.sb_z_draw_offset.setSuffix(mm_suf)
        self.sb_z_lift.setSuffix(mm_suf)
        self.sb_pen_width.setSuffix(mm_suf)
        self.lbl_calc_z_down_title.setText(tr("lbl_calc_z_down"))
        self.lbl_calc_z_up_title.setText(tr("lbl_calc_z_up"))

        self.grp_orient.setTitle(tr("group_orientation"))
        self.cb_invert_y.setText(tr("chk_invert_y"))

        self.grp_speeds.setTitle(tr("group_speeds"))
        self.lbl_speed_travel_title.setText(tr("lbl_speed_travel"))
        self.lbl_speed_draw_title.setText(tr("lbl_speed_draw"))
        self.sb_feed_travel.setSuffix(f" {tr('unit_mm')}/min")
        self.sb_feed_draw.setSuffix(f" {tr('unit_mm')}/min")

        self.grp_custom_gcode.setTitle(tr("group_custom_gcode"))
        self.lbl_vars_hint.setText(tr("gcode_variables_hint"))
        self.lbl_gcode_hdr.setText(tr("lbl_gcode_header"))
        self.lbl_gcode_ftr.setText(tr("lbl_gcode_footer"))
        self.btn_reset_gcode.setText(tr("btn_reset_gcode"))

        self.lbl_port_title.setText(tr("lbl_port"))
        self.lbl_baud_title.setText(tr("lbl_baudrate"))
        self.btn_refresh.setToolTip(tr("btn_refresh_tip"))

        self._update_derived()
