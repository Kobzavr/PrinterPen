"""
PrinterPen — 3D Printer to Plotter desktop application.
Application entry point.
"""
import os
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt
from ui.main_window import MainWindow
from core.font_manager import install_qt_message_handler, FontManager


def main():
    # Install message handler to silence benign OpenType/HarfBuzz warnings
    install_qt_message_handler()

    # Set AppUserModelID on Windows so the application icon shows correctly on the taskbar
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("printerpen.plotter.app.1.1")
        except Exception:
            pass

    # Enable HiDPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("PrinterPen")
    app.setApplicationVersion("1.1.0")
    app.setOrganizationName("PrinterPen")

    # Load custom fonts and watch fonts/ directory for additions
    font_mgr = FontManager.get_instance()
    font_mgr.scan_and_load_fonts()
    font_mgr.start_file_watcher()

    # Application icon
    base_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(base_dir, "logo.ico")
    if os.path.exists(logo_path):
        app_icon = QIcon(logo_path)
        app.setWindowIcon(app_icon)

    # Apply initial theme stylesheet
    from core.theme_manager import get_theme, set_theme
    set_theme(get_theme(), app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
