"""
properties_panel.py — Properties panel for the selected canvas item.

Stack pages:
  0 — Empty (no selection)
  1 — TextItem (text content, font family, bold/italic, pos, rot, scale)
  2 — SvgItem (pos, rot, scale)
  3 — RasterItem (pos, rot, scale, Canny edge detection sliders + auto-debounce)
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QDoubleSpinBox,
    QGroupBox, QSlider, QCheckBox, QPushButton, QStackedWidget,
    QLineEdit, QFontComboBox, QMessageBox, QComboBox, QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QFont

from core.i18n import tr, register_listener
from core.font_manager import PlotterFontComboBox, FontManager
from ui.icons import get_icon

if TYPE_CHECKING:
    from ui.canvas_items import BasePlotItem, TextItem, SvgItem, RasterItem


class DynamicStackedWidget(QStackedWidget):
    """QStackedWidget that reports sizeHint and minimumSizeHint based only on the current visible page."""

    def sizeHint(self):
        current = self.currentWidget()
        if current:
            return current.sizeHint()
        return super().sizeHint()

    def minimumSizeHint(self):
        current = self.currentWidget()
        if current:
            return current.minimumSizeHint()
        return super().minimumSizeHint()


class PropertiesPanel(QWidget):
    """Properties panel displaying and editing properties of the selected canvas item."""

    item_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self._current_item: Optional["BasePlotItem"] = None
        self._updating = False

        # Debounce timer for Canny auto-retrace (fires 500ms after user stops moving sliders)
        self._retrace_timer = QTimer()
        self._retrace_timer.setSingleShot(True)
        self._retrace_timer.setInterval(500)
        self._retrace_timer.timeout.connect(self._on_retrace)

        self._init_ui()
        register_listener(self.retranslate_ui)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 4)
        layout.setSpacing(2)

        self.lbl_panel_title = QLabel(tr("prop_title"))
        self.lbl_panel_title.setAlignment(Qt.AlignCenter)
        self.lbl_panel_title.setStyleSheet("font-weight: bold; font-size: 12px; margin: 0px; padding: 0px;")
        layout.addWidget(self.lbl_panel_title)

        # Status / Item Mode Bar (Lock & Hide)
        self.item_toolbar = QWidget()
        tb_layout = QHBoxLayout(self.item_toolbar)
        tb_layout.setContentsMargins(6, 4, 6, 4)
        tb_layout.setSpacing(10)

        self.chk_lock = QCheckBox(tr("chk_lock"))
        self.chk_lock.setToolTip(tr("tip_lock"))
        self.chk_lock.toggled.connect(self._on_lock_toggled)

        self.chk_hide = QCheckBox(tr("chk_hide"))
        self.chk_hide.setToolTip(tr("tip_hide"))
        self.chk_hide.toggled.connect(self._on_hide_toggled)

        tb_layout.addWidget(self.chk_lock)
        tb_layout.addWidget(self.chk_hide)
        tb_layout.addStretch()
        self.item_toolbar.setVisible(False)
        layout.addWidget(self.item_toolbar)

        self._scroll_area = QScrollArea()
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._stack = DynamicStackedWidget()
        self._scroll_area.setWidget(self._stack)
        layout.addWidget(self._scroll_area, 1)

        # Page 0: Empty
        self.lbl_empty = QLabel(tr("prop_empty"))
        self.lbl_empty.setAlignment(Qt.AlignCenter)
        self.lbl_empty.setStyleSheet("color: #aaa; padding: 10px;")
        self._stack.addWidget(self.lbl_empty)

        # Page 1: Text
        self._stack.addWidget(self._build_text_page())

        # Page 2: SVG
        self._stack.addWidget(self._build_svg_page())

        # Page 3: Raster
        self._stack.addWidget(self._build_raster_page())

    # ── Page 1: Text ──────────────────────────────────────────

    def _build_text_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignTop)

        self.lbl_type_t = QLabel(tr("prop_type_text"))
        self.lbl_type_t.setStyleSheet("color: #666; font-size: 11px; margin: 0px; padding: 0px;")
        layout.addWidget(self.lbl_type_t)

        # Text input group
        self.grp_text_content = QGroupBox(tr("group_text"))
        tf = QFormLayout(self.grp_text_content)
        tf.setContentsMargins(6, 4, 6, 4)
        tf.setVerticalSpacing(3)

        self.txt_input = QLineEdit()
        self.txt_input.textChanged.connect(self._on_text_content_changed)
        self.lbl_txt_prompt = QLabel(tr("lbl_text"))
        tf.addRow(self.lbl_txt_prompt, self.txt_input)

        self.txt_font_combo = PlotterFontComboBox()
        self.txt_font_combo.currentFontChanged.connect(self._on_text_font_changed)
        self.lbl_txt_font = QLabel(tr("lbl_font"))

        self.btn_open_fonts = QPushButton()
        self.btn_open_fonts.setIcon(get_icon("folder"))
        self.btn_open_fonts.setIconSize(QSize(16, 16))
        self.btn_open_fonts.setObjectName("btnOpenFonts")
        self.btn_open_fonts.setFixedSize(28, 26)
        self.btn_open_fonts.setToolTip(tr("tip_open_fonts"))
        self.btn_open_fonts.clicked.connect(self._on_open_fonts_dir)

        font_row = QHBoxLayout()
        font_row.setContentsMargins(0, 0, 0, 0)
        font_row.setSpacing(4)
        font_row.addWidget(self.txt_font_combo, 1)
        font_row.addWidget(self.btn_open_fonts, 0)
        tf.addRow(self.lbl_txt_font, font_row)

        style_row = QHBoxLayout()
        style_row.setContentsMargins(0, 0, 0, 0)
        style_row.setSpacing(6)
        self.txt_bold = QCheckBox(tr("chk_bold"))
        self.txt_bold.stateChanged.connect(self._on_text_style_changed)
        self.txt_italic = QCheckBox(tr("chk_italic"))
        self.txt_italic.stateChanged.connect(self._on_text_style_changed)
        style_row.addWidget(self.txt_bold)
        style_row.addWidget(self.txt_italic)
        tf.addRow("", style_row)
        layout.addWidget(self.grp_text_content)

        # Position group
        self.grp_t_pos = QGroupBox(tr("group_position"))
        pf = QFormLayout(self.grp_t_pos)
        pf.setContentsMargins(6, 4, 6, 4)
        pf.setVerticalSpacing(2)
        self.t_pos_x = QDoubleSpinBox()
        self.t_pos_x.setRange(-500, 500); self.t_pos_x.setSuffix(f" {tr('unit_mm')}"); self.t_pos_x.setDecimals(1)
        self.t_pos_x.valueChanged.connect(self._on_text_pos_changed)
        pf.addRow("X:", self.t_pos_x)

        self.t_pos_y = QDoubleSpinBox()
        self.t_pos_y.setRange(-500, 500); self.t_pos_y.setSuffix(f" {tr('unit_mm')}"); self.t_pos_y.setDecimals(1)
        self.t_pos_y.valueChanged.connect(self._on_text_pos_changed)
        pf.addRow("Y:", self.t_pos_y)
        layout.addWidget(self.grp_t_pos)

        # Rotation group
        self.grp_t_rot = QGroupBox(tr("group_rotation"))
        rf = QFormLayout(self.grp_t_rot)
        rf.setContentsMargins(6, 4, 6, 4)
        rf.setVerticalSpacing(2)
        self.t_rotation = QDoubleSpinBox()
        self.t_rotation.setRange(-360, 360); self.t_rotation.setSuffix(" °"); self.t_rotation.setDecimals(1)
        self.t_rotation.valueChanged.connect(self._on_text_rot_changed)
        self.lbl_t_angle = QLabel(tr("lbl_angle"))
        rf.addRow(self.lbl_t_angle, self.t_rotation)
        layout.addWidget(self.grp_t_rot)

        # Scale group
        self.grp_t_scale = QGroupBox(tr("group_scale"))
        sf = QFormLayout(self.grp_t_scale)
        sf.setContentsMargins(6, 4, 6, 4)
        sf.setVerticalSpacing(2)
        self.t_scale = QDoubleSpinBox()
        self.t_scale.setRange(0.05, 20.0); self.t_scale.setSingleStep(0.1); self.t_scale.setDecimals(2)
        self.t_scale.valueChanged.connect(self._on_text_scale_changed)
        self.lbl_t_scale = QLabel(tr("lbl_scale"))
        sf.addRow(self.lbl_t_scale, self.t_scale)
        layout.addWidget(self.grp_t_scale)

        # Letter Infill Group
        self.grp_text_infill = QGroupBox(tr("group_text_infill"))
        tif = QVBoxLayout(self.grp_text_infill)
        tif.setContentsMargins(6, 3, 6, 3)
        tif.setSpacing(3)

        self.cb_text_infill = QCheckBox(tr("chk_enable_text_infill"))
        self.cb_text_infill.setChecked(False)
        self.cb_text_infill.stateChanged.connect(self._on_text_infill_changed)
        tif.addWidget(self.cb_text_infill)

        self.text_infill_params = QWidget()
        tpf = QFormLayout(self.text_infill_params)
        tpf.setContentsMargins(0, 2, 0, 2)
        tpf.setVerticalSpacing(2)

        self.cb_text_pattern = QComboBox()
        self.cb_text_pattern.addItem(tr("pattern_linear"), "linear")
        self.cb_text_pattern.addItem(tr("pattern_crosshatch"), "crosshatch")
        self.cb_text_pattern.addItem(tr("pattern_concentric"), "concentric")
        self.cb_text_pattern.addItem(tr("pattern_honeycomb"), "honeycomb")
        self.cb_text_pattern.addItem(tr("pattern_triangles"), "triangles")
        self.cb_text_pattern.currentIndexChanged.connect(self._on_text_infill_changed)
        self.lbl_text_pattern = QLabel(tr("lbl_infill_pattern"))
        tpf.addRow(self.lbl_text_pattern, self.cb_text_pattern)

        self.sb_text_spacing = QDoubleSpinBox()
        self.sb_text_spacing.setRange(0.1, 10.0)
        self.sb_text_spacing.setSingleStep(0.05)
        self.sb_text_spacing.setValue(0.5)
        self.sb_text_spacing.setSuffix(f" {tr('unit_mm')}")
        self.sb_text_spacing.valueChanged.connect(self._on_text_infill_changed)
        self.lbl_text_spacing = QLabel(tr("lbl_infill_spacing"))
        tpf.addRow(self.lbl_text_spacing, self.sb_text_spacing)

        self.sb_text_angle = QDoubleSpinBox()
        self.sb_text_angle.setRange(0, 180)
        self.sb_text_angle.setValue(45)
        self.sb_text_angle.setSuffix(" °")
        self.sb_text_angle.valueChanged.connect(self._on_text_infill_changed)
        self.lbl_text_angle = QLabel(tr("lbl_infill_angle"))
        tpf.addRow(self.lbl_text_angle, self.sb_text_angle)

        self.text_infill_params.setEnabled(False)
        tif.addWidget(self.text_infill_params)
        layout.addWidget(self.grp_text_infill)

        layout.addStretch()
        return page

    # ── Page 2: SVG ───────────────────────────────────────────

    def _build_svg_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignTop)

        self.lbl_type_s = QLabel(tr("prop_type_svg"))
        self.lbl_type_s.setStyleSheet("color: #666; font-size: 11px; margin: 0px; padding: 0px;")
        layout.addWidget(self.lbl_type_s)

        # Position group
        self.grp_s_pos = QGroupBox(tr("group_position"))
        pf = QFormLayout(self.grp_s_pos)
        pf.setContentsMargins(6, 4, 6, 4)
        pf.setVerticalSpacing(2)
        self.s_pos_x = QDoubleSpinBox()
        self.s_pos_x.setRange(-500, 500); self.s_pos_x.setSuffix(f" {tr('unit_mm')}"); self.s_pos_x.setDecimals(1)
        self.s_pos_x.valueChanged.connect(self._on_svg_pos_changed)
        pf.addRow("X:", self.s_pos_x)

        self.s_pos_y = QDoubleSpinBox()
        self.s_pos_y.setRange(-500, 500); self.s_pos_y.setSuffix(f" {tr('unit_mm')}"); self.s_pos_y.setDecimals(1)
        self.s_pos_y.valueChanged.connect(self._on_svg_pos_changed)
        pf.addRow("Y:", self.s_pos_y)
        layout.addWidget(self.grp_s_pos)

        # Rotation group
        self.grp_s_rot = QGroupBox(tr("group_rotation"))
        rf = QFormLayout(self.grp_s_rot)
        rf.setContentsMargins(6, 4, 6, 4)
        rf.setVerticalSpacing(2)
        self.s_rotation = QDoubleSpinBox()
        self.s_rotation.setRange(-360, 360); self.s_rotation.setSuffix(" °"); self.s_rotation.setDecimals(1)
        self.s_rotation.valueChanged.connect(self._on_svg_rot_changed)
        self.lbl_s_angle = QLabel(tr("lbl_angle"))
        rf.addRow(self.lbl_s_angle, self.s_rotation)
        layout.addWidget(self.grp_s_rot)

        # Scale group
        self.grp_s_scale = QGroupBox(tr("group_scale"))
        sf = QFormLayout(self.grp_s_scale)
        sf.setContentsMargins(6, 4, 6, 4)
        sf.setVerticalSpacing(2)
        self.s_scale = QDoubleSpinBox()
        self.s_scale.setRange(0.05, 20.0); self.s_scale.setSingleStep(0.1); self.s_scale.setDecimals(2)
        self.s_scale.valueChanged.connect(self._on_svg_scale_changed)
        self.lbl_s_scale = QLabel(tr("lbl_scale"))
        sf.addRow(self.lbl_s_scale, self.s_scale)
        layout.addWidget(self.grp_s_scale)

        # Color Infill Palette Group
        self.grp_svg_infill = QGroupBox(tr("group_color_infill"))
        sif = QVBoxLayout(self.grp_svg_infill)
        sif.setContentsMargins(6, 4, 6, 4)
        sif.setSpacing(3)

        self.cb_svg_infill = QCheckBox(tr("chk_enable_svg_infill"))
        self.cb_svg_infill.setChecked(False)
        self.cb_svg_infill.stateChanged.connect(self._on_svg_infill_master_changed)
        sif.addWidget(self.cb_svg_infill)

        self.svg_infill_params = QWidget()
        spf = QVBoxLayout(self.svg_infill_params)
        spf.setContentsMargins(0, 0, 0, 0)
        spf.setSpacing(3)

        spacing_row = QHBoxLayout()
        spacing_row.setContentsMargins(0, 0, 0, 0)
        spacing_row.setSpacing(4)
        self.lbl_svg_spacing = QLabel(tr("lbl_infill_spacing"))
        self.sb_svg_spacing = QDoubleSpinBox()
        self.sb_svg_spacing.setRange(0.1, 10.0)
        self.sb_svg_spacing.setSingleStep(0.05)
        self.sb_svg_spacing.setValue(0.5)
        self.sb_svg_spacing.setSuffix(f" {tr('unit_mm')}")
        self.sb_svg_spacing.valueChanged.connect(self._on_svg_spacing_changed)
        spacing_row.addWidget(self.lbl_svg_spacing)
        spacing_row.addWidget(self.sb_svg_spacing)
        spf.addLayout(spacing_row)

        self.svg_colors_widget = QWidget()
        self.svg_colors_layout = QVBoxLayout(self.svg_colors_widget)
        self.svg_colors_layout.setContentsMargins(0, 0, 0, 0)
        self.svg_colors_layout.setSpacing(3)
        spf.addWidget(self.svg_colors_widget)

        self.svg_infill_params.setEnabled(False)
        sif.addWidget(self.svg_infill_params)
        layout.addWidget(self.grp_svg_infill)

        layout.addStretch()
        return page

    # ── Page 3: Raster ────────────────────────────────────────

    def _build_raster_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignTop)

        self.lbl_type_r = QLabel(tr("prop_type_raster"))
        self.lbl_type_r.setStyleSheet("color: #666; font-size: 11px; margin: 0px; padding: 0px;")
        layout.addWidget(self.lbl_type_r)

        # Position group
        self.grp_r_pos = QGroupBox(tr("group_position"))
        pf = QFormLayout(self.grp_r_pos)
        pf.setContentsMargins(6, 4, 6, 4)
        pf.setVerticalSpacing(2)
        self.r_pos_x = QDoubleSpinBox()
        self.r_pos_x.setRange(-500, 500); self.r_pos_x.setSuffix(f" {tr('unit_mm')}"); self.r_pos_x.setDecimals(1)
        self.r_pos_x.valueChanged.connect(self._on_raster_pos_changed)
        pf.addRow("X:", self.r_pos_x)

        self.r_pos_y = QDoubleSpinBox()
        self.r_pos_y.setRange(-500, 500); self.r_pos_y.setSuffix(f" {tr('unit_mm')}"); self.r_pos_y.setDecimals(1)
        self.r_pos_y.valueChanged.connect(self._on_raster_pos_changed)
        pf.addRow("Y:", self.r_pos_y)
        layout.addWidget(self.grp_r_pos)

        # Rotation group
        self.grp_r_rot = QGroupBox(tr("group_rotation"))
        rf = QFormLayout(self.grp_r_rot)
        rf.setContentsMargins(6, 4, 6, 4)
        rf.setVerticalSpacing(2)
        self.r_rotation = QDoubleSpinBox()
        self.r_rotation.setRange(-360, 360); self.r_rotation.setSuffix(" °"); self.r_rotation.setDecimals(1)
        self.r_rotation.valueChanged.connect(self._on_raster_rot_changed)
        self.lbl_r_angle = QLabel(tr("lbl_angle"))
        rf.addRow(self.lbl_r_angle, self.r_rotation)
        layout.addWidget(self.grp_r_rot)

        # Scale group
        self.grp_r_scale = QGroupBox(tr("group_scale"))
        sf = QFormLayout(self.grp_r_scale)
        sf.setContentsMargins(6, 4, 6, 4)
        sf.setVerticalSpacing(2)
        self.r_scale = QDoubleSpinBox()
        self.r_scale.setRange(0.05, 20.0); self.r_scale.setSingleStep(0.1); self.r_scale.setDecimals(2)
        self.r_scale.valueChanged.connect(self._on_raster_scale_changed)
        self.lbl_r_scale = QLabel(tr("lbl_scale"))
        sf.addRow(self.lbl_r_scale, self.r_scale)
        layout.addWidget(self.grp_r_scale)

        # Vectorization group
        self.grp_vectorization = QGroupBox(tr("group_vectorization"))
        vl = QVBoxLayout(self.grp_vectorization)
        vl.setContentsMargins(6, 4, 6, 4)
        vl.setSpacing(3)

        # Method selector
        mf = QFormLayout()
        mf.setContentsMargins(0, 0, 0, 0)
        mf.setVerticalSpacing(2)
        self.lbl_method = QLabel(tr("lbl_method"))
        self.cb_method = QComboBox()
        self.cb_method.addItem(tr("method_smooth_contour"), "contour")
        self.cb_method.addItem(tr("method_centerline"), "centerline")
        self.cb_method.addItem(tr("method_canny"), "canny")
        self.cb_method.currentIndexChanged.connect(self._on_method_changed)
        mf.addRow(self.lbl_method, self.cb_method)
        vl.addLayout(mf)

        # Method sub-stack
        self.method_stack = QStackedWidget()

        # Page 0: Smooth Contour ("contour")
        page_contour = QWidget()
        cf = QFormLayout(page_contour)
        cf.setContentsMargins(0, 2, 0, 2)
        cf.setVerticalSpacing(2)

        self.cb_auto_otsu = QCheckBox(tr("chk_auto_otsu"))
        self.cb_auto_otsu.setChecked(True)
        self.cb_auto_otsu.stateChanged.connect(self._on_contour_auto_changed)
        cf.addRow(self.cb_auto_otsu)

        self.sl_contour_thresh = QSlider(Qt.Horizontal)
        self.sl_contour_thresh.setRange(0, 255)
        self.sl_contour_thresh.setValue(128)
        self.sl_contour_thresh.setEnabled(False)
        self.lbl_val_contour_thresh = QLabel("128")
        self.sl_contour_thresh.valueChanged.connect(self._on_contour_thresh_changed)
        self.lbl_contour_thresh_title = QLabel(tr("lbl_contour_thresh"))
        cf.addRow(self.lbl_contour_thresh_title, self.sl_contour_thresh)
        cf.addRow("", self.lbl_val_contour_thresh)

        self.cb_invert = QCheckBox(tr("chk_invert_colors"))
        self.cb_invert.setChecked(False)
        self.cb_invert.stateChanged.connect(self._on_param_changed)
        cf.addRow(self.cb_invert)

        self.lbl_smoothness = QLabel(tr("lbl_smoothness"))
        self.cb_smoothness = QComboBox()
        self.cb_smoothness.addItem(tr("smooth_none"), 0)
        self.cb_smoothness.addItem(tr("smooth_low"), 1)
        self.cb_smoothness.addItem(tr("smooth_medium"), 2)
        self.cb_smoothness.addItem(tr("smooth_high"), 3)
        self.cb_smoothness.setCurrentIndex(2)
        self.cb_smoothness.currentIndexChanged.connect(self._on_param_changed)
        cf.addRow(self.lbl_smoothness, self.cb_smoothness)

        self.method_stack.addWidget(page_contour)

        # Page 1: Centerline / Skeleton ("centerline")
        page_centerline = QWidget()
        clf = QFormLayout(page_centerline)
        clf.setContentsMargins(0, 2, 0, 2)
        clf.setVerticalSpacing(2)

        self.cb_auto_otsu_cl = QCheckBox(tr("chk_auto_otsu"))
        self.cb_auto_otsu_cl.setChecked(True)
        self.cb_auto_otsu_cl.stateChanged.connect(self._on_cl_auto_changed)
        clf.addRow(self.cb_auto_otsu_cl)

        self.sl_cl_thresh = QSlider(Qt.Horizontal)
        self.sl_cl_thresh.setRange(0, 255)
        self.sl_cl_thresh.setValue(128)
        self.sl_cl_thresh.setEnabled(False)
        self.lbl_val_cl_thresh = QLabel("128")
        self.sl_cl_thresh.valueChanged.connect(self._on_cl_thresh_changed)
        self.lbl_cl_thresh_title = QLabel(tr("lbl_contour_thresh"))
        clf.addRow(self.lbl_cl_thresh_title, self.sl_cl_thresh)
        clf.addRow("", self.lbl_val_cl_thresh)

        self.cb_invert_cl = QCheckBox(tr("chk_invert_colors"))
        self.cb_invert_cl.setChecked(False)
        self.cb_invert_cl.stateChanged.connect(self._on_param_changed)
        clf.addRow(self.cb_invert_cl)

        self.lbl_smoothness_cl = QLabel(tr("lbl_smoothness"))
        self.cb_smoothness_cl = QComboBox()
        self.cb_smoothness_cl.addItem(tr("smooth_none"), 0)
        self.cb_smoothness_cl.addItem(tr("smooth_low"), 1)
        self.cb_smoothness_cl.addItem(tr("smooth_medium"), 2)
        self.cb_smoothness_cl.addItem(tr("smooth_high"), 3)
        self.cb_smoothness_cl.setCurrentIndex(2)
        self.cb_smoothness_cl.currentIndexChanged.connect(self._on_param_changed)
        clf.addRow(self.lbl_smoothness_cl, self.cb_smoothness_cl)

        self.cb_merge_close = QCheckBox(tr("chk_merge_close"))
        self.cb_merge_close.setChecked(True)
        self.cb_merge_close.setToolTip(tr("tip_merge_close"))
        self.cb_merge_close.stateChanged.connect(self._on_param_changed)
        clf.addRow(self.cb_merge_close)

        self.method_stack.addWidget(page_centerline)

        # Page 2: Canny ("canny")
        page_canny = QWidget()
        tf = QFormLayout(page_canny)
        tf.setContentsMargins(0, 2, 0, 2)
        tf.setVerticalSpacing(2)

        self.sl_thresh1 = QSlider(Qt.Horizontal)
        self.sl_thresh1.setRange(0, 255); self.sl_thresh1.setValue(50)
        self.sl_thresh1.setToolTip(tr("tip_thresh1"))
        self.lbl_val_thresh1 = QLabel("50")
        self.sl_thresh1.valueChanged.connect(self._on_thresh_changed)
        self.lbl_thresh1_title = QLabel(tr("lbl_thresh1"))
        tf.addRow(self.lbl_thresh1_title, self.sl_thresh1)
        tf.addRow("", self.lbl_val_thresh1)

        self.sl_thresh2 = QSlider(Qt.Horizontal)
        self.sl_thresh2.setRange(0, 255); self.sl_thresh2.setValue(150)
        self.sl_thresh2.setToolTip(tr("tip_thresh2"))
        self.lbl_val_thresh2 = QLabel("150")
        self.sl_thresh2.valueChanged.connect(self._on_thresh_changed)
        self.lbl_thresh2_title = QLabel(tr("lbl_thresh2"))
        tf.addRow(self.lbl_thresh2_title, self.sl_thresh2)
        tf.addRow("", self.lbl_val_thresh2)

        self.method_stack.addWidget(page_canny)

        vl.addWidget(self.method_stack)

        # Min line length / speckle filter row
        ff = QFormLayout()
        ff.setContentsMargins(0, 2, 0, 2)
        ff.setVerticalSpacing(2)
        self.lbl_min_path_len_title = QLabel(tr("lbl_min_path_len"))
        self.sb_min_path_len = QDoubleSpinBox()
        self.sb_min_path_len.setRange(0.0, 50.0)
        self.sb_min_path_len.setSingleStep(0.1)
        self.sb_min_path_len.setValue(0.5)
        self.sb_min_path_len.setSuffix(f" {tr('unit_mm')}")
        self.sb_min_path_len.setToolTip(tr("tip_min_path_len"))
        self.sb_min_path_len.valueChanged.connect(self._on_param_changed)
        ff.addRow(self.lbl_min_path_len_title, self.sb_min_path_len)
        vl.addLayout(ff)

        self.cb_show_preview = QCheckBox(tr("chk_preview_lines"))
        self.cb_show_preview.setToolTip(tr("tip_preview_lines"))
        self.cb_show_preview.stateChanged.connect(self._on_preview_changed)

        self.btn_help = QPushButton(tr("btn_canny_help"))
        self.btn_help.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px; color: #90caf9; background: transparent; border: none; text-align: left; }"
            "QPushButton:hover { text-decoration: underline; color: #bbdefb; }"
        )
        self.btn_help.clicked.connect(self._show_vector_help)

        self.lbl_auto_note = QLabel(tr("lbl_auto_update"))
        self.lbl_auto_note.setStyleSheet("color: #888; font-size: 10px;")

        vl.addWidget(self.cb_show_preview)
        vl.addWidget(self.btn_help)
        vl.addWidget(self.lbl_auto_note)

        layout.addWidget(self.grp_vectorization)

        # Infill group
        self.grp_infill = QGroupBox(tr("group_infill"))
        inf_layout = QVBoxLayout(self.grp_infill)
        inf_layout.setContentsMargins(6, 4, 6, 4)
        inf_layout.setSpacing(3)

        self.cb_enable_infill = QCheckBox(tr("chk_enable_infill"))
        self.cb_enable_infill.setChecked(False)
        self.cb_enable_infill.stateChanged.connect(self._on_infill_enable_changed)
        inf_layout.addWidget(self.cb_enable_infill)

        self.infill_params_widget = QWidget()
        ipf = QFormLayout(self.infill_params_widget)
        ipf.setContentsMargins(0, 2, 0, 2)
        ipf.setVerticalSpacing(2)

        self.lbl_infill_pattern = QLabel(tr("lbl_infill_pattern"))
        self.cb_infill_pattern = QComboBox()
        self.cb_infill_pattern.addItem(tr("pattern_linear"), "linear")
        self.cb_infill_pattern.addItem(tr("pattern_crosshatch"), "crosshatch")
        self.cb_infill_pattern.addItem(tr("pattern_concentric"), "concentric")
        self.cb_infill_pattern.addItem(tr("pattern_honeycomb"), "honeycomb")
        self.cb_infill_pattern.addItem(tr("pattern_triangles"), "triangles")
        self.cb_infill_pattern.addItem(tr("pattern_adaptive"), "adaptive")
        self.cb_infill_pattern.currentIndexChanged.connect(self._on_infill_pattern_changed)
        ipf.addRow(self.lbl_infill_pattern, self.cb_infill_pattern)

        self.lbl_adaptive_range = QLabel(tr("lbl_adaptive_range"))
        self.adaptive_range_widget = QWidget()
        ar_layout = QHBoxLayout(self.adaptive_range_widget)
        ar_layout.setContentsMargins(0, 0, 0, 0)
        ar_layout.setSpacing(6)

        self.sl_adaptive_range = QSlider(Qt.Horizontal)
        self.sl_adaptive_range.setRange(20, 240)
        self.sl_adaptive_range.setValue(128)
        self.sl_adaptive_range.setToolTip(tr("tip_adaptive_range"))
        self.sl_adaptive_range.valueChanged.connect(self._on_adaptive_range_changed)

        self.lbl_val_adaptive_range = QLabel("128")
        self.lbl_val_adaptive_range.setMinimumWidth(28)

        ar_layout.addWidget(self.sl_adaptive_range, 1)
        ar_layout.addWidget(self.lbl_val_adaptive_range, 0)

        ipf.addRow(self.lbl_adaptive_range, self.adaptive_range_widget)
        self._update_adaptive_visibility()

        self.lbl_infill_spacing = QLabel(tr("lbl_infill_spacing"))
        self.sb_infill_spacing = QDoubleSpinBox()
        self.sb_infill_spacing.setRange(0.1, 20.0)
        self.sb_infill_spacing.setSingleStep(0.1)
        self.sb_infill_spacing.setDecimals(2)
        self.sb_infill_spacing.setValue(0.5)
        self.sb_infill_spacing.setSuffix(f" {tr('unit_mm')}")
        self.sb_infill_spacing.setToolTip(tr("tip_infill_spacing"))
        self.sb_infill_spacing.valueChanged.connect(self._on_param_changed)
        ipf.addRow(self.lbl_infill_spacing, self.sb_infill_spacing)

        self.lbl_infill_angle = QLabel(tr("lbl_infill_angle"))
        self.sb_infill_angle = QDoubleSpinBox()
        self.sb_infill_angle.setRange(0.0, 180.0)
        self.sb_infill_angle.setSingleStep(5.0)
        self.sb_infill_angle.setDecimals(1)
        self.sb_infill_angle.setValue(45.0)
        self.sb_infill_angle.setSuffix(" °")
        self.sb_infill_angle.valueChanged.connect(self._on_param_changed)
        ipf.addRow(self.lbl_infill_angle, self.sb_infill_angle)

        self.lbl_infill_min_area = QLabel(tr("lbl_infill_min_area"))
        self.sb_infill_min_area = QDoubleSpinBox()
        self.sb_infill_min_area.setRange(0.1, 1000.0)
        self.sb_infill_min_area.setSingleStep(0.5)
        self.sb_infill_min_area.setDecimals(1)
        self.sb_infill_min_area.setValue(2.0)
        self.sb_infill_min_area.setSuffix(" mm²")
        self.sb_infill_min_area.setToolTip(tr("tip_infill_min_area"))
        self.sb_infill_min_area.valueChanged.connect(self._on_param_changed)
        ipf.addRow(self.lbl_infill_min_area, self.sb_infill_min_area)

        self.infill_params_widget.setEnabled(False)
        inf_layout.addWidget(self.infill_params_widget)

        self.btn_infill_help = QPushButton(tr("btn_infill_help"))
        self.btn_infill_help.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px; color: #90caf9; background: transparent; border: none; text-align: left; }"
            "QPushButton:hover { text-decoration: underline; color: #bbdefb; }"
        )
        self.btn_infill_help.clicked.connect(self._show_infill_help)
        inf_layout.addWidget(self.btn_infill_help)

        layout.addWidget(self.grp_infill)
        layout.addStretch()
        return page

    # ── set_item ──────────────────────────────────────────────

    def _on_lock_toggled(self, checked: bool):
        if self._updating or not self._current_item:
            return
        self._current_item.set_locked(checked)
        self._update_transform_controls_enabled(not checked)
        self.item_changed.emit()

    def _on_hide_toggled(self, checked: bool):
        if self._updating or not self._current_item:
            return
        self._current_item.set_hidden(checked)
        self.item_changed.emit()

    def _update_transform_controls_enabled(self, enabled: bool):
        # Text page transform controls
        self.t_pos_x.setEnabled(enabled)
        self.t_pos_y.setEnabled(enabled)
        self.t_rotation.setEnabled(enabled)
        self.t_scale.setEnabled(enabled)

        # SVG page transform controls
        self.s_pos_x.setEnabled(enabled)
        self.s_pos_y.setEnabled(enabled)
        self.s_rotation.setEnabled(enabled)
        self.s_scale.setEnabled(enabled)

        # Raster page transform controls
        self.r_pos_x.setEnabled(enabled)
        self.r_pos_y.setEnabled(enabled)
        self.r_rotation.setEnabled(enabled)
        self.r_scale.setEnabled(enabled)

    def set_item(self, item: Optional["BasePlotItem"]):
        """Updates the panel controls to reflect the selected canvas item."""
        self._current_item = item
        self._updating = True

        if item is None:
            self.item_toolbar.setVisible(False)
            self._stack.setCurrentIndex(0)
            self._stack.updateGeometry()
            self._scroll_area.updateGeometry()
            self._updating = False
            return

        self.item_toolbar.setVisible(True)
        self.chk_lock.blockSignals(True)
        self.chk_lock.setChecked(getattr(item, "is_locked", False))
        self.chk_lock.blockSignals(False)

        self.chk_hide.blockSignals(True)
        self.chk_hide.setChecked(getattr(item, "is_hidden", False))
        self.chk_hide.blockSignals(False)

        self._update_transform_controls_enabled(not getattr(item, "is_locked", False))

        from ui.canvas_items import TextItem, SvgItem, RasterItem, MM_TO_PX

        pos = item.pos()
        x_mm = pos.x() / MM_TO_PX
        y_mm = pos.y() / MM_TO_PX
        rot = item.rotation()
        sc = item.scale()

        if isinstance(item, TextItem):
            self._stack.setCurrentIndex(1)
            self.txt_input.setText(item.text)
            self.txt_font_combo.setCurrentFont(QFont(item.font_family))
            self.txt_bold.setChecked(item.is_bold)
            self.txt_italic.setChecked(item.is_italic)
            self.t_pos_x.setValue(x_mm)
            self.t_pos_y.setValue(y_mm)
            self.t_rotation.setValue(rot)
            self.t_scale.setValue(sc)

            has_t_inf = bool(getattr(item, "enable_infill", False))
            self.cb_text_infill.setChecked(has_t_inf)
            self.text_infill_params.setEnabled(has_t_inf)
            p_val = getattr(item, "infill_pattern", "linear")
            p_idx = self.cb_text_pattern.findData(p_val)
            if p_idx >= 0:
                self.cb_text_pattern.setCurrentIndex(p_idx)
            self.sb_text_spacing.setValue(float(getattr(item, "infill_spacing_mm", 0.5)))
            self.sb_text_angle.setValue(float(getattr(item, "infill_angle", 45.0)))

        elif isinstance(item, SvgItem):
            self._stack.setCurrentIndex(2)
            self.s_pos_x.setValue(x_mm)
            self.s_pos_y.setValue(y_mm)
            self.s_rotation.setValue(rot)
            self.s_scale.setValue(sc)

            has_s_inf = bool(getattr(item, "enable_infill", False))
            self.cb_svg_infill.setChecked(has_s_inf)
            self.svg_infill_params.setEnabled(has_s_inf)
            self.sb_svg_spacing.setValue(float(getattr(item, "infill_spacing_mm", 0.5)))
            self._populate_svg_colors(item)

        elif isinstance(item, RasterItem):
            self._stack.setCurrentIndex(3)
            self.r_pos_x.setValue(x_mm)
            self.r_pos_y.setValue(y_mm)
            self.r_rotation.setValue(rot)
            self.r_scale.setValue(sc)
            self.cb_show_preview.setChecked(item.show_preview)

            # Method
            method = getattr(item, "method", "contour")
            m_idx = self.cb_method.findData(method)
            if m_idx >= 0:
                self.cb_method.setCurrentIndex(m_idx)
            stack_idx = {"contour": 0, "centerline": 1, "canny": 2}.get(method, 0)
            self.method_stack.setCurrentIndex(stack_idx)

            # Canny
            self.sl_thresh1.setValue(int(getattr(item, "threshold1", 50)))
            self.sl_thresh2.setValue(int(getattr(item, "threshold2", 150)))
            self.lbl_val_thresh1.setText(str(self.sl_thresh1.value()))
            self.lbl_val_thresh2.setText(str(self.sl_thresh2.value()))

            # Contour
            auto_th = bool(getattr(item, "auto_thresh", True))
            self.cb_auto_otsu.setChecked(auto_th)
            self.sl_contour_thresh.setValue(int(getattr(item, "contour_thresh", 128)))
            self.sl_contour_thresh.setEnabled(not auto_th)
            self.lbl_val_contour_thresh.setText(str(self.sl_contour_thresh.value()))
            self.cb_invert.setChecked(bool(getattr(item, "invert", False)))

            s_val = getattr(item, "smooth_level", 2)
            s_idx = self.cb_smoothness.findData(s_val)
            if s_idx >= 0:
                self.cb_smoothness.setCurrentIndex(s_idx)

            # Centerline
            self.cb_auto_otsu_cl.setChecked(auto_th)
            self.sl_cl_thresh.setValue(int(getattr(item, "contour_thresh", 128)))
            self.sl_cl_thresh.setEnabled(not auto_th)
            self.lbl_val_cl_thresh.setText(str(self.sl_cl_thresh.value()))
            self.cb_invert_cl.setChecked(bool(getattr(item, "invert", False)))
            s_cl_idx = self.cb_smoothness_cl.findData(s_val)
            if s_cl_idx >= 0:
                self.cb_smoothness_cl.setCurrentIndex(s_cl_idx)
            self.cb_merge_close.setChecked(bool(getattr(item, "merge_close_lines", True)))

            # Min path length
            self.sb_min_path_len.setValue(float(getattr(item, "min_path_len_mm", 0.5)))

            # Infill
            has_inf = bool(getattr(item, "enable_infill", False))
            self.cb_enable_infill.setChecked(has_inf)
            self.infill_params_widget.setEnabled(has_inf)

            p_val = getattr(item, "infill_pattern", "linear")
            p_idx = self.cb_infill_pattern.findData(p_val)
            if p_idx >= 0:
                self.cb_infill_pattern.setCurrentIndex(p_idx)

            self.sl_adaptive_range.setValue(int(getattr(item, "infill_adaptive_range", 128)))
            self.lbl_val_adaptive_range.setText(str(self.sl_adaptive_range.value()))
            self._update_adaptive_visibility()

            self.sb_infill_spacing.setValue(float(getattr(item, "infill_spacing_mm", 0.5)))
            self.sb_infill_angle.setValue(float(getattr(item, "infill_angle", 45.0)))
            self.sb_infill_min_area.setValue(float(getattr(item, "infill_min_area_mm2", 2.0)))

        self._stack.updateGeometry()
        self._scroll_area.updateGeometry()
        self._updating = False

    def focus_text_input(self):
        """Focuses and selects all text in the text input box for quick editing."""
        self.txt_input.setFocus()
        self.txt_input.selectAll()

    # ── Text Item Slots ───────────────────────────────────────

    def _on_text_content_changed(self, text: str):
        if self._updating or not self._current_item:
            return
        from ui.canvas_items import TextItem
        if isinstance(self._current_item, TextItem):
            self._current_item.set_text(text)
            self.item_changed.emit()

    def _on_text_font_changed(self, font: QFont):
        if self._updating or not self._current_item:
            return
        from ui.canvas_items import TextItem
        if isinstance(self._current_item, TextItem):
            self._current_item.set_font_family(font.family())
            self.item_changed.emit()

    def _on_open_fonts_dir(self):
        FontManager.get_instance().open_fonts_folder()

    def _on_text_style_changed(self):
        if self._updating or not self._current_item:
            return
        from ui.canvas_items import TextItem
        if isinstance(self._current_item, TextItem):
            self._current_item.set_bold(self.txt_bold.isChecked())
            self._current_item.set_italic(self.txt_italic.isChecked())
            self.item_changed.emit()

    def _on_text_pos_changed(self):
        if self._updating or not self._current_item:
            return
        from ui.canvas_items import MM_TO_PX
        self._current_item.setPos(self.t_pos_x.value() * MM_TO_PX,
                                   self.t_pos_y.value() * MM_TO_PX)
        self.item_changed.emit()

    def _on_text_rot_changed(self):
        if self._updating or not self._current_item:
            return
        self._current_item.setRotation(self.t_rotation.value())
        self.item_changed.emit()

    def _on_text_scale_changed(self):
        if self._updating or not self._current_item:
            return
        self._current_item.setScale(self.t_scale.value())
        self.item_changed.emit()

    def _on_text_infill_changed(self):
        if self._updating or not self._current_item:
            return
        from ui.canvas_items import TextItem
        if isinstance(self._current_item, TextItem):
            enabled = self.cb_text_infill.isChecked()
            self.text_infill_params.setEnabled(enabled)
            self._current_item.set_infill(
                enable_infill=enabled,
                infill_pattern=self.cb_text_pattern.currentData(),
                infill_spacing_mm=self.sb_text_spacing.value(),
                infill_angle=self.sb_text_angle.value(),
            )
            self.item_changed.emit()

    # ── SVG Item Slots ────────────────────────────────────────

    def _on_svg_pos_changed(self):
        if self._updating or not self._current_item:
            return
        from ui.canvas_items import MM_TO_PX
        self._current_item.setPos(self.s_pos_x.value() * MM_TO_PX,
                                   self.s_pos_y.value() * MM_TO_PX)
        self.item_changed.emit()

    def _on_svg_rot_changed(self):
        if self._updating or not self._current_item:
            return
        self._current_item.setRotation(self.s_rotation.value())
        self.item_changed.emit()

    def _on_svg_scale_changed(self):
        if self._updating or not self._current_item:
            return
        self._current_item.setScale(self.s_scale.value())
        self.item_changed.emit()

    def _on_svg_infill_master_changed(self, state: int):
        if self._updating or not self._current_item:
            return
        from ui.canvas_items import SvgItem
        if isinstance(self._current_item, SvgItem):
            enabled = (state == Qt.Checked)
            self.svg_infill_params.setEnabled(enabled)
            self._current_item.set_infill_config(
                enable_infill=enabled,
                infill_spacing_mm=self.sb_svg_spacing.value(),
            )
            self.item_changed.emit()

    def _on_svg_spacing_changed(self, val: float):
        if self._updating or not self._current_item:
            return
        from ui.canvas_items import SvgItem
        if isinstance(self._current_item, SvgItem):
            self._current_item.set_infill_config(
                enable_infill=self.cb_svg_infill.isChecked(),
                infill_spacing_mm=val,
            )
            self.item_changed.emit()

    def _populate_svg_colors(self, item: "SvgItem"):
        while self.svg_colors_layout.count():
            child = self.svg_colors_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        configs = getattr(item, "color_configs", [])
        if not configs:
            lbl = QLabel(tr("lbl_no_colors"))
            lbl.setStyleSheet("color: #777; font-size: 10px; font-style: italic;")
            self.svg_colors_layout.addWidget(lbl)
            self._svg_row_widgets = []
            return

        self._svg_row_widgets = []
        for idx, cfg in enumerate(configs):
            row = QFrame()
            row.setObjectName("svgColorRow")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 2, 4, 2)
            rl.setSpacing(4)

            swatch = QLabel()
            swatch.setFixedSize(16, 16)
            swatch.setStyleSheet(f"background-color: {cfg['hex']}; border: 1px solid #777; border-radius: 3px;")
            swatch.setToolTip(f"{cfg['hex']} ({cfg.get('pct', 0):.1f}%)")
            rl.addWidget(swatch)

            lbl_pct = QLabel(f"{cfg.get('pct', 0):.0f}%")
            lbl_pct.setStyleSheet("color: #888; font-size: 10px; min-width: 25px;")
            rl.addWidget(lbl_pct)

            chk = QCheckBox()
            chk.setChecked(cfg.get("enabled", True))
            chk.setToolTip(tr("lbl_color_fill"))
            chk.stateChanged.connect(self._on_svg_color_row_changed)
            rl.addWidget(chk)

            cb_pat = QComboBox()
            cb_pat.addItem(tr("pattern_linear"), "linear")
            cb_pat.addItem(tr("pattern_crosshatch"), "crosshatch")
            cb_pat.addItem(tr("pattern_concentric"), "concentric")
            cb_pat.addItem(tr("pattern_honeycomb"), "honeycomb")
            cb_pat.addItem(tr("pattern_triangles"), "triangles")
            p_idx = cb_pat.findData(cfg.get("pattern", "linear"))
            if p_idx >= 0:
                cb_pat.setCurrentIndex(p_idx)
            cb_pat.currentIndexChanged.connect(self._on_svg_color_row_changed)
            rl.addWidget(cb_pat, 1)

            sb_ang = QDoubleSpinBox()
            sb_ang.setRange(0, 180)
            sb_ang.setValue(float(cfg.get("angle_deg", 45.0)))
            sb_ang.setSuffix("°")
            sb_ang.setFixedWidth(55)
            sb_ang.valueChanged.connect(self._on_svg_color_row_changed)
            rl.addWidget(sb_ang)

            self.svg_colors_layout.addWidget(row)
            self._svg_row_widgets.append((chk, cb_pat, sb_ang, cfg))

    def _on_svg_color_row_changed(self):
        if self._updating or not self._current_item:
            return
        from ui.canvas_items import SvgItem
        if not isinstance(self._current_item, SvgItem):
            return

        updated = []
        for chk, cb_pat, sb_ang, orig_cfg in getattr(self, "_svg_row_widgets", []):
            cfg = dict(orig_cfg)
            cfg["enabled"] = chk.isChecked()
            cfg["pattern"] = cb_pat.currentData()
            cfg["angle_deg"] = sb_ang.value()
            updated.append(cfg)

        self._current_item.set_infill_config(
            enable_infill=self.cb_svg_infill.isChecked(),
            infill_spacing_mm=self.sb_svg_spacing.value(),
            color_configs=updated,
        )
        self.item_changed.emit()

    # ── Raster Item Slots ─────────────────────────────────────

    def _on_raster_pos_changed(self):
        if self._updating or not self._current_item:
            return
        from ui.canvas_items import MM_TO_PX
        self._current_item.setPos(self.r_pos_x.value() * MM_TO_PX,
                                   self.r_pos_y.value() * MM_TO_PX)
        self.item_changed.emit()

    def _on_raster_rot_changed(self):
        if self._updating or not self._current_item:
            return
        self._current_item.setRotation(self.r_rotation.value())
        self.item_changed.emit()

    def _on_raster_scale_changed(self):
        if self._updating or not self._current_item:
            return
        self._current_item.setScale(self.r_scale.value())
        self.item_changed.emit()

    def _on_method_changed(self, index: int):
        method = self.cb_method.currentData() or "contour"
        stack_idx = {"contour": 0, "centerline": 1, "canny": 2}.get(method, 0)
        self.method_stack.setCurrentIndex(stack_idx)
        if not self._updating:
            self._retrace_timer.start()

    def _on_contour_auto_changed(self, state: int):
        self.sl_contour_thresh.setEnabled(state != Qt.Checked)
        if not self._updating:
            self._retrace_timer.start()

    def _on_contour_thresh_changed(self, value: int):
        self.lbl_val_contour_thresh.setText(str(value))
        if not self._updating:
            self._retrace_timer.start()

    def _on_cl_auto_changed(self, state: int):
        self.sl_cl_thresh.setEnabled(state != Qt.Checked)
        if not self._updating:
            self._retrace_timer.start()

    def _on_cl_thresh_changed(self, value: int):
        self.lbl_val_cl_thresh.setText(str(value))
        if not self._updating:
            self._retrace_timer.start()

    def _on_infill_enable_changed(self, state: int):
        self.infill_params_widget.setEnabled(state == Qt.Checked)
        if not self._updating:
            self._retrace_timer.start()

    def _on_infill_pattern_changed(self, index: int):
        self._update_adaptive_visibility()
        self._on_param_changed()

    def _update_adaptive_visibility(self):
        if hasattr(self, "cb_infill_pattern") and hasattr(self, "lbl_adaptive_range") and hasattr(self, "adaptive_range_widget"):
            is_adaptive = (self.cb_infill_pattern.currentData() == "adaptive")
            self.lbl_adaptive_range.setVisible(is_adaptive)
            self.adaptive_range_widget.setVisible(is_adaptive)

    def _on_adaptive_range_changed(self, value: int):
        self.lbl_val_adaptive_range.setText(str(value))
        if not self._updating:
            self._retrace_timer.start()

    def _on_param_changed(self, *args):
        if not self._updating:
            self._retrace_timer.start()

    def _on_thresh_changed(self, value: int):
        self.lbl_val_thresh1.setText(str(self.sl_thresh1.value()))
        self.lbl_val_thresh2.setText(str(self.sl_thresh2.value()))
        if not self._updating:
            self._retrace_timer.start()

    def _on_preview_changed(self, state):
        from ui.canvas_items import RasterItem
        if isinstance(self._current_item, RasterItem):
            self._current_item.set_show_preview(state == Qt.Checked)

    def _on_retrace(self):
        from ui.canvas_items import RasterItem
        if isinstance(self._current_item, RasterItem):
            method = self.cb_method.currentData() or "contour"
            is_cl = (method == "centerline")
            auto_th = self.cb_auto_otsu_cl.isChecked() if is_cl else self.cb_auto_otsu.isChecked()
            c_thresh = int(self.sl_cl_thresh.value()) if is_cl else int(self.sl_contour_thresh.value())
            inv = self.cb_invert_cl.isChecked() if is_cl else self.cb_invert.isChecked()
            smooth_cb = self.cb_smoothness_cl if is_cl else self.cb_smoothness
            s_level = int(smooth_cb.currentData() if smooth_cb.currentData() is not None else 2)

            self._current_item.retrace(
                method=method,
                threshold1=float(self.sl_thresh1.value()),
                threshold2=float(self.sl_thresh2.value()),
                contour_thresh=c_thresh,
                auto_thresh=auto_th,
                invert=inv,
                smooth_level=s_level,
                enable_infill=self.cb_enable_infill.isChecked(),
                infill_pattern=self.cb_infill_pattern.currentData() or "linear",
                infill_spacing_mm=float(self.sb_infill_spacing.value()),
                infill_angle=float(self.sb_infill_angle.value()),
                infill_min_area_mm2=float(self.sb_infill_min_area.value()),
                min_path_len_mm=float(self.sb_min_path_len.value()),
                merge_close_lines=self.cb_merge_close.isChecked(),
                infill_adaptive_range=int(self.sl_adaptive_range.value()),
            )
            self.item_changed.emit()

    def _show_vector_help(self):
        QMessageBox.information(self, tr("canny_help_title"), tr("canny_help_content"))

    def _show_infill_help(self):
        QMessageBox.information(self, tr("infill_help_title"), tr("infill_help_content"))

    # ── Retranslate UI ────────────────────────────────────────

    def retranslate_ui(self):
        """Refreshes all localized labels, tooltips and suffixes."""
        mm_suf = f" {tr('unit_mm')}"

        self.lbl_panel_title.setText(tr("prop_title"))
        self.lbl_empty.setText(tr("prop_empty"))
        self.chk_lock.setText(tr("chk_lock"))
        self.chk_lock.setToolTip(tr("tip_lock"))
        self.chk_hide.setText(tr("chk_hide"))
        self.chk_hide.setToolTip(tr("tip_hide"))

        # Text page
        self.lbl_type_t.setText(tr("prop_type_text"))
        self.grp_text_content.setTitle(tr("group_text"))
        self.lbl_txt_prompt.setText(tr("lbl_text"))
        self.lbl_txt_font.setText(tr("lbl_font"))
        self.btn_open_fonts.setText(tr("btn_open_fonts"))
        self.btn_open_fonts.setToolTip(tr("tip_open_fonts"))
        self.txt_bold.setText(tr("chk_bold"))
        self.txt_italic.setText(tr("chk_italic"))
        self.grp_t_pos.setTitle(tr("group_position"))
        self.t_pos_x.setSuffix(mm_suf)
        self.t_pos_y.setSuffix(mm_suf)
        self.grp_t_rot.setTitle(tr("group_rotation"))
        self.lbl_t_angle.setText(tr("lbl_angle"))
        self.grp_t_scale.setTitle(tr("group_scale"))
        self.lbl_t_scale.setText(tr("lbl_scale"))

        self.grp_text_infill.setTitle(tr("group_text_infill"))
        self.cb_text_infill.setText(tr("chk_enable_text_infill"))
        self.lbl_text_pattern.setText(tr("lbl_infill_pattern"))
        self.cb_text_pattern.setItemText(0, tr("pattern_linear"))
        self.cb_text_pattern.setItemText(1, tr("pattern_crosshatch"))
        self.cb_text_pattern.setItemText(2, tr("pattern_concentric"))
        self.cb_text_pattern.setItemText(3, tr("pattern_honeycomb"))
        self.cb_text_pattern.setItemText(4, tr("pattern_triangles"))
        self.lbl_text_spacing.setText(tr("lbl_infill_spacing"))
        self.sb_text_spacing.setSuffix(mm_suf)
        self.lbl_text_angle.setText(tr("lbl_infill_angle"))

        # SVG page
        self.lbl_type_s.setText(tr("prop_type_svg"))
        self.grp_s_pos.setTitle(tr("group_position"))
        self.s_pos_x.setSuffix(mm_suf)
        self.s_pos_y.setSuffix(mm_suf)
        self.grp_s_rot.setTitle(tr("group_rotation"))
        self.lbl_s_angle.setText(tr("lbl_angle"))
        self.grp_s_scale.setTitle(tr("group_scale"))
        self.lbl_s_scale.setText(tr("lbl_scale"))

        self.grp_svg_infill.setTitle(tr("group_color_infill"))
        self.cb_svg_infill.setText(tr("chk_enable_svg_infill"))
        self.lbl_svg_spacing.setText(tr("lbl_infill_spacing"))
        self.sb_svg_spacing.setSuffix(mm_suf)

        # Raster page
        self.lbl_type_r.setText(tr("prop_type_raster"))
        self.grp_r_pos.setTitle(tr("group_position"))
        self.r_pos_x.setSuffix(mm_suf)
        self.r_pos_y.setSuffix(mm_suf)
        self.grp_r_rot.setTitle(tr("group_rotation"))
        self.lbl_r_angle.setText(tr("lbl_angle"))
        self.grp_r_scale.setTitle(tr("group_scale"))
        self.lbl_r_scale.setText(tr("lbl_scale"))

        self.grp_vectorization.setTitle(tr("group_vectorization"))
        self.lbl_method.setText(tr("lbl_method"))
        self.cb_method.setItemText(0, tr("method_smooth_contour"))
        self.cb_method.setItemText(1, tr("method_centerline"))
        self.cb_method.setItemText(2, tr("method_canny"))

        self.cb_auto_otsu.setText(tr("chk_auto_otsu"))
        self.lbl_contour_thresh_title.setText(tr("lbl_contour_thresh"))
        self.cb_invert.setText(tr("chk_invert_colors"))
        self.lbl_smoothness.setText(tr("lbl_smoothness"))
        self.cb_smoothness.setItemText(0, tr("smooth_none"))
        self.cb_smoothness.setItemText(1, tr("smooth_low"))
        self.cb_smoothness.setItemText(2, tr("smooth_medium"))
        self.cb_smoothness.setItemText(3, tr("smooth_high"))

        self.cb_auto_otsu_cl.setText(tr("chk_auto_otsu"))
        self.lbl_cl_thresh_title.setText(tr("lbl_contour_thresh"))
        self.cb_invert_cl.setText(tr("chk_invert_colors"))
        self.lbl_smoothness_cl.setText(tr("lbl_smoothness"))
        self.cb_smoothness_cl.setItemText(0, tr("smooth_none"))
        self.cb_smoothness_cl.setItemText(1, tr("smooth_low"))
        self.cb_smoothness_cl.setItemText(2, tr("smooth_medium"))
        self.cb_smoothness_cl.setItemText(3, tr("smooth_high"))
        self.cb_merge_close.setText(tr("chk_merge_close"))
        self.cb_merge_close.setToolTip(tr("tip_merge_close"))

        self.lbl_min_path_len_title.setText(tr("lbl_min_path_len"))
        self.sb_min_path_len.setSuffix(mm_suf)
        self.sb_min_path_len.setToolTip(tr("tip_min_path_len"))

        self.lbl_thresh1_title.setText(tr("lbl_thresh1"))
        self.sl_thresh1.setToolTip(tr("tip_thresh1"))
        self.lbl_thresh2_title.setText(tr("lbl_thresh2"))
        self.sl_thresh2.setToolTip(tr("tip_thresh2"))

        self.cb_show_preview.setText(tr("chk_preview_lines"))
        self.cb_show_preview.setToolTip(tr("tip_preview_lines"))
        self.btn_help.setText(tr("btn_canny_help"))
        self.lbl_auto_note.setText(tr("lbl_auto_update"))

        self.grp_infill.setTitle(tr("group_infill"))
        self.cb_enable_infill.setText(tr("chk_enable_infill"))
        self.lbl_infill_pattern.setText(tr("lbl_infill_pattern"))
        self.cb_infill_pattern.setItemText(0, tr("pattern_linear"))
        self.cb_infill_pattern.setItemText(1, tr("pattern_crosshatch"))
        self.cb_infill_pattern.setItemText(2, tr("pattern_concentric"))
        self.cb_infill_pattern.setItemText(3, tr("pattern_honeycomb"))
        self.cb_infill_pattern.setItemText(4, tr("pattern_triangles"))
        self.cb_infill_pattern.setItemText(5, tr("pattern_adaptive"))

        self.lbl_adaptive_range.setText(tr("lbl_adaptive_range"))
        self.sl_adaptive_range.setToolTip(tr("tip_adaptive_range"))

        self.lbl_infill_spacing.setText(tr("lbl_infill_spacing"))
        self.sb_infill_spacing.setSuffix(mm_suf)
        self.sb_infill_spacing.setToolTip(tr("tip_infill_spacing"))

        self.lbl_infill_angle.setText(tr("lbl_infill_angle"))
        self.lbl_infill_min_area.setText(tr("lbl_infill_min_area"))
        self.sb_infill_min_area.setToolTip(tr("tip_infill_min_area"))
        self.btn_infill_help.setText(tr("btn_infill_help"))
