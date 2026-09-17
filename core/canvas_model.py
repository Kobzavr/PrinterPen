"""
canvas_model.py — Canvas data model and printer configuration.

Stores the list of objects (CanvasItem) and workspace/printer settings.
Independent of PyQt — pure business logic.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import json

# Default G-code header template
DEFAULT_GCODE_HEADER = (
    "G90\n"
    "G21\n"
    "M84 S0\n"
    "G28 X Y\n"
    "M420 S1\n"
    "G0 Z{z_up} F{f_travel}"
)

# Default G-code footer template
DEFAULT_GCODE_FOOTER = (
    "G0 Z{z_up}\n"
    "G0 X0 Y220 Z20 F{f_travel}\n"
    "M84"
)


@dataclass
class PrinterSettings:
    """Printer hardware parameters, pen offset, speeds, and custom G-code templates."""

    # ── Physical Printer Travel Limits (mm) ───────────────────
    printer_max_w: float = 220.0   # Ender 3 V3 SE default: 220 mm
    printer_max_h: float = 220.0

    # ── Pen Mount Offset relative to Nozzle (mm) ──────────────
    offset_x: float = 39.5   # Pen is 39.5 mm to the right of nozzle
    offset_y: float = 0.0

    # ── Z Axis Calibration (mm) ───────────────────────────────
    pen_z_offset: float = 2.0    # Pen tip is physically 2.0 mm below nozzle
    z_lift: float = 1.5          # Rapid travel clearance lift above drawing contact
    z_draw_offset: float = 0.5   # Pen pressure adjustment (>0: lighter, 0: exact, <0: firmer)

    # ── Physical Pen Properties ───────────────────────────────
    pen_width: float = 0.5       # Pen tip diameter in mm (for preview and path merging)

    # ── Orientation ───────────────────────────────────────────
    invert_y: bool = True        # Invert Y so canvas top (Y=0) maps to printer back

    # ── Speeds (mm/min) ───────────────────────────────────────
    feed_travel: float = 3000.0  # Rapid travel speed (G0)
    feed_draw: float = 1500.0    # Drawing speed (G1)

    # ── Serial Connection ─────────────────────────────────────
    port: str = ""
    baudrate: int = 115200

    # ── UI Language & Theme ───────────────────────────────────
    language: str = "en"         # "en" or "ru"
    theme: str = "dark"          # "dark" or "light"
    show_grid: bool = True       # Dynamic millimeter grid on canvas

    # ── Customizable G-code Templates ─────────────────────────
    gcode_header: str = DEFAULT_GCODE_HEADER
    gcode_footer: str = DEFAULT_GCODE_FOOTER

    # ── Computed Geometry Properties ──────────────────────────
    @property
    def z_down(self) -> float:
        """Z position during drawing: pen_z_offset + z_draw_offset."""
        return self.pen_z_offset + self.z_draw_offset

    @property
    def z_up(self) -> float:
        """Z position during travel moves: z_down + z_lift."""
        return self.pen_z_offset + self.z_draw_offset + self.z_lift

    @property
    def print_area_w(self) -> float:
        """Available canvas width: printer_max_w minus absolute X pen offset."""
        return max(1.0, self.printer_max_w - abs(self.offset_x))

    @property
    def print_area_h(self) -> float:
        """Available canvas height: printer_max_h minus absolute Y pen offset."""
        return max(1.0, self.printer_max_h - abs(self.offset_y))

    @property
    def paper_x(self) -> float:
        """Left coordinate of printable paper area on printer bed (mm)."""
        return abs(self.offset_x) if self.offset_x > 0 else 0.0

    @property
    def paper_y(self) -> float:
        """Top coordinate of printable paper area on printer bed (mm)."""
        return abs(self.offset_y) if self.offset_y > 0 else 0.0

    def to_dict(self) -> dict:
        """Serializes all fields to dictionary."""
        import dataclasses
        return {f.name: getattr(self, f.name) for f in dataclasses.fields(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "PrinterSettings":
        """Deserializes fields from dictionary with defaults for missing keys."""
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(cls)}
        obj = cls()
        for k, v in d.items():
            if k in field_names:
                setattr(obj, k, v)
        return obj


@dataclass
class CanvasObjectData:
    """Serializable descriptor of a single canvas object."""
    obj_type: str          # "text" | "svg" | "raster"
    obj_id: int

    # Center position (mm)
    x: float = 0.0
    y: float = 0.0

    # Rotation (degrees)
    rotation: float = 0.0

    # Scaling factor
    scale_x: float = 1.0
    scale_y: float = 1.0

    # Type-specific payload
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "obj_type": self.obj_type,
            "obj_id": self.obj_id,
            "x": self.x,
            "y": self.y,
            "rotation": self.rotation,
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CanvasObjectData":
        return cls(
            obj_type=d.get("obj_type", "text"),
            obj_id=d.get("obj_id", 1),
            x=d.get("x", 0.0),
            y=d.get("y", 0.0),
            rotation=d.get("rotation", 0.0),
            scale_x=d.get("scale_x", 1.0),
            scale_y=d.get("scale_y", 1.0),
            extra=d.get("extra", {}),
        )


class CanvasModel:
    """Model managing project data (settings and objects)."""

    def __init__(self):
        self.settings = PrinterSettings()
        self.objects: List[CanvasObjectData] = []
        self._next_id = 1

    def add_object(self, obj_type: str, x: float = 0, y: float = 0,
                   extra: Optional[dict] = None) -> CanvasObjectData:
        obj = CanvasObjectData(
            obj_type=obj_type,
            obj_id=self._next_id,
            x=x,
            y=y,
            extra=extra or {},
        )
        self._next_id += 1
        self.objects.append(obj)
        return obj

    def remove_object(self, obj_id: int):
        self.objects = [o for o in self.objects if o.obj_id != obj_id]

    def get_object(self, obj_id: int) -> Optional[CanvasObjectData]:
        for o in self.objects:
            if o.obj_id == obj_id:
                return o
        return None

    def save_project(self, filepath: str, items: list):
        """
        Saves the project (.ppen / .json) including settings and canvas items.
        Stores both absolute and relative file paths for external assets.
        """
        import os
        from ui.canvas_items import MM_TO_PX, TextItem, SvgItem, RasterItem

        proj_dir = os.path.dirname(os.path.abspath(filepath))
        serialized_items = []

        for item in items:
            item_data = {
                "x_mm": item.pos().x() / MM_TO_PX,
                "y_mm": item.pos().y() / MM_TO_PX,
                "rotation": item.rotation(),
                "scale": item.scale(),
                "is_locked": getattr(item, "is_locked", False),
                "is_hidden": getattr(item, "is_hidden", False),
            }

            if isinstance(item, TextItem):
                item_data.update({
                    "type": "text",
                    "text": item.text,
                    "font_family": item.font_family,
                    "font_size_mm": item.font_size_mm,
                    "bold": getattr(item, "_bold", False),
                    "italic": getattr(item, "_italic", False),
                    "enable_infill": getattr(item, "enable_infill", False),
                    "infill_pattern": getattr(item, "infill_pattern", "linear"),
                    "infill_spacing_mm": getattr(item, "infill_spacing_mm", 0.5),
                    "infill_angle": getattr(item, "infill_angle", 45.0),
                })
            elif isinstance(item, SvgItem):
                svg_abs = os.path.abspath(item.svg_path)
                try:
                    rel_p = os.path.relpath(svg_abs, proj_dir)
                except ValueError:
                    rel_p = ""
                item_data.update({
                    "type": "svg",
                    "svg_path": svg_abs,
                    "rel_path": rel_p,
                    "width_mm": item.width_mm,
                    "enable_infill": getattr(item, "enable_infill", False),
                    "infill_spacing_mm": getattr(item, "infill_spacing_mm", 0.5),
                    "color_configs": getattr(item, "color_configs", []),
                })
            elif isinstance(item, RasterItem):
                img_abs = os.path.abspath(item.image_path)
                try:
                    rel_p = os.path.relpath(img_abs, proj_dir)
                except ValueError:
                    rel_p = ""
                item_data.update({
                    "type": "raster",
                    "image_path": img_abs,
                    "rel_path": rel_p,
                    "width_mm": item.width_mm,
                    "method": getattr(item, "method", "contour"),
                    "threshold1": getattr(item, "threshold1", 50),
                    "threshold2": getattr(item, "threshold2", 150),
                    "contour_thresh": getattr(item, "contour_thresh", 128),
                    "auto_thresh": getattr(item, "auto_thresh", True),
                    "invert": getattr(item, "invert", False),
                    "smooth_level": getattr(item, "smooth_level", 2),
                    "enable_infill": getattr(item, "enable_infill", False),
                    "infill_pattern": getattr(item, "infill_pattern", "linear"),
                    "infill_spacing_mm": getattr(item, "infill_spacing_mm", 0.5),
                    "infill_angle": getattr(item, "infill_angle", 45.0),
                    "infill_min_area_mm2": getattr(item, "infill_min_area_mm2", 2.0),
                    "infill_adaptive_range": getattr(item, "infill_adaptive_range", 128),
                    "min_path_len_mm": getattr(item, "min_path_len_mm", 0.5),
                    "pen_width_filter": getattr(item, "pen_width_filter", True),
                })
            else:
                continue

            serialized_items.append(item_data)

        data = {
            "app": "PrinterPen",
            "version": 1,
            "settings": self.settings.to_dict(),
            "items": serialized_items,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_project(self, filepath: str) -> Tuple[PrinterSettings, list]:
        """
        Loads project file and returns (PrinterSettings, list_of_raw_item_dicts).
        Supports backwards compatibility with earlier versions.
        """
        import os

        proj_dir = os.path.dirname(os.path.abspath(filepath))
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        settings = PrinterSettings.from_dict(data.get("settings", {}))
        self.settings = settings

        raw_items = data.get("items", [])
        resolved_items = []

        for item_data in raw_items:
            resolved = dict(item_data)
            # Resolve relative asset path if present
            if "rel_path" in resolved and resolved["rel_path"]:
                cand = os.path.normpath(os.path.join(proj_dir, resolved["rel_path"]))
                if os.path.exists(cand):
                    if resolved.get("type") == "svg":
                        resolved["svg_path"] = cand
                    elif resolved.get("type") == "raster":
                        resolved["image_path"] = cand

            resolved_items.append(resolved)

        return settings, resolved_items


def export_polylines_to_svg(
    polylines: List[List[Tuple[float, float]]],
    width_mm: float,
    height_mm: float,
    filepath: str,
):
    """Exports vectorized polyline strokes to a standard SVG file."""
    lines = [
        f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm:.1f}mm" height="{height_mm:.1f}mm" '
        f'viewBox="0 0 {width_mm:.1f} {height_mm:.1f}">',
        f'  <title>PrinterPen Export</title>',
        f'  <rect width="100%" height="100%" fill="none" stroke="#ddd" stroke-width="0.2"/>',
        f'  <g fill="none" stroke="#000000" stroke-width="0.3" stroke-linecap="round" stroke-linejoin="round">',
    ]

    for pl in polylines:
        if len(pl) < 2:
            continue
        pts = " ".join(f"{x:.3f},{y:.3f}" for x, y in pl)
        lines.append(f'    <polyline points="{pts}" />')

    lines.append('  </g>')
    lines.append('</svg>')

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def get_app_settings_path() -> str:
    """Returns the persistent settings JSON file path."""
    import os
    config_dir = os.path.join(os.path.expanduser("~"), ".printerpen")
    try:
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "settings.json")
    except Exception:
        return os.path.join(os.getcwd(), "plotter_settings.json")


def load_app_settings() -> PrinterSettings:
    """Loads persistent settings from disk, falling back to defaults if not found."""
    import json
    import os
    path = get_app_settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PrinterSettings.from_dict(data)
        except Exception as e:
            print(f"Warning: Failed to load app settings from {path}: {e}")
    return PrinterSettings()


def save_app_settings(settings: PrinterSettings):
    """Saves persistent settings to disk."""
    import json
    path = get_app_settings_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings.to_dict(), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Failed to save app settings to {path}: {e}")

