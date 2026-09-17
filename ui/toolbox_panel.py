"""
toolbox_panel.py — Left tools sidebar panel.

Provides controls to activate the Text placement tool, import vector/raster images,
delete selections, and reset zoom.
"""
from __future__ import annotations
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFileDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize

from core.i18n import tr, register_listener
from ui.icons import get_icon


class ToolboxPanel(QWidget):
    """Left tools sidebar panel."""

    tool_mode_changed = pyqtSignal(str)           # "text" or "select"
    text_tool_activated = pyqtSignal()
    add_file_requested = pyqtSignal(str)          # filepath (SVG, PNG, JPG, BMP)
    delete_selected_requested = pyqtSignal()
    fit_view_requested = pyqtSignal()
    grid_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(190)
        self._text_active = False
        self._init_ui()
        register_listener(self.retranslate_ui)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header label
        self.lbl_title = QLabel(tr("dock_toolbox"))
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.lbl_title)

        layout.addSpacing(4)

        # 1. Text tool (click-to-place on canvas)
        self.btn_text = QPushButton(tr("tool_text"))
        self.btn_text.setIcon(get_icon("text"))
        self.btn_text.setIconSize(QSize(18, 18))
        self.btn_text.setCheckable(True)
        self.btn_text.setToolTip(tr("tool_text_tip"))
        self.btn_text.clicked.connect(self._on_text_clicked)
        layout.addWidget(self.btn_text)

        # 2. Unified Vector & Image import
        self.btn_image = QPushButton(tr("tool_image"))
        self.btn_image.setIcon(get_icon("image"))
        self.btn_image.setIconSize(QSize(18, 18))
        self.btn_image.setToolTip(tr("tool_image_tip"))
        self.btn_image.clicked.connect(self._on_add_file)
        layout.addWidget(self.btn_image)

        layout.addSpacing(6)

        # 3. Delete selection
        self.btn_del = QPushButton(tr("tool_delete"))
        self.btn_del.setIcon(get_icon("delete"))
        self.btn_del.setIconSize(QSize(18, 18))
        self.btn_del.setToolTip(tr("tool_delete_tip"))
        self.btn_del.clicked.connect(self.delete_selected_requested)
        layout.addWidget(self.btn_del)

        # 4. Zoom to fit
        self.btn_fit = QPushButton(tr("tool_fit"))
        self.btn_fit.setIcon(get_icon("fit"))
        self.btn_fit.setIconSize(QSize(18, 18))
        self.btn_fit.setToolTip(tr("tool_fit_tip"))
        self.btn_fit.clicked.connect(self.fit_view_requested)
        layout.addWidget(self.btn_fit)

        # 5. Millimeter grid toggle
        self.btn_grid = QPushButton(tr("tool_grid"))
        self.btn_grid.setIcon(get_icon("grid"))
        self.btn_grid.setIconSize(QSize(18, 18))
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.setToolTip(tr("tool_grid_tip"))
        self.btn_grid.toggled.connect(self.grid_toggled)
        layout.addWidget(self.btn_grid)

        layout.addStretch()

        # Navigation hints
        self.lbl_hints = QLabel(tr("nav_hints"))
        self.lbl_hints.setStyleSheet("color: #777; font-size: 10px; line-height: 130%;")
        self.lbl_hints.setWordWrap(True)
        layout.addWidget(self.lbl_hints)

    def _on_text_clicked(self):
        if self._text_active:
            self.set_text_mode_active(False)
            self.tool_mode_changed.emit("select")
        else:
            self.set_text_mode_active(True)
            self.text_tool_activated.emit()
            self.tool_mode_changed.emit("text")

    def set_text_mode_active(self, active: bool):
        self._text_active = active
        self.btn_text.setChecked(active)
        if active:
            self.btn_text.setText(tr("tool_text_active"))
            self.btn_text.setStyleSheet(
                "QPushButton { background-color: #1976D2; color: #ffffff; font-weight: bold; border-radius: 4px; padding: 6px; }"
            )
        else:
            self.btn_text.setText(tr("tool_text"))
            self.btn_text.setStyleSheet("")

    def _on_add_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("tool_image"), "",
            "Images & Vectors (*.svg *.png *.jpg *.jpeg *.bmp);;Vector SVG (*.svg);;Raster Images (*.png *.jpg *.jpeg *.bmp);;All Files (*.*)"
        )
        if path:
            self.add_file_requested.emit(path)

    def set_grid_checked(self, checked: bool):
        """Programmatically sets the grid button checked state without echoing signals."""
        self.btn_grid.blockSignals(True)
        self.btn_grid.setChecked(checked)
        self.btn_grid.blockSignals(False)

    def retranslate_ui(self):
        """Updates all panel texts and tooltips on language switch."""
        self.lbl_title.setText(tr("dock_toolbox"))
        if self._text_active:
            self.btn_text.setText(tr("tool_text_active"))
        else:
            self.btn_text.setText(tr("tool_text"))
        self.btn_text.setToolTip(tr("tool_text_tip"))

        self.btn_image.setText(tr("tool_image"))
        self.btn_image.setToolTip(tr("tool_image_tip"))

        self.btn_del.setText(tr("tool_delete"))
        self.btn_del.setToolTip(tr("tool_delete_tip"))

        self.btn_fit.setText(tr("tool_fit"))
        self.btn_fit.setToolTip(tr("tool_fit_tip"))

        self.btn_grid.setText(tr("tool_grid"))
        self.btn_grid.setToolTip(tr("tool_grid_tip"))

        self.lbl_hints.setText(tr("nav_hints"))
