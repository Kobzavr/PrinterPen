"""
text_to_path.py — Converts text string glyphs to polyline stroke paths using QPainterPath.

Returns a list of subpaths, each being a list of points [(x, y), ...] in mm.
"""
from __future__ import annotations
from typing import List, Tuple
import math

from PyQt5.QtGui import QPainterPath, QFont, QFontMetricsF, QTransform, QImage, QPainter, QColor
from PyQt5.QtCore import Qt, QPointF
import numpy as np

from core.raster_tracer import generate_infill

# Step resolution for cubic Bezier discretization
BEZIER_STEPS = 20

# 96 DPI / 25.4 mm per inch
PX_PER_MM = 3.7795275591


def text_to_paths(
    text: str,
    font_family: str,
    font_size_mm: float,
    bold: bool = False,
    italic: bool = False,
    letter_spacing: float = 0.0,
) -> List[List[Tuple[float, float]]]:
    """
    Converts a text string to polyline contours in mm.

    Args:
        text: String of text
        font_family: Font family name
        font_size_mm: Font size in mm
        bold: Bold weight
        italic: Italic slant
        letter_spacing: Extra letter spacing in mm

    Returns:
        List of subpaths, each a list of (x, y) coordinates in mm.
    """
    font_size_pt = font_size_mm * 72.0 / 25.4

    font = QFont(font_family)
    font.setPointSizeF(font_size_pt)
    font.setBold(bold)
    font.setItalic(italic)
    if letter_spacing != 0.0:
        font.setLetterSpacing(QFont.AbsoluteSpacing, letter_spacing * PX_PER_MM)

    path = QPainterPath()
    path.addText(0, 0, font, text)

    return _painter_path_to_polylines(path, scale=1.0 / PX_PER_MM)


def _painter_path_to_polylines(
    path: QPainterPath,
    scale: float = 1.0,
) -> List[List[Tuple[float, float]]]:
    """
    Breaks a QPainterPath down into polylines.
    Approximates Bezier segments with line segments.
    """
    subpaths: List[List[Tuple[float, float]]] = []
    current: List[Tuple[float, float]] = []
    current_pos = QPointF(0, 0)

    count = path.elementCount()
    for i in range(count):
        el = path.elementAt(i)

        if el.type == QPainterPath.MoveToElement:
            if current:
                subpaths.append(current)
            current = [(el.x * scale, el.y * scale)]
            current_pos = QPointF(el.x, el.y)

        elif el.type == QPainterPath.LineToElement:
            current.append((el.x * scale, el.y * scale))
            current_pos = QPointF(el.x, el.y)

        elif el.type == QPainterPath.CurveToElement:
            if i + 2 < count:
                cp1 = QPointF(el.x, el.y)
                cp2_el = path.elementAt(i + 1)
                end_el = path.elementAt(i + 2)
                cp2 = QPointF(cp2_el.x, cp2_el.y)
                end = QPointF(end_el.x, end_el.y)
                pts = _cubic_bezier_points(current_pos, cp1, cp2, end, BEZIER_STEPS)
                for p in pts[1:]:
                    current.append((p.x() * scale, p.y() * scale))
                current_pos = end

    if current:
        subpaths.append(current)

    return [sp for sp in subpaths if len(sp) >= 2]


def _cubic_bezier_points(
    p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF, steps: int
) -> List[QPointF]:
    """Approximates cubic Bezier curve with piecewise linear points."""
    result = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3 * p0.x() + 3*mt**2*t * p1.x() + 3*mt*t**2 * p2.x() + t**3 * p3.x()
        y = mt**3 * p0.y() + 3*mt**2*t * p1.y() + 3*mt*t**2 * p2.y() + t**3 * p3.y()
        result.append(QPointF(x, y))
    return result


def get_text_bounding_box(
    text: str, font_family: str, font_size_mm: float,
    bold: bool = False, italic: bool = False
) -> Tuple[float, float]:
    """Returns (width, height) bounding box of rendered text in mm."""
    font_size_pt = font_size_mm * 72.0 / 25.4
    font = QFont(font_family)
    font.setPointSizeF(font_size_pt)
    font.setBold(bold)
    font.setItalic(italic)

    path = QPainterPath()
    path.addText(0, 0, font, text)
    br = path.boundingRect()
    return br.width() / PX_PER_MM, br.height() / PX_PER_MM


def generate_text_infill(
    path: QPainterPath,
    pattern: str = "linear",
    spacing_mm: float = 0.5,
    angle_deg: float = 45.0,
    min_area_mm2: float = 0.1,
) -> List[List[Tuple[float, float]]]:
    """
    Generates infill hatching paths strictly bounded inside font glyphs of a QPainterPath.
    Returns polyline paths in mm coordinates matching the text glyph coordinate space.
    """
    if path.isEmpty():
        return []

    br = path.boundingRect()
    if br.width() <= 0 or br.height() <= 0:
        return []

    raster_scale = 10.0
    margin = 4
    w = int(math.ceil(br.width() * raster_scale)) + margin * 2
    h = int(math.ceil(br.height() * raster_scale)) + margin * 2

    qimg = QImage(w, h, QImage.Format_Grayscale8)
    qimg.fill(0)

    painter = QPainter(qimg)
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.translate(-br.x() * raster_scale + margin, -br.y() * raster_scale + margin)
    painter.scale(raster_scale, raster_scale)
    painter.fillPath(path, QColor(255, 255, 255))
    painter.end()

    ptr = qimg.bits()
    ptr.setsize(qimg.byteCount())
    mask = np.array(ptr, copy=True).reshape(h, qimg.bytesPerLine())[:, :w]

    width_mm = w / (raster_scale * PX_PER_MM)
    infill_strokes = generate_infill(
        binary_mask=mask,
        target_width_mm=width_mm,
        pattern=pattern,
        spacing_mm=spacing_mm,
        angle_deg=angle_deg,
        min_area_mm2=min_area_mm2,
    )

    off_x_mm = (br.x() * raster_scale - margin) / (raster_scale * PX_PER_MM)
    off_y_mm = (br.y() * raster_scale - margin) / (raster_scale * PX_PER_MM)

    adjusted = []
    for stroke in infill_strokes:
        adj_stroke = [(x + off_x_mm, y + off_y_mm) for x, y in stroke]
        if len(adj_stroke) >= 2:
            adjusted.append(adj_stroke)

    return adjusted
