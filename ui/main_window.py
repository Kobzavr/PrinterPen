"""
main_window.py — Main application window for PrinterPen.

Layout:
  ┌─────────────────────────────────────────────────────────┐
  │  Menu Bar & Language Selector                           │
  ├──────────┬───────────────────────────────┬──────────────┤
  │ Toolbox  │      Plotter Canvas           │ Properties   │
  │ (left    │      with mm Rulers           │ (right       │
  │  dock)   │                               │  dock)       │
  ├──────────┴───────────────────────────────┴──────────────┤
  │  Serial Connection & G-code Monitor (bottom dock)       │
  └─────────────────────────────────────────────────────────┘
"""
from __future__ import annotations
import os
from typing import Optional, List

from PyQt5.QtWidgets import (
    QMainWindow, QDockWidget, QFileDialog, QMessageBox,
    QAction, QMenuBar, QStatusBar, QLabel, QWidget,
    QHBoxLayout, QComboBox, QPushButton,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QKeySequence, QIcon

from core.canvas_model import CanvasModel, PrinterSettings, load_app_settings, save_app_settings
from core.gcode_generator import generate_gcode, estimate_print_time, validate_polylines
from core.i18n import tr, set_language, get_language, register_listener
from ui.canvas_view import CanvasView, PlotterScene
from ui.canvas_items import TextItem, SvgItem, RasterItem, MM_TO_PX
from ui.toolbox_panel import ToolboxPanel
from ui.properties_panel import PropertiesPanel
from ui.serial_panel import SerialPanel
from ui.settings_dialog import SettingsDialog
from ui.icons import get_icon
from core.font_manager import FontManager
from core.theme_manager import get_theme, set_theme, toggle_theme, register_theme_listener


class MainWindow(QMainWindow):
    """Main application window for PrinterPen."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(1000, 700)
        self.setAcceptDrops(True)
        self.resize(1280, 800)

        # Set application icon
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(base_dir, "logo.ico")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        # Model and project state
        self._model = CanvasModel()
        self._model.settings = load_app_settings()
        self._current_project_path: Optional[str] = None
        self._gcode_lines: List[str] = []

        # Sync active language from settings
        if self._model.settings.language:
            set_language(self._model.settings.language)

        # Scene and Canvas View
        self._scene = PlotterScene()
        self._scene.set_printer_config(
            self._model.settings.printer_max_w,
            self._model.settings.printer_max_h,
            self._model.settings.offset_x,
            self._model.settings.offset_y,
        )
        self._scene.set_show_grid(self._model.settings.show_grid)
        self._view = CanvasView(self._scene)
        self._scene.item_selection_changed.connect(self._on_item_selected)

        self.setCentralWidget(self._view)

        # Panels
        self._toolbox = ToolboxPanel()
        self._toolbox.set_grid_checked(self._model.settings.show_grid)
        self._properties = PropertiesPanel()
        self._serial_panel = SerialPanel()
        self._serial_panel.set_settings_provider(lambda: self._model.settings)
        self._serial_panel.set_gcode_provider(self._provide_fresh_gcode)

        # Setup UI components
        self._setup_docks()
        self._setup_menu()

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._lbl_coords = QLabel("X: — mm  Y: — mm")
        self._status.addPermanentWidget(self._lbl_coords)

        # Connect signals
        self._connect_signals()

        # Register internationalization listener and apply initial strings
        register_listener(self.retranslate_ui)
        self.retranslate_ui()

        # Register theme listener and apply saved theme
        register_theme_listener(self._on_theme_changed)
        initial_theme = getattr(self._model.settings, "theme", "dark")
        set_theme(initial_theme)

        self._status_msg(tr("welcome_msg"))

    def _setup_docks(self):
        # Left dock: Toolbox
        self._left_dock = QDockWidget(tr("dock_toolbox"), self)
        self._left_dock.setWidget(self._toolbox)
        self._left_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self._left_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._left_dock)

        # Right dock: Properties
        self._right_dock = QDockWidget(tr("dock_properties"), self)
        self._right_dock.setWidget(self._properties)
        self._right_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self._right_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, self._right_dock)
        self.resizeDocks([self._right_dock], [320], Qt.Horizontal)

        # Bottom dock: Serial
        self._bottom_dock = QDockWidget(tr("dock_connection"), self)
        self._bottom_dock.setWidget(self._serial_panel)
        self._bottom_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self._bottom_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._bottom_dock)

    def _setup_menu(self):
        menubar = self.menuBar()

        # ── File Menu ─────────────────────────────────────────────
        self.menu_file = menubar.addMenu(tr("menu_file"))

        self.act_new = QAction(tr("new_project"), self)
        self.act_new.setShortcut(QKeySequence.New)
        self.act_new.triggered.connect(self._on_new)
        self.menu_file.addAction(self.act_new)

        self.act_open = QAction(tr("open_project"), self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self._on_open)
        self.menu_file.addAction(self.act_open)

        self.act_save = QAction(tr("save_project"), self)
        self.act_save.setShortcut(QKeySequence.Save)
        self.act_save.triggered.connect(self._on_save)
        self.menu_file.addAction(self.act_save)

        self.act_save_as = QAction(tr("save_project_as"), self)
        self.act_save_as.setShortcut("Ctrl+Shift+S")
        self.act_save_as.triggered.connect(self._on_save_as)
        self.menu_file.addAction(self.act_save_as)

        self.menu_file.addSeparator()

        self.act_import = QAction(tr("import_file"), self)
        self.act_import.setShortcut("Ctrl+I")
        self.act_import.triggered.connect(self._on_import_file)
        self.menu_file.addAction(self.act_import)

        self.menu_file.addSeparator()

        self.act_export_gcode = QAction(tr("export_gcode"), self)
        self.act_export_gcode.setShortcut("Ctrl+E")
        self.act_export_gcode.triggered.connect(self._on_export_gcode)
        self.menu_file.addAction(self.act_export_gcode)

        self.act_export_svg = QAction(tr("export_svg"), self)
        self.act_export_svg.triggered.connect(self._on_export_svg)
        self.menu_file.addAction(self.act_export_svg)
 
        self.menu_file.addSeparator()

        self.act_open_fonts = QAction(tr("action_open_fonts"), self)
        self.act_open_fonts.triggered.connect(lambda: FontManager.get_instance().open_fonts_folder())
        self.menu_file.addAction(self.act_open_fonts)

        self.menu_file.addSeparator()

        self.act_exit = QAction(tr("exit"), self)
        self.act_exit.setShortcut(QKeySequence.Quit)
        self.act_exit.triggered.connect(self.close)
        self.menu_file.addAction(self.act_exit)

        # ── Edit Menu ─────────────────────────────────────────────
        self.menu_edit = menubar.addMenu(tr("menu_edit"))

        self.act_delete = QAction(tr("action_delete_selected"), self)
        self.act_delete.setShortcut(QKeySequence.Delete)
        self.act_delete.triggered.connect(self._on_delete_selected)
        self.menu_edit.addAction(self.act_delete)

        self.menu_edit.addSeparator()

        self.act_settings = QAction(tr("action_settings"), self)
        self.act_settings.setShortcut("Ctrl+,")
        self.act_settings.triggered.connect(self._on_settings)
        self.menu_edit.addAction(self.act_settings)

        # ── View Menu ─────────────────────────────────────────────
        self.menu_view = menubar.addMenu(tr("menu_view"))

        self.act_fit_view = QAction(tr("action_fit_view"), self)
        self.act_fit_view.setShortcut("Ctrl+0")
        self.act_fit_view.triggered.connect(self._view.fit_to_view)
        self.menu_view.addAction(self.act_fit_view)

        self.act_preview_gcode = QAction(tr("action_preview_gcode"), self)
        self.act_preview_gcode.setShortcut("Ctrl+P")
        self.act_preview_gcode.setCheckable(True)
        self.act_preview_gcode.triggered.connect(self._on_toggle_preview)
        self.menu_view.addAction(self.act_preview_gcode)

        self.act_show_grid = QAction(tr("action_show_grid"), self)
        self.act_show_grid.setIcon(get_icon("grid"))
        self.act_show_grid.setShortcut("Ctrl+G")
        self.act_show_grid.setCheckable(True)
        self.act_show_grid.setChecked(self._model.settings.show_grid)
        self.act_show_grid.triggered.connect(self._on_toggle_grid)
        self.menu_view.addAction(self.act_show_grid)

        self.menu_view.addSeparator()
        self.menu_theme = self.menu_view.addMenu(tr("menu_theme"))
        self.act_theme_dark = QAction(tr("theme_dark"), self)
        self.act_theme_dark.setIcon(get_icon("moon"))
        self.act_theme_dark.setCheckable(True)
        self.act_theme_dark.triggered.connect(lambda: self._change_theme("dark"))
        self.act_theme_light = QAction(tr("theme_light"), self)
        self.act_theme_light.setIcon(get_icon("sun"))
        self.act_theme_light.setCheckable(True)
        self.act_theme_light.triggered.connect(lambda: self._change_theme("light"))
        self.menu_theme.addAction(self.act_theme_dark)
        self.menu_theme.addAction(self.act_theme_light)

        # ── G-code Menu ───────────────────────────────────────────
        self.menu_gcode = menubar.addMenu(tr("menu_gcode"))

        self.act_generate_gcode = QAction(tr("action_generate_gcode"), self)
        self.act_generate_gcode.setShortcut("F5")
        self.act_generate_gcode.triggered.connect(self._on_generate_gcode)
        self.menu_gcode.addAction(self.act_generate_gcode)

        self.act_send_printer = QAction(tr("action_send_to_printer"), self)
        self.act_send_printer.setShortcut("F6")
        self.act_send_printer.triggered.connect(self._on_send_to_printer)
        self.menu_gcode.addAction(self.act_send_printer)

        self.menu_gcode.addSeparator()

        # Test Patterns submenu
        self.menu_test_patterns = self.menu_gcode.addMenu(tr("action_test_patterns"))
        self._test_pattern_actions = []
        for pattern_key, pattern_id in [
            ("test_border", "border"),
            ("test_crosshair", "crosshair"),
            ("test_grid", "grid"),
            ("test_spiral", "spiral"),
        ]:
            act = QAction(tr(pattern_key), self)
            act.triggered.connect(lambda checked, p=pattern_id: self._on_test_gcode(p))
            self.menu_test_patterns.addAction(act)
            self._test_pattern_actions.append((pattern_key, act))

        # ── Language Menu ─────────────────────────────────────────
        self.menu_lang = menubar.addMenu(tr("menu_language"))
        self.act_lang_en = QAction("English", self)
        self.act_lang_en.setCheckable(True)
        self.act_lang_en.triggered.connect(lambda: self._change_language("en"))
        self.act_lang_ru = QAction("Русский", self)
        self.act_lang_ru.setCheckable(True)
        self.act_lang_ru.triggered.connect(lambda: self._change_language("ru"))
        self.menu_lang.addAction(self.act_lang_en)
        self.menu_lang.addAction(self.act_lang_ru)

    def _connect_signals(self):
        # Toolbox actions
        self._toolbox.tool_mode_changed.connect(self._on_tool_mode_changed)
        self._toolbox.add_file_requested.connect(self._on_add_file)
        self._toolbox.delete_selected_requested.connect(self._on_delete_selected)
        self._toolbox.fit_view_requested.connect(self._view.fit_to_view)
        self._toolbox.grid_toggled.connect(self._on_toggle_grid)

        # Canvas click-to-place text
        self._view.text_placement_requested.connect(self._on_text_placement_requested)

        # Canvas drag & drop file
        self._view.file_dropped.connect(self._on_file_dropped)

        # Canvas mouse coordinates
        self._view.mouse_moved_mm.connect(self._on_mouse_moved)

        # Properties
        self._properties.item_changed.connect(self._scene.update)

        # Serial panel
        self._serial_panel.compile_requested.connect(self._on_generate_gcode)
        self._serial_panel.print_finished.connect(self._on_print_finished)

        # Custom fonts hot-reload notification
        FontManager.get_instance().fonts_updated.connect(self._on_fonts_updated)

    def _on_fonts_updated(self, families: list):
        if families:
            names = ", ".join(families[:3])
            if len(families) > 3:
                names += f" (+{len(families) - 3})"
            msg = tr("msg_new_fonts_loaded").format(names=names)
            self.statusBar().showMessage(f"✨ {msg}", 6000)

    # ── Language & Theme Management ───────────────────────────

    def _change_language(self, code: str):
        if code not in ("en", "ru"):
            return
        self._model.settings.language = code
        set_language(code)

    def _change_theme(self, theme_name: str):
        self._model.settings.theme = theme_name
        set_theme(theme_name)

    def _on_theme_changed(self, theme: str):
        is_dark = (theme == "dark")
        self.act_theme_dark.setChecked(is_dark)
        self.act_theme_light.setChecked(not is_dark)

    def retranslate_ui(self):
        """Updates all strings in MainWindow when active language changes."""
        lang = get_language()

        self.act_lang_en.setChecked(lang == "en")
        self.act_lang_ru.setChecked(lang == "ru")

        # Window Title
        if self._current_project_path:
            name = os.path.basename(self._current_project_path)
            self.setWindowTitle(f"{tr('app_title')} — {name}")
        else:
            self.setWindowTitle(tr("app_title_new"))

        # Dock Titles
        self._left_dock.setWindowTitle(tr("dock_toolbox"))
        self._right_dock.setWindowTitle(tr("dock_properties"))
        self._bottom_dock.setWindowTitle(tr("dock_connection"))

        # Menus
        self.menu_file.setTitle(tr("menu_file"))
        self.act_new.setText(tr("new_project"))
        self.act_open.setText(tr("open_project"))
        self.act_save.setText(tr("save_project"))
        self.act_save_as.setText(tr("save_project_as"))
        self.act_import.setText(tr("import_file"))
        self.act_export_gcode.setText(tr("export_gcode"))
        self.act_export_svg.setText(tr("export_svg"))
        self.act_open_fonts.setText(tr("action_open_fonts"))
        self.act_exit.setText(tr("exit"))

        self.menu_edit.setTitle(tr("menu_edit"))
        self.act_delete.setText(tr("action_delete_selected"))
        self.act_settings.setText(tr("action_settings"))

        self.menu_view.setTitle(tr("menu_view"))
        self.act_fit_view.setText(tr("action_fit_view"))
        self.act_preview_gcode.setText(tr("action_preview_gcode"))
        self.act_show_grid.setText(tr("action_show_grid"))
        self.menu_theme.setTitle(tr("menu_theme"))
        self.act_theme_dark.setText(tr("theme_dark"))
        self.act_theme_light.setText(tr("theme_light"))

        self.menu_gcode.setTitle(tr("menu_gcode"))
        self.act_generate_gcode.setText(tr("action_generate_gcode"))
        self.act_send_printer.setText(tr("action_send_to_printer"))
        self.menu_test_patterns.setTitle(tr("action_test_patterns"))
        self.menu_lang.setTitle(tr("menu_language"))

        for key, act in self._test_pattern_actions:
            act.setText(tr(key))

        self._on_theme_changed(get_theme())

    # ── Tool Mode & Text Placement ────────────────────────────

    def _on_tool_mode_changed(self, mode: str):
        self._view.set_tool_mode(mode)
        if mode == "text":
            self._status_msg(tr("tool_text_active"))

    def _on_text_placement_requested(self, x_mm: float, y_mm: float):
        """Creates a new editable TextItem where the user clicked on the canvas."""
        self._view.set_tool_mode("select")
        self._toolbox.set_text_mode_active(False)

        item_id = len(self._scene.get_all_plot_items()) + 1
        item = TextItem(
            item_id=item_id,
            text="Text",
            font_family="Arial",
            bold=False,
            italic=False,
        )
        item.signals.changed.connect(lambda i: self._properties.set_item(i))
        self._scene.add_plot_item(item, center=False)
        item.setPos(x_mm * MM_TO_PX, y_mm * MM_TO_PX)

        self._scene.clearSelection()
        item.setSelected(True)
        self._properties.set_item(item)
        self._properties.focus_text_input()
        self._status_msg(f"Text placed at X={x_mm:.1f} Y={y_mm:.1f}")

    # ── Project Management ────────────────────────────────────

    def _on_new(self):
        items = self._scene.get_all_plot_items()
        if items:
            reply = QMessageBox.question(
                self, tr("new_project"),
                tr("unsaved_confirm"),
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self._scene.clear_plot_items()
        self._properties.set_item(None)
        self._current_project_path = None
        self.setWindowTitle(tr("app_title_new"))
        self._status_msg(tr("new_project_created"))

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("open_project"), "",
            "PrinterPen Projects (*.ppen *.json *.ppj);;All Files (*.*)"
        )
        if path:
            self._load_project_file(path)

    def _load_project_file(self, path: str):
        try:
            settings, raw_items = self._model.load_project(path)
            self._scene.clear_plot_items()
            self._properties.set_item(None)

            # Apply loaded printer configuration
            self._scene.set_printer_config(
                settings.printer_max_w,
                settings.printer_max_h,
                settings.offset_x,
                settings.offset_y,
            )
            self._on_toggle_grid(settings.show_grid)

            loaded_count = 0
            for d in raw_items:
                obj_type = d.get("type")
                item_id = len(self._scene.get_all_plot_items()) + 1
                item = None

                if obj_type == "text":
                    item = TextItem(
                        item_id=item_id,
                        text=d.get("text", ""),
                        font_family=d.get("font_family", "Arial"),
                        font_size_mm=d.get("font_size_mm", 12.0),
                        bold=d.get("bold", False),
                        italic=d.get("italic", False),
                        enable_infill=d.get("enable_infill", False),
                        infill_pattern=d.get("infill_pattern", "linear"),
                        infill_spacing_mm=d.get("infill_spacing_mm", 0.5),
                        infill_angle=d.get("infill_angle", 45.0),
                    )
                elif obj_type == "svg":
                    svg_path = d.get("svg_path", "")
                    if os.path.exists(svg_path):
                        item = SvgItem(
                            item_id=item_id,
                            svg_path=svg_path,
                            width_mm=d.get("width_mm", 80.0),
                            enable_infill=d.get("enable_infill", False),
                            infill_spacing_mm=d.get("infill_spacing_mm", 0.5),
                            color_configs=d.get("color_configs", None),
                        )
                    else:
                        self._status_msg(f"SVG file not found: {os.path.basename(svg_path)}")
                elif obj_type == "raster":
                    image_path = d.get("image_path", "")
                    if os.path.exists(image_path):
                        item = RasterItem(
                            item_id=item_id,
                            image_path=image_path,
                            width_mm=d.get("width_mm", 80.0),
                            method=d.get("method", "contour"),
                            threshold1=d.get("threshold1", 50),
                            threshold2=d.get("threshold2", 150),
                            contour_thresh=d.get("contour_thresh", 128),
                            auto_thresh=d.get("auto_thresh", True),
                            invert=d.get("invert", False),
                            smooth_level=d.get("smooth_level", 2),
                            enable_infill=d.get("enable_infill", False),
                            infill_pattern=d.get("infill_pattern", "linear"),
                            infill_spacing_mm=d.get("infill_spacing_mm", 0.5),
                            infill_angle=d.get("infill_angle", 45.0),
                            infill_min_area_mm2=d.get("infill_min_area_mm2", 2.0),
                            min_path_len_mm=d.get("min_path_len_mm", 0.5),
                            merge_close_lines=d.get("merge_close_lines", True),
                            infill_adaptive_range=d.get("infill_adaptive_range", 128),
                        )
                    else:
                        self._status_msg(f"Image file not found: {os.path.basename(image_path)}")

                if item is not None:
                    item.signals.changed.connect(lambda i: self._properties.set_item(i))
                    self._scene.add_plot_item(item, center=False)
                    x_mm = d.get("x_mm", 0.0)
                    y_mm = d.get("y_mm", 0.0)
                    item.setPos(x_mm * MM_TO_PX, y_mm * MM_TO_PX)
                    item.setRotation(d.get("rotation", 0.0))
                    item.setScale(d.get("scale", 1.0))
                    if d.get("is_locked", False):
                        item.set_locked(True)
                    if d.get("is_hidden", False):
                        item.set_hidden(True)
                    loaded_count += 1

            self._current_project_path = path
            self.setWindowTitle(f"{tr('app_title')} — {os.path.basename(path)}")
            self._view.fit_to_view()
            self._status_msg(f"Project loaded: {os.path.basename(path)} ({loaded_count} objects)")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")

    def _on_save(self):
        if self._current_project_path:
            self._save_to_path(self._current_project_path)
        else:
            self._on_save_as()

    def _on_save_as(self):
        default_name = os.path.basename(self._current_project_path) if self._current_project_path else "my_project.ppen"
        path, _ = QFileDialog.getSaveFileName(
            self, tr("save_project_as"), default_name,
            "PrinterPen Project (*.ppen);;JSON Project (*.json);;Legacy Project (*.ppj)"
        )
        if path:
            if not any(path.endswith(ext) for ext in [".ppen", ".json", ".ppj"]):
                path += ".ppen"
            self._save_to_path(path)

    def _save_to_path(self, path: str):
        try:
            items = self._scene.get_all_plot_items()
            self._model.save_project(path, items)
            self._current_project_path = path
            self.setWindowTitle(f"{tr('app_title')} — {os.path.basename(path)}")
            self._status_msg(f"Project saved: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save project:\n{e}")

    # ── File Import & Export ──────────────────────────────────

    def _on_import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("import_file"), "",
            "Vector & Images (*.svg *.png *.jpg *.jpeg *.bmp);;SVG Files (*.svg);;Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self._on_add_file(path)

    def _on_add_file(self, filepath: str, x_mm: Optional[float] = None, y_mm: Optional[float] = None):
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".svg":
            self._on_add_svg(filepath, x_mm=x_mm, y_mm=y_mm)
        else:
            self._on_add_image(filepath, x_mm=x_mm, y_mm=y_mm)

    def _on_add_svg(self, filepath: str, x_mm: Optional[float] = None, y_mm: Optional[float] = None):
        try:
            item = SvgItem(
                item_id=len(self._scene.get_all_plot_items()) + 1,
                svg_path=filepath,
                width_mm=80.0,
            )
            item.signals.changed.connect(lambda i: self._properties.set_item(i))
            pos_mm = (x_mm, y_mm) if (x_mm is not None and y_mm is not None) else None
            self._scene.add_plot_item(item, center=(pos_mm is None), pos_mm=pos_mm)
            self._scene.clearSelection()
            item.setSelected(True)
            self._status_msg(f"Added SVG: {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load SVG:\n{e}")

    def _on_add_image(self, filepath: str, x_mm: Optional[float] = None, y_mm: Optional[float] = None):
        try:
            pen_w = getattr(self._model.settings, "pen_width", 0.5)
            item = RasterItem(
                item_id=len(self._scene.get_all_plot_items()) + 1,
                image_path=filepath,
                width_mm=80.0,
                infill_spacing_mm=pen_w,
            )
            item.signals.changed.connect(lambda i: self._properties.set_item(i))
            pos_mm = (x_mm, y_mm) if (x_mm is not None and y_mm is not None) else None
            self._scene.add_plot_item(item, center=(pos_mm is None), pos_mm=pos_mm)
            self._scene.clearSelection()
            item.setSelected(True)
            self._status_msg(f"Added image: {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image:\n{e}")

    def _on_file_dropped(self, filepath: str, x_mm: Optional[float] = None, y_mm: Optional[float] = None):
        """Dispatches drag & dropped files according to extension."""
        ext = os.path.splitext(filepath)[1].lower()
        if ext in (".ppen", ".json", ".ppj"):
            self._load_project_file(filepath)
        elif ext in (".gcode", ".nc"):
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [l.rstrip() for l in f]
                self._gcode_lines = lines
                self._serial_panel.set_gcode(lines, is_custom=True)
                self._status_msg(f"Loaded G-code: {os.path.basename(filepath)} ({len(lines)} commands)")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load G-code:\n{e}")
        elif ext == ".svg":
            self._on_add_svg(filepath, x_mm=x_mm, y_mm=y_mm)
        elif ext in (".png", ".jpg", ".jpeg", ".bmp"):
            self._on_add_image(filepath, x_mm=x_mm, y_mm=y_mm)

    def _on_export_svg(self):
        polylines = self._scene.get_all_polylines_mm()
        if not polylines:
            QMessageBox.warning(self, "No Objects", "No objects on canvas to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("export_svg"), "drawing.svg",
            "SVG Files (*.svg)"
        )
        if path:
            try:
                from core.canvas_model import export_polylines_to_svg
                export_polylines_to_svg(
                    polylines,
                    self._model.settings.print_area_w,
                    self._model.settings.print_area_h,
                    path,
                )
                self._status_msg(f"SVG exported: {os.path.basename(path)}")
                QMessageBox.information(self, "Export Complete", f"SVG exported successfully:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export SVG:\n{e}")

    def _on_settings(self):
        dlg = SettingsDialog(self._model.settings, self)
        if dlg.exec_():
            self._model.settings = dlg.get_settings()
            save_app_settings(self._model.settings)
            s = self._model.settings
            self._scene.set_printer_config(
                s.printer_max_w,
                s.printer_max_h,
                s.offset_x,
                s.offset_y,
            )
            self._view.fit_to_view()
            if self._scene.get_all_plot_items():
                self._on_generate_gcode()
            self._status_msg(
                f"Settings saved │ Canvas: {s.print_area_w:.1f}×{s.print_area_h:.1f} mm  │  "
                f"Z draw={s.z_down:.2f} mm [pressure: {s.z_draw_offset:+.2f} mm]  Z lift={s.z_up:.2f} mm"
            )

    def _provide_fresh_gcode(self) -> List[str]:
        """Generates fresh G-code using active settings when streaming starts."""
        self._on_generate_gcode()
        return self._gcode_lines

    def _on_mouse_moved(self, x_mm: float, y_mm: float):
        self._lbl_coords.setText(f"X: {x_mm:.1f} mm  Y: {y_mm:.1f} mm")

    def _on_delete_selected(self):
        selected = self._scene.selectedItems()
        for item in selected:
            if isinstance(item, (TextItem, SvgItem, RasterItem)):
                self._scene.removeItem(item)
        self._properties.set_item(None)
        self._status_msg(f"Deleted {len(selected)} item(s)")

    def _on_item_selected(self, item):
        self._properties.set_item(item)

    # ── G-code Generation & Execution ─────────────────────────

    def _on_generate_gcode(self):
        polylines = self._scene.get_all_polylines_mm()

        if not polylines:
            QMessageBox.warning(self, "No Objects", "Canvas is empty.")
            return

        # Coordinate boundary validation
        errors = validate_polylines(polylines, self._model.settings)
        if errors:
            msg = "Some coordinates exceed the printable work area:\n\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                msg += f"\n... and {len(errors) - 5} more warning(s)"
            reply = QMessageBox.warning(
                self, "Warning", msg + "\n\nContinue generation anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.No:
                return

        gcode = generate_gcode(polylines, self._model.settings, optimize=True)
        self._gcode_lines = gcode.split("\n")
        cmd_count = sum(1 for l in self._gcode_lines if l.strip() and not l.strip().startswith(";"))

        self._serial_panel.set_gcode(self._gcode_lines)
        self._status_msg(
            f"G-code compiled: {cmd_count} commands, {len(polylines)} strokes"
        )

        if self.act_preview_gcode.isChecked():
            self._scene.set_gcode_preview(polylines, show=True)

    def _on_export_gcode(self):
        self._on_generate_gcode()
        if not self._gcode_lines:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("export_gcode"), "plotter_job.gcode",
            "G-code Files (*.gcode *.nc *.txt)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(self._gcode_lines))
                self._status_msg(f"G-code saved: {os.path.basename(path)}")
                QMessageBox.information(self, "Done", f"G-code saved:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save G-code:\n{e}")

    def _on_toggle_preview(self, checked: bool):
        if checked:
            self._on_generate_gcode()
        else:
            self._scene.set_gcode_preview([], show=False)

    def _on_toggle_grid(self, checked: bool):
        """Toggles the millimeter canvas grid and synchronizes UI controls."""
        self._model.settings.show_grid = checked
        self.act_show_grid.blockSignals(True)
        self.act_show_grid.setChecked(checked)
        self.act_show_grid.blockSignals(False)
        self._toolbox.set_grid_checked(checked)
        self._scene.set_show_grid(checked)

    def _on_send_to_printer(self):
        self._on_generate_gcode()
        if self._gcode_lines:
            self._serial_panel._on_start_print()

    def _on_test_gcode(self, pattern: str):
        from core.gcode_generator import generate_test_gcode

        gcode = generate_test_gcode(self._model.settings, pattern)
        self._gcode_lines = gcode.split("\n")
        self._serial_panel.set_gcode(self._gcode_lines, is_custom=True)

        pattern_name = tr(f"test_{pattern}")
        box = QMessageBox(self)
        box.setWindowTitle(f"{tr('action_test_patterns')}: {pattern_name}")
        box.setText(
            f"{tr('action_test_patterns')}: '{pattern_name}'\n\n"
            f"Work Area: {self._model.settings.print_area_w:.1f} × "
            f"{self._model.settings.print_area_h:.1f} mm\n"
            f"Z Draw: {self._model.settings.z_down:.2f} mm  |  "
            f"Z Lift: {self._model.settings.z_up:.2f} mm"
        )
        box.setIcon(QMessageBox.Information)

        btn_print = box.addButton(tr("btn_print_now"), QMessageBox.AcceptRole)
        btn_save = box.addButton(tr("btn_save_gcode"), QMessageBox.ActionRole)
        btn_cancel = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(btn_print)

        box.exec_()
        clicked = box.clickedButton()

        if clicked == btn_print:
            self._serial_panel._on_start_print()
        elif clicked == btn_save:
            path, _ = QFileDialog.getSaveFileName(
                self, tr("btn_save_gcode"),
                f"test_{pattern}.gcode",
                "G-code Files (*.gcode *.nc *.txt)",
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(gcode)
                self._status_msg(f"Test G-code saved: {os.path.basename(path)}")

        self._status_msg(f"Test '{pattern_name}' loaded")

    def _on_print_finished(self, success: bool):
        if success:
            self._status_msg("✅ Print completed successfully!")
        else:
            self._status_msg("❌ Print interrupted")

    def _status_msg(self, msg: str, timeout: int = 5000):
        self._status.showMessage(msg, timeout)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self._on_delete_selected()
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            valid_exts = (".svg", ".png", ".jpg", ".jpeg", ".bmp", ".ppen", ".json", ".ppj", ".gcode", ".nc")
            if any(u.toLocalFile().lower().endswith(valid_exts) for u in urls if u.isLocalFile()):
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            valid_exts = (".svg", ".png", ".jpg", ".jpeg", ".bmp", ".ppen", ".json", ".ppj", ".gcode", ".nc")
            dropped = False
            for u in urls:
                if u.isLocalFile():
                    path = u.toLocalFile()
                    if path.lower().endswith(valid_exts):
                        self._on_file_dropped(path)
                        dropped = True
            if dropped:
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def closeEvent(self, event):
        try:
            save_app_settings(self._model.settings)
        except Exception as e:
            print(f"Warning: Failed to auto-save settings on exit: {e}")
        super().closeEvent(event)

