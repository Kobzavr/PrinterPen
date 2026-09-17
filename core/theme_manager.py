"""
theme_manager.py — Runtime theme switching engine for PrinterPen (Dark / Light).

Maintains current theme state, loads QSS stylesheets, and notifies registered listeners.
"""
from __future__ import annotations
import os
import sys
from typing import Callable, List, Optional

from PyQt5.QtWidgets import QApplication

_current_theme: str = "dark"
_theme_listeners: List[Callable[[str], None]] = []


def _resolve_styles_dir() -> str:
    """Resolves base directory where resources/styles/ resides."""
    if getattr(sys, "frozen", False):
        # Running inside PyInstaller bundle or portable directory
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "resources", "styles")


def get_theme() -> str:
    """Returns the active theme code ('dark' or 'light')."""
    return _current_theme


def register_theme_listener(callback: Callable[[str], None]) -> None:
    """Registers a callback function to be called whenever the theme changes."""
    if callback not in _theme_listeners:
        _theme_listeners.append(callback)


def unregister_theme_listener(callback: Callable[[str], None]) -> None:
    """Removes a previously registered theme listener callback."""
    if callback in _theme_listeners:
        _theme_listeners.remove(callback)


def get_theme_stylesheet(theme_name: str) -> str:
    """Loads and returns the QSS content for the given theme name."""
    styles_dir = _resolve_styles_dir()
    theme_file = "dark.qss" if theme_name == "dark" else "light.qss"
    full_path = os.path.join(styles_dir, theme_file)

    if not os.path.exists(full_path):
        # Fallback to resources/style.qss if styles dir missing
        fallback = os.path.join(os.path.dirname(styles_dir), "style.qss")
        if os.path.exists(fallback):
            full_path = fallback

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[ThemeManager] Warning: could not load theme '{theme_name}': {e}", file=sys.stderr)
        return ""


def set_theme(theme_name: str, app: Optional[QApplication] = None) -> None:
    """
    Sets the active theme ('dark' or 'light'), applies the stylesheet to QApplication,
    and invokes all registered listeners.
    """
    global _current_theme
    norm_theme = "light" if str(theme_name).lower() == "light" else "dark"
    _current_theme = norm_theme

    qapp = app or QApplication.instance()
    if qapp is not None:
        qss = get_theme_stylesheet(norm_theme)
        qapp.setStyleSheet(qss)

    for cb in list(_theme_listeners):
        try:
            cb(norm_theme)
        except Exception as e:
            print(f"[ThemeManager] Error in theme listener {cb}: {e}", file=sys.stderr)


def toggle_theme(app: Optional[QApplication] = None) -> str:
    """Toggles between 'dark' and 'light' themes and returns the new theme name."""
    new_theme = "light" if _current_theme == "dark" else "dark"
    set_theme(new_theme, app)
    return new_theme
