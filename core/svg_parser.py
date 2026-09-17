"""
svg_parser.py — Parses SVG vector files into plotter polyline strokes (in mm).

Uses svgpathtools to extract and discretize SVG path elements.
Bezier curves and arcs are approximated into linear segments.
"""
from __future__ import annotations
from typing import List, Tuple, Optional
import math

try:
    from svgpathtools import svg2paths2, Path, Line, CubicBezier, QuadraticBezier, Arc
    HAS_SVGPATHTOOLS = True
except ImportError:
    HAS_SVGPATHTOOLS = False

# Number of linear approximation segments per curve
CURVE_STEPS = 30


def parse_svg(filepath: str, target_width_mm: Optional[float] = None) -> List[List[Tuple[float, float]]]:
    """
    Parses an SVG file and returns a list of polyline strokes in mm.

    Args:
        filepath: path to .svg file
        target_width_mm: optional scaling target in mm.

    Returns:
        List of polylines — each a list of (x, y) coordinates in mm.
    """
    if not HAS_SVGPATHTOOLS:
        raise ImportError("svgpathtools is not installed. Install with: pip install svgpathtools")

    paths, attributes, svg_attrs = svg2paths2(filepath)

    scale = _compute_scale(svg_attrs, target_width_mm)

    all_polylines: List[List[Tuple[float, float]]] = []
    for path in paths:
        polylines = _path_to_polylines(path, scale)
        all_polylines.extend(polylines)

    return all_polylines


def _compute_scale(svg_attrs: dict, target_width_mm: Optional[float]) -> float:
    """Computes px to mm scaling factor from SVG attributes."""
    viewbox = svg_attrs.get("viewBox", svg_attrs.get("viewbox", ""))
    width_attr = svg_attrs.get("width", "")

    svg_width_px = None

    if viewbox:
        try:
            parts = viewbox.replace(",", " ").split()
            svg_width_px = float(parts[2])
        except (ValueError, IndexError):
            pass

    if svg_width_px is None and width_attr:
        svg_width_px = _parse_length_to_px(width_attr)

    if target_width_mm is not None and svg_width_px:
        return target_width_mm / max(svg_width_px, 1)
    elif svg_width_px:
        # Standard CSS assumption: 96 DPI -> 25.4 / 96 mm per px
        return 25.4 / 96.0
    else:
        return 1.0


def _parse_length_to_px(value: str) -> Optional[float]:
    """Converts CSS length units ('100mm', '200px', '5in') to pixels at 96 DPI."""
    value = value.strip()
    try:
        if value.endswith("mm"):
            return float(value[:-2]) * 96 / 25.4
        elif value.endswith("cm"):
            return float(value[:-2]) * 96 / 2.54
        elif value.endswith("in"):
            return float(value[:-2]) * 96
        elif value.endswith("pt"):
            return float(value[:-2]) * 96 / 72
        elif value.endswith("px"):
            return float(value[:-2])
        else:
            return float(value)
    except ValueError:
        return None


def _path_to_polylines(path: "Path", scale: float) -> List[List[Tuple[float, float]]]:
    """Converts an SVG Path object into polylines."""
    if not path:
        return []

    polylines: List[List[Tuple[float, float]]] = []
    current: List[Tuple[float, float]] = []
    last_end = None

    for segment in path:
        if isinstance(segment, Line):
            start = (segment.start.real * scale, segment.start.imag * scale)
            end = (segment.end.real * scale, segment.end.imag * scale)

            if last_end is not None and _dist(last_end, start) > 0.01:
                if current:
                    polylines.append(current)
                current = [start]
            elif not current:
                current = [start]

            current.append(end)
            last_end = end

        elif isinstance(segment, (CubicBezier, QuadraticBezier)):
            pts = _approx_curve(segment, CURVE_STEPS, scale)
            start = pts[0]

            if last_end is not None and _dist(last_end, start) > 0.01:
                if current:
                    polylines.append(current)
                current = [start]
            elif not current:
                current = [start]

            current.extend(pts[1:])
            last_end = pts[-1]

        elif isinstance(segment, Arc):
            pts = _approx_arc(segment, CURVE_STEPS, scale)
            start = pts[0]

            if last_end is not None and _dist(last_end, start) > 0.01:
                if current:
                    polylines.append(current)
                current = [start]
            elif not current:
                current = [start]

            current.extend(pts[1:])
            last_end = pts[-1]

    if current:
        polylines.append(current)

    return [pl for pl in polylines if len(pl) >= 2]


def _approx_curve(segment, steps: int, scale: float) -> List[Tuple[float, float]]:
    """Approximates Bezier curve with piecewise linear segments."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        p = segment.point(t)
        pts.append((p.real * scale, p.imag * scale))
    return pts


def _approx_arc(segment, steps: int, scale: float) -> List[Tuple[float, float]]:
    """Approximates SVG Arc with piecewise linear segments."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        try:
            p = segment.point(t)
            pts.append((p.real * scale, p.imag * scale))
        except Exception:
            pass
    return pts


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
