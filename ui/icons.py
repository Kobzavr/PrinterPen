"""
icons.py — Cross-platform vector icons for PrinterPen.

Generates sharp, theme-friendly QIcons from SVG definitions.
Independent of OS-specific emoji fonts (works identically on Windows, Linux/Ubuntu, and macOS).
"""
from __future__ import annotations
import os
from typing import Dict, Optional
from PyQt5.QtGui import QIcon, QPixmap, QPainter
from PyQt5.QtCore import Qt, QByteArray, QSize
from PyQt5.QtSvg import QSvgRenderer

# Clean modern vector icons (viewBox 0 0 24 24)
ICON_SVGS: Dict[str, str] = {
    # Text / Pen tool: Sleek pen with drawing baseline
    "text": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="#2196F3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M12 20h9"/>'
        '<path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>'
        '</svg>'
    ),
    # Image / SVG import tool: Picture frame with sun and landscape
    "image": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="#4CAF50" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
        '<circle cx="8.5" cy="8.5" r="1.5" fill="#4CAF50"/>'
        '<polyline points="21 15 16 10 5 21"/>'
        '</svg>'
    ),
    # Delete tool: Clean trash can with lid
    "delete": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="#E53935" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="3 6 5 6 21 6"/>'
        '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
        '<line x1="10" y1="11" x2="10" y2="17"/>'
        '<line x1="14" y1="11" x2="14" y2="17"/>'
        '</svg>'
    ),
    # Fit to window / Viewport zoom: 4-corner expand frame
    "fit": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="#FF9800" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>'
        '</svg>'
    ),
    # Folder: Clean directory folder
    "folder": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="#FFA000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'
        '</svg>'
    ),
    # Refresh: Modern sync arrows
    "refresh": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="#2196F3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="23 4 23 10 17 10"/>'
        '<polyline points="1 20 1 14 7 14"/>'
        '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>'
        '</svg>'
    ),
    # Compile / Generate G-code: Code brackets with slash
    "compile": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="#26A69A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="16 18 22 12 16 6"/>'
        '<polyline points="8 6 2 12 8 18"/>'
        '<line x1="14" y1="4" x2="10" y2="20"/>'
        '</svg>'
    ),
    # Start / Play: Crisp green forward triangle
    "play": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="#4CAF50" stroke="#4CAF50" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polygon points="6 4 20 12 6 20 6 4"/>'
        '</svg>'
    ),
    # Pause: Clean amber double bars
    "pause": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="#FFA000" stroke="#FFA000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="6" y="4" width="4" height="16" rx="1"/>'
        '<rect x="14" y="4" width="4" height="16" rx="1"/>'
        '</svg>'
    ),
    # Stop: Square red symbol
    "stop": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="#E53935" stroke="#E53935" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="4" y="4" width="16" height="16" rx="2"/>'
        '</svg>'
    ),
    # Dark Theme: Crescent moon
    "moon": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="#90CAF9" stroke="#90CAF9" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
        '</svg>'
    ),
    # Light Theme: Sun with rays
    "sun": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="#FFA726" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="4" fill="#FFA726"/>'
        '<line x1="12" y1="1" x2="12" y2="4"/>'
        '<line x1="12" y1="20" x2="12" y2="23"/>'
        '<line x1="4.22" y1="4.22" x2="6.34" y2="6.34"/>'
        '<line x1="17.66" y1="17.66" x2="19.78" y2="19.78"/>'
        '<line x1="1" y1="12" x2="4" y2="12"/>'
        '<line x1="20" y1="12" x2="23" y2="12"/>'
        '<line x1="4.22" y1="19.78" x2="6.34" y2="17.66"/>'
        '<line x1="17.66" y1="6.34" x2="19.78" y2="4.22"/>'
        '</svg>'
    ),
    # Grid Tool: Precision millimeter matrix grid
    "grid": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="#00BCD4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
        '<line x1="3" y1="9" x2="21" y2="9"/>'
        '<line x1="3" y1="15" x2="21" y2="15"/>'
        '<line x1="9" y1="3" x2="9" y2="21"/>'
        '<line x1="15" y1="3" x2="15" y2="21"/>'
        '</svg>'
    ),
}

_icon_cache: Dict[str, QIcon] = {}


def get_icon(name: str, size: int = 24) -> QIcon:
    """
    Returns a scalable, crisp QIcon by name.
    Caches icons in memory for optimal performance.
    """
    cache_key = f"{name}_{size}"
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    svg_data = ICON_SVGS.get(name)
    if not svg_data:
        return QIcon()

    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(p)
    p.end()

    ico = QIcon(pix)
    _icon_cache[cache_key] = ico
    return ico


def export_svg_icons_to_disk(target_dir: str):
    """Utility to write SVG files to resources/icons directory for git distribution."""
    os.makedirs(target_dir, exist_ok=True)
    for name, svg in ICON_SVGS.items():
        filepath = os.path.join(target_dir, f"{name}.svg")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(svg)
        except Exception:
            pass
