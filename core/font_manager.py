"""
font_manager.py — Manages custom application fonts and Qt font diagnostics.

Features:
- Dynamically loads TrueType (.ttf) and OpenType (.otf) fonts from the 'fonts/' folder.
- Watches 'fonts/' folder in real time via QFileSystemWatcher for instant hot-reloading.
- Silences harmless OpenType / HarfBuzz script warnings and painter state noise.
- Provides helper to open the fonts folder in native file manager.
"""
from __future__ import annotations
import os
import sys
from typing import List, Set, Optional

from PyQt5.QtCore import QObject, pyqtSignal, QFileSystemWatcher, QUrl, QtMsgType, qInstallMessageHandler
from PyQt5.QtGui import QFontDatabase, QDesktopServices
from PyQt5.QtWidgets import QFontComboBox


def install_qt_message_handler():
    """
    Installs a global Qt message handler to filter out harmless console noise:
    - 'OpenType support missing for "...", script ...' (emitted when Qt font engine checks script tables)
    - 'QPainter::end: Painter ended with ...'
    Genuine errors, fatal messages, and critical warnings are preserved and printed to stderr.
    """
    def _handler(msg_type: int, context, message: str):
        try:
            # Filter harmless HarfBuzz / Windows OpenType script diagnostics
            if "OpenType support missing" in message:
                return
            # Filter QPainter end state noise
            if "QPainter::end" in message:
                return
            # Filter font size zero or negligible floating point rounding notices
            if "QFont::setPointSizeF" in message and "point size <= 0" in message:
                return

            # Pass through genuine warnings and critical messages
            if msg_type == QtMsgType.QtWarningMsg:
                print(f"[Qt Warning] {message}", file=sys.stderr)
            elif msg_type == QtMsgType.QtCriticalMsg:
                print(f"[Qt Critical] {message}", file=sys.stderr)
            elif msg_type == QtMsgType.QtFatalMsg:
                print(f"[Qt Fatal] {message}", file=sys.stderr)
        except Exception:
            pass

    qInstallMessageHandler(_handler)


class FontManager(QObject):
    """
    Singleton manager that scans, loads, and hot-watches custom font files
    from the project 'fonts/' and 'resources/fonts/' directories.
    """
    fonts_updated = pyqtSignal(list)  # Emits list of newly loaded family names

    _instance: Optional["FontManager"] = None

    @classmethod
    def get_instance(cls) -> "FontManager":
        if cls._instance is None:
            cls._instance = FontManager()
        return cls._instance

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._loaded_paths: Set[str] = set()
        self._loaded_families: Set[str] = set()
        self._watcher: Optional[QFileSystemWatcher] = None

        # Resolve primary fonts directory (plotter/fonts or executable/fonts)
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.primary_fonts_dir = os.path.join(base_dir, "fonts")
        self.resources_fonts_dir = os.path.join(base_dir, "resources", "fonts")

        self.ensure_fonts_dir()

    def ensure_fonts_dir(self):
        """Creates the fonts/ folder in the project root if it does not exist yet."""
        try:
            if not os.path.exists(self.primary_fonts_dir):
                os.makedirs(self.primary_fonts_dir, exist_ok=True)
            readme_path = os.path.join(self.primary_fonts_dir, "README.txt")
            if not os.path.exists(readme_path):
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write(
                        "=== PrinterPen Fonts Folder ===\n\n"
                        "Drop your custom TrueType (.ttf) or OpenType (.otf) font files here.\n"
                        "They will automatically appear in the font dropdown list in PrinterPen!\n"
                    )
        except Exception as e:
            print(f"[FontManager] Warning: could not ensure fonts dir: {e}", file=sys.stderr)

    def get_search_directories(self) -> List[str]:
        dirs = []
        if os.path.exists(self.primary_fonts_dir):
            dirs.append(self.primary_fonts_dir)
        if os.path.exists(self.resources_fonts_dir):
            dirs.append(self.resources_fonts_dir)
        return dirs

    def scan_and_load_fonts(self) -> List[str]:
        """
        Scans font search directories for new .ttf / .otf / .ttc files.
        Loads them into QFontDatabase and returns a list of newly loaded font family names.
        """
        new_families: List[str] = []
        dirs = self.get_search_directories()

        for folder in dirs:
            try:
                for fname in os.listdir(folder):
                    if fname.lower().endswith((".ttf", ".otf", ".ttc")):
                        full_path = os.path.abspath(os.path.join(folder, fname))
                        if full_path not in self._loaded_paths:
                            font_id = QFontDatabase.addApplicationFont(full_path)
                            if font_id != -1:
                                self._loaded_paths.add(full_path)
                                fams = QFontDatabase.applicationFontFamilies(font_id)
                                for fam in fams:
                                    if fam not in self._loaded_families:
                                        self._loaded_families.add(fam)
                                        new_families.append(fam)
                            else:
                                # Mark as checked even if failed to avoid repeated loading
                                self._loaded_paths.add(full_path)
            except Exception as e:
                print(f"[FontManager] Error scanning folder {folder}: {e}", file=sys.stderr)

        if new_families:
            self.fonts_updated.emit(new_families)

        return new_families

    def start_file_watcher(self):
        """Initializes real-time file watcher on font folders for automatic hot-reloading."""
        if self._watcher is not None:
            return

        watch_dirs = [d for d in self.get_search_directories() if os.path.exists(d)]
        if not watch_dirs:
            return

        self._watcher = QFileSystemWatcher(watch_dirs, self)
        self._watcher.directoryChanged.connect(self._on_dir_changed)

    def _on_dir_changed(self, path: str):
        """Triggered when files are added, modified, or deleted in watched font folders."""
        self.scan_and_load_fonts()

    def open_fonts_folder(self) -> bool:
        """Opens the project fonts/ folder in the system file manager."""
        self.ensure_fonts_dir()
        if os.path.exists(self.primary_fonts_dir):
            return QDesktopServices.openUrl(QUrl.fromLocalFile(self.primary_fonts_dir))
        return False


class PlotterFontComboBox(QFontComboBox):
    """
    Enhanced QFontComboBox for the plotter:
    - Filters to ScalableFonts only (eliminates old non-vector bitmap fonts).
    - Checks for newly added font files immediately before expanding the popup.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFontFilters(QFontComboBox.ScalableFonts)

    def showPopup(self):
        # Quick check for any newly dropped font files before user sees the list
        try:
            FontManager.get_instance().scan_and_load_fonts()
        except Exception:
            pass
        super().showPopup()
