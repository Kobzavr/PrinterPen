"""
gcode_generator.py — G-code generator for 3D printer pen plotters.

Takes vectorized polylines (in mm) and printer settings,
and produces clean, Marlin-compatible G-code.
"""
from __future__ import annotations
from typing import List, Tuple, Optional
import math

from core.canvas_model import PrinterSettings, DEFAULT_GCODE_HEADER, DEFAULT_GCODE_FOOTER
from core.path_optimizer import optimize_paths

Polyline = List[Tuple[float, float]]


class GCodeFloat(float):
    """Float wrapper formatting as 2 decimal places by default, preserving custom format specs."""
    def __format__(self, format_spec):
        if not format_spec:
            return f"{self:.2f}"
        return super().__format__(format_spec)


class GCodeInt(float):
    """Number wrapper formatting as integer by default, preserving custom format specs."""
    def __format__(self, format_spec):
        if not format_spec:
            return f"{self:.0f}"
        return super().__format__(format_spec)


def _format_custom_gcode(template: str, vars_dict: dict) -> List[str]:
    """Safely formats template variables in custom G-code blocks."""
    lines = []
    for line in template.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            formatted = line.format(**vars_dict)
            lines.append(formatted)
        except Exception:
            lines.append(line)
    return lines


def generate_gcode(
    polylines: List[Polyline],
    settings: PrinterSettings,
    optimize: bool = True,
    add_comments: bool = True,
) -> str:
    """
    Generates G-code from a list of polylines.

    Canvas coordinates map directly to nozzle coordinates.
    The pen draws on the paper at (ax + offset_x, ay + offset_y).
    """
    if not polylines:
        return "; No objects to print\n"

    canvas_w = settings.print_area_w
    canvas_h = settings.print_area_h
    invert_y = settings.invert_y

    adjusted: List[Polyline] = []
    warnings: List[str] = []

    for pl in polylines:
        adj_pl = []
        for (x, y) in pl:
            ax = x - settings.offset_x
            # Invert Y: canvas Y=0 (top) -> printer Y=printer_max_h (back)
            if invert_y:
                ay = settings.printer_max_h - y
            else:
                ay = y - settings.offset_y

            # Boundary check against physical printer travel
            if ax < -0.05 or ay < -0.05 or ax > settings.printer_max_w + 0.05 or ay > settings.printer_max_h + 0.05:
                warnings.append(
                    f"Nozzle point ({ax:.1f}, {ay:.1f}) exceeds physical travel "
                    f"({settings.printer_max_w:.1f}×{settings.printer_max_h:.1f} mm)"
                )
            adj_pl.append((ax, ay))
        adjusted.append(adj_pl)

    if optimize:
        adjusted = optimize_paths(adjusted)

    lines: List[str] = []

    # ── Program attribution header (always added in code) ───
    lines.append("; PrinterPen G-code v1.1")
    lines.append("; Plotter mode: extruder disabled, heated bed off")
    lines.append(f"; Canvas: {canvas_w:.1f}x{canvas_h:.1f}mm  Offset X:{settings.offset_x:.1f} Y:{settings.offset_y:.1f}")
    lines.append(f"; Z draw:{settings.z_down:.2f}mm  Z travel:{settings.z_up:.2f}mm  Pen tip:{settings.pen_width:.2f}mm")
    lines.append(f"; Feed draw:{settings.feed_draw:.0f}  travel:{settings.feed_travel:.0f}")
    lines.append("")

    if warnings:
        for w in warnings[:5]:
            lines.append(f"; WARNING: {w}")
        if len(warnings) > 5:
            lines.append(f"; ... and {len(warnings) - 5} more boundary warnings")
        lines.append("")

    z_up = settings.z_up
    z_down = settings.z_down
    f_travel = settings.feed_travel
    f_draw = settings.feed_draw

    fmt_vars = {
        "z_up": GCodeFloat(z_up),
        "z_down": GCodeFloat(z_down),
        "f_travel": GCodeInt(f_travel),
        "f_draw": GCodeInt(f_draw),
        "canvas_w": GCodeFloat(canvas_w),
        "canvas_h": GCodeFloat(canvas_h),
    }

    # ── User-configurable Start / Init G-code ───────────────
    lines.append("; === Init ===")
    header_template = settings.gcode_header or DEFAULT_GCODE_HEADER
    for h_line in _format_custom_gcode(header_template, fmt_vars):
        lines.append(h_line)
    lines.append("")

    # ── Drawing moves ───────────────────────────────────────
    lines.append("; === Draw ===")
    pen_is_up = True

    for pl_idx, pl in enumerate(adjusted):
        if not pl:
            continue

        if add_comments:
            lines.append(f"; seg {pl_idx + 1}/{len(adjusted)}")

        # Travel to start of stroke
        x0, y0 = pl[0]
        if not pen_is_up:
            lines.append(f"G0 Z{z_up:.2f}")
            pen_is_up = True

        lines.append(f"G0 X{x0:.3f} Y{y0:.3f} F{f_travel:.0f}")

        # Lower pen to paper
        lines.append(f"G1 Z{z_down:.2f} F{f_travel:.0f}")
        pen_is_up = False

        # Draw stroke
        curr_x, curr_y = x0, y0
        n_pts = len(pl)
        for i, (x, y) in enumerate(pl[1:]):
            is_last = (i == n_pts - 2)
            dist = math.hypot(x - curr_x, y - curr_y)
            # Skip redundant micro-moves smaller than 20 microns (0.02 mm),
            # but always output the stroke endpoint unless it's identical (< 0.001 mm).
            if dist < 0.001 or (not is_last and dist < 0.02):
                continue
            lines.append(f"G1 X{x:.3f} Y{y:.3f} F{f_draw:.0f}")
            curr_x, curr_y = x, y

    # ── User-configurable End / Footer G-code ───────────────
    lines.append("")
    lines.append("; === End ===")
    if not pen_is_up:
        lines.append(f"G0 Z{z_up:.2f}")
        pen_is_up = True
    footer_template = settings.gcode_footer or DEFAULT_GCODE_FOOTER
    for f_line in _format_custom_gcode(footer_template, fmt_vars):
        lines.append(f_line)

    return "\n".join(lines)


def estimate_print_time(polylines: List[Polyline], settings: PrinterSettings) -> float:
    """Estimates total print time in seconds."""
    from core.path_optimizer import total_draw_distance, total_travel_distance

    draw_dist = total_draw_distance(polylines)
    travel_dist = total_travel_distance(polylines)

    draw_time = draw_dist / (settings.feed_draw / 60.0)      # mm / (mm/s)
    travel_time = travel_dist / (settings.feed_travel / 60.0)

    return draw_time + travel_time


def validate_polylines(
    polylines: List[Polyline],
    settings: PrinterSettings,
) -> List[str]:
    """
    Validates that all path coordinates fit within the accessible paper area.
    Returns a list of warning strings (empty if valid).
    """
    errors = []
    min_x = settings.paper_x
    max_x = min_x + settings.print_area_w
    min_y = settings.paper_y
    max_y = min_y + settings.print_area_h

    for i, pl in enumerate(polylines):
        for x, y in pl:
            if x < min_x - 0.05 or y < min_y - 0.05 or x > max_x + 0.05 or y > max_y + 0.05:
                errors.append(
                    f"Segment {i+1}: point ({x:.1f}, {y:.1f}) is outside "
                    f"paper area (X: {min_x:.1f}–{max_x:.1f}, Y: {min_y:.1f}–{max_y:.1f} mm)"
                )
                break
    return errors


def generate_test_gcode(settings: PrinterSettings, pattern: str = "border") -> str:
    """
    Generates calibration test patterns for plotter verification.

    Patterns:
      "border"    — Rectangle along perimeter (verifies offsets and bounds)
      "crosshair" — Center crosshair and diagonals (verifies alignment)
      "grid"      — 5x5 grid (verifies speed and accuracy)
      "spiral"    — Smooth Archimedean spiral (verifies curved motion)
    """
    w = settings.print_area_w
    h = settings.print_area_h
    ox = settings.paper_x
    oy = settings.paper_y
    cx = ox + w / 2
    cy = oy + h / 2

    polylines: List[Polyline] = []

    if pattern == "border":
        polylines = [[(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h), (ox, oy)]]

    elif pattern == "crosshair":
        arm = min(w, h) / 2 * 0.8
        polylines = [
            [(cx - arm, cy), (cx + arm, cy)],
            [(cx, cy - arm), (cx, cy + arm)],
            [(cx - 5, cy - 5), (cx + 5, cy + 5)],
            [(cx + 5, cy - 5), (cx - 5, cy + 5)],
        ]

    elif pattern == "grid":
        cols = 5
        rows = 5
        for i in range(cols + 1):
            x = ox + (w / cols) * i
            polylines.append([(x, oy), (x, oy + h)])
        for j in range(rows + 1):
            y = oy + (h / rows) * j
            polylines.append([(ox, y), (ox + w, y)])

    elif pattern == "spiral":
        pts = []
        turns = 5
        steps = turns * 60
        r_max = min(w, h) / 2 * 0.85
        for i in range(steps + 1):
            t = i / steps
            angle = t * turns * 2 * math.pi
            r = t * r_max
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        polylines = [pts]

    else:
        polylines = [[(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h), (ox, oy)]]

    return generate_gcode(polylines, settings, optimize=False, add_comments=True)
