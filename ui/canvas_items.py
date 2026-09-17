"""
canvas_items.py — Custom QGraphicsScene elements for plotter objects.

TextItem    — Vectorized text outlines (rendered via QPainterPath)
SvgItem     — Scalable Vector Graphics (SVG) object
RasterItem  — Raster image (PNG/JPG/BMP) with real-time Canny vectorization preview
"""
from __future__ import annotations
from typing import Optional, List, Tuple
import math

from PyQt5.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem,
    QGraphicsRectItem, QStyleOptionGraphicsItem, QWidget,
    QGraphicsSceneMouseEvent,
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath, QFont,
    QPixmap, QTransform, QCursor, QImage,
)
from PyQt5.QtCore import Qt, QRectF, QPointF, QSizeF, pyqtSignal, QObject
from PyQt5.QtSvg import QSvgRenderer
import numpy as np


MM_TO_PX = 3.7795275591   # 1 mm = 3.78 px at 96 DPI

HANDLE_SIZE = 8            # Transformation handle size in px
HANDLE_COLOR = QColor("#2196F3")
SELECTION_COLOR = QColor("#2196F3")
PREVIEW_COLOR = QColor("#E53935")    # G-code draw stroke preview color
TRAVEL_COLOR = QColor("#9E9E9E")     # G-code rapid travel preview color

# Margin around content for handles (rotation handle sits 20px above top)
HANDLE_MARGIN = 30


class ItemSignals(QObject):
    """Signals for canvas items (items cannot inherit QObject directly in PyQt5)."""
    selected = pyqtSignal(object)
    changed = pyqtSignal(object)


class BasePlotItem(QGraphicsItem):
    """
    Base class for all canvas objects.
    Supports selection, moving, mouse rotation (with Shift=45° snap), and scaling.
    """

    ITEM_TYPE_TEXT = 1
    ITEM_TYPE_SVG = 2
    ITEM_TYPE_RASTER = 3

    def __init__(self, item_id: int, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.signals = ItemSignals()

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        self._rotation_handle_pos: Optional[QPointF] = None
        self._dragging_rotate = False
        self._rotate_start_angle = 0.0
        self._rotate_start_item_angle = 0.0

        self._scale_handle_pos: Optional[QPointF] = None
        self._dragging_scale = False
        self._scale_start_pos: Optional[QPointF] = None
        self._scale_start_scale = 1.0

        self._is_locked: bool = False
        self._is_hidden: bool = False

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    def set_locked(self, locked: bool):
        self._is_locked = locked
        self.setFlag(QGraphicsItem.ItemIsMovable, not locked)
        self.update()
        self.signals.changed.emit(self)

    @property
    def is_hidden(self) -> bool:
        return self._is_hidden

    def set_hidden(self, hidden: bool):
        self._is_hidden = hidden
        self.setOpacity(0.35 if hidden else 1.0)
        self.update()
        self.signals.changed.emit(self)

    def item_type(self) -> int:
        raise NotImplementedError

    def get_polylines_mm(self) -> List[List[Tuple[float, float]]]:
        """Returns item contours in local mm coordinates."""
        raise NotImplementedError

    def shape_bounding_rect(self) -> QRectF:
        """Returns the actual bounding rectangle of the content."""
        raise NotImplementedError

    def boundingRect(self) -> QRectF:
        """Includes handle margins to prevent ghosting artifacts during redraws."""
        br = self.shape_bounding_rect()
        return br.adjusted(-HANDLE_MARGIN, -HANDLE_MARGIN, HANDLE_MARGIN, HANDLE_MARGIN)

    def get_transformed_polylines_mm(self) -> List[List[Tuple[float, float]]]:
        """Returns contours in global canvas mm coordinates with full transform applied."""
        raw = self.get_polylines_mm()
        result = []
        transform = self.sceneTransform()

        for pl in raw:
            transformed = []
            for (x_mm, y_mm) in pl:
                x_px = x_mm * MM_TO_PX
                y_px = y_mm * MM_TO_PX
                scene_pt = transform.map(QPointF(x_px, y_px))
                transformed.append((scene_pt.x() / MM_TO_PX, scene_pt.y() / MM_TO_PX))
            if transformed:
                result.append(transformed)
        return result

    def _get_bounding_rect_mm(self) -> QRectF:
        """Returns content bounding rect in mm."""
        br = self.shape_bounding_rect()
        return QRectF(
            br.x() / MM_TO_PX, br.y() / MM_TO_PX,
            br.width() / MM_TO_PX, br.height() / MM_TO_PX
        )

    def _rotation_handle_scene_pos(self) -> QPointF:
        br = self.shape_bounding_rect()
        top_center = QPointF(br.center().x(), br.top() - 20)
        return self.mapToScene(top_center)

    def _scale_handle_scene_pos(self) -> QPointF:
        br = self.shape_bounding_rect()
        return self.mapToScene(QPointF(br.right(), br.bottom()))

    def hoverMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self.isSelected():
            if self._is_locked:
                self.setCursor(QCursor(Qt.ArrowCursor))
                super().hoverMoveEvent(event)
                return
            rot_pos = self.mapFromScene(self._rotation_handle_scene_pos())
            sc_pos = self.mapFromScene(self._scale_handle_scene_pos())
            pos = event.pos()
            if (pos - rot_pos).manhattanLength() < HANDLE_SIZE * 1.5:
                self.setCursor(QCursor(Qt.CrossCursor))
            elif (pos - sc_pos).manhattanLength() < HANDLE_SIZE * 1.5:
                self.setCursor(QCursor(Qt.SizeFDiagCursor))
            else:
                self.setCursor(QCursor(Qt.SizeAllCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if self._is_locked:
            self._dragging_rotate = False
            self._dragging_scale = False
            super().mousePressEvent(event)
            return

        if self.isSelected() and event.button() == Qt.LeftButton:
            pos = event.pos()
            rot_pos = self.mapFromScene(self._rotation_handle_scene_pos())
            sc_pos = self.mapFromScene(self._scale_handle_scene_pos())

            if (pos - rot_pos).manhattanLength() < HANDLE_SIZE * 2:
                self._dragging_rotate = True
                self._dragging_scale = False
                center = self.mapToScene(self.shape_bounding_rect().center())
                scene_pos = event.scenePos()
                dx = scene_pos.x() - center.x()
                dy = scene_pos.y() - center.y()
                self._rotate_start_angle = math.degrees(math.atan2(dy, dx))
                self._rotate_start_item_angle = self.rotation()
                event.accept()
                return

            elif (pos - sc_pos).manhattanLength() < HANDLE_SIZE * 2:
                self._dragging_scale = True
                self._dragging_rotate = False
                self._scale_start_pos = event.scenePos()
                self._scale_start_scale = self.scale()
                event.accept()
                return

        self._dragging_rotate = False
        self._dragging_scale = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging_rotate:
            center = self.mapToScene(self.shape_bounding_rect().center())
            scene_pos = event.scenePos()
            dx = scene_pos.x() - center.x()
            dy = scene_pos.y() - center.y()
            angle = math.degrees(math.atan2(dy, dx))
            delta = angle - self._rotate_start_angle
            new_angle = self._rotate_start_item_angle + delta

            # Shift: snap to 45 degree increments
            if event.modifiers() & Qt.ShiftModifier:
                new_angle = round(new_angle / 45.0) * 45.0

            self.setRotation(new_angle)
            self.signals.changed.emit(self)
            event.accept()
            return

        if self._dragging_scale:
            if self._scale_start_pos:
                delta = event.scenePos() - self._scale_start_pos
                factor = 1.0 + (delta.x() + delta.y()) / 200.0
                new_scale = max(0.05, self._scale_start_scale * factor)
                self.setScale(new_scale)
                self.signals.changed.emit(self)
            event.accept()
            return

        super().mouseMoveEvent(event)
        self.signals.changed.emit(self)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        self._dragging_rotate = False
        self._dragging_scale = False
        super().mouseReleaseEvent(event)

    def _draw_selection_handles(self, painter: QPainter):
        """Draws transformation bounding box and handles when selected."""
        br = self.shape_bounding_rect()

        if self._is_locked:
            # Locked object: subtle amber dashed box and lock badge in top-right
            pen = QPen(QColor("#FF9800"), 1.2, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(br)

            # Draw a subtle lock badge
            badge_w, badge_h = 16, 16
            bx = br.right() - badge_w - 2
            by = br.top() + 2
            painter.fillRect(QRectF(bx, by, badge_w, badge_h), QColor(255, 152, 0, 210))
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI Emoji", 8, QFont.Bold))
            painter.drawText(QRectF(bx, by, badge_w, badge_h), Qt.AlignCenter, "🔒")
            return

        # Selection dashed box
        pen = QPen(SELECTION_COLOR, 1, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(br)

        # Rotation handle (top center circle)
        rot_pos = self.mapFromScene(self._rotation_handle_scene_pos())
        painter.setPen(QPen(SELECTION_COLOR, 1))
        painter.setBrush(QBrush(Qt.white))
        painter.drawEllipse(rot_pos, HANDLE_SIZE // 2, HANDLE_SIZE // 2)

        # Line connecting bounding box to rotation handle
        top_center = QPointF(br.center().x(), br.top())
        painter.drawLine(top_center, rot_pos)

        # Scale handle (bottom-right rectangle)
        sc_pos = self.mapFromScene(self._scale_handle_scene_pos())
        painter.setBrush(QBrush(HANDLE_COLOR))
        half = HANDLE_SIZE // 2
        painter.drawRect(int(sc_pos.x() - half), int(sc_pos.y() - half), HANDLE_SIZE, HANDLE_SIZE)

    def _update_transform_origin(self):
        """Sets rotation/scaling origin to geometric center of the object."""
        br = self.shape_bounding_rect()
        self.setTransformOriginPoint(br.center())

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.signals.changed.emit(self)
        return super().itemChange(change, value)


class TextItem(BasePlotItem):
    """Text object on canvas rendered as vector contour paths."""

    def __init__(
        self,
        item_id: int,
        text: str = "Text",
        font_family: str = "Arial",
        font_size_mm: float = 12.0,
        bold: bool = False,
        italic: bool = False,
        enable_infill: bool = False,
        infill_pattern: str = "linear",
        infill_spacing_mm: float = 0.5,
        infill_angle: float = 45.0,
    ):
        super().__init__(item_id)
        self._text = text
        self._font_family = font_family
        self._font_size_mm = font_size_mm
        self._bold = bold
        self._italic = italic
        self._enable_infill = enable_infill
        self._infill_pattern = infill_pattern
        self._infill_spacing_mm = infill_spacing_mm
        self._infill_angle = infill_angle
        self._path: Optional[QPainterPath] = None
        self._infill_polylines: List[List[Tuple[float, float]]] = []
        self._rebuild_path()

    def item_type(self) -> int:
        return self.ITEM_TYPE_TEXT

    @property
    def text(self) -> str:
        return self._text

    @property
    def font_family(self) -> str:
        return self._font_family

    @property
    def font_size_mm(self) -> float:
        return self._font_size_mm

    @property
    def bold(self) -> bool:
        return self._bold

    @property
    def is_bold(self) -> bool:
        return self._bold

    @property
    def italic(self) -> bool:
        return self._italic

    @property
    def is_italic(self) -> bool:
        return self._italic

    @property
    def enable_infill(self) -> bool:
        return self._enable_infill

    @property
    def infill_pattern(self) -> str:
        return self._infill_pattern

    @property
    def infill_spacing_mm(self) -> float:
        return self._infill_spacing_mm

    @property
    def infill_angle(self) -> float:
        return self._infill_angle

    def set_text(self, text: str):
        if self._text != text:
            self._text = text
            self._rebuild_path()
            self.update()
            self.signals.changed.emit(self)

    def set_font_family(self, family: str):
        if self._font_family != family:
            self._font_family = family
            self._rebuild_path()
            self.update()
            self.signals.changed.emit(self)

    def set_bold(self, bold: bool):
        if self._bold != bold:
            self._bold = bold
            self._rebuild_path()
            self.update()
            self.signals.changed.emit(self)

    def set_italic(self, italic: bool):
        if self._italic != italic:
            self._italic = italic
            self._rebuild_path()
            self.update()
            self.signals.changed.emit(self)

    def set_font(self, family: str, size_mm: float = 12.0, bold: bool = False, italic: bool = False):
        self._font_family = family
        self._font_size_mm = size_mm
        self._bold = bold
        self._italic = italic
        self._rebuild_path()
        self.update()
        self.signals.changed.emit(self)

    def set_infill(
        self,
        enable_infill: bool,
        infill_pattern: Optional[str] = None,
        infill_spacing_mm: Optional[float] = None,
        infill_angle: Optional[float] = None,
    ):
        changed = False
        if self._enable_infill != enable_infill:
            self._enable_infill = enable_infill
            changed = True
        if infill_pattern is not None and self._infill_pattern != infill_pattern:
            self._infill_pattern = infill_pattern
            changed = True
        if infill_spacing_mm is not None and abs(self._infill_spacing_mm - infill_spacing_mm) > 1e-4:
            self._infill_spacing_mm = infill_spacing_mm
            changed = True
        if infill_angle is not None and abs(self._infill_angle - infill_angle) > 1e-4:
            self._infill_angle = infill_angle
            changed = True

        if changed:
            self._rebuild_infill()
            self.update()
            self.signals.changed.emit(self)

    def _rebuild_path(self):
        font_size_pt = self._font_size_mm * 72.0 / 25.4
        font = QFont(self._font_family)
        font.setPointSizeF(font_size_pt)
        font.setBold(self._bold)
        font.setItalic(self._italic)

        path = QPainterPath()
        path.addText(0, 0, font, self._text if self._text else " ")
        self._path = path
        self._rebuild_infill()
        self.prepareGeometryChange()
        self._update_transform_origin()

    def _rebuild_infill(self):
        if not self._enable_infill or not self._path:
            self._infill_polylines = []
            return
        try:
            from core.text_to_path import generate_text_infill
            self._infill_polylines = generate_text_infill(
                path=self._path,
                pattern=self._infill_pattern,
                spacing_mm=self._infill_spacing_mm,
                angle_deg=self._infill_angle,
            )
        except Exception as e:
            print(f"Text infill generation error: {e}")
            self._infill_polylines = []

    def shape_bounding_rect(self) -> QRectF:
        if self._path:
            return self._path.boundingRect().adjusted(-2, -2, 2, 2)
        return QRectF(-2, -2, 4, 4)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        if not self._path:
            return

        painter.setRenderHint(QPainter.Antialiasing)

        # 1. Draw infill strokes if enabled (Cyan #00ACC1)
        if self._enable_infill and self._infill_polylines:
            pen_infill = QPen(QColor("#00ACC1"), 1.0)
            painter.setPen(pen_infill)
            painter.setBrush(Qt.NoBrush)
            for pl in self._infill_polylines:
                for i in range(len(pl) - 1):
                    x1, y1 = pl[i]
                    x2, y2 = pl[i + 1]
                    painter.drawLine(
                        QPointF(x1 * MM_TO_PX, y1 * MM_TO_PX),
                        QPointF(x2 * MM_TO_PX, y2 * MM_TO_PX),
                    )

        # 2. Draw stroke outline (as pen plotter draws contours)
        pen = QPen(QColor("#1a1a1a"), 1.2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self._path)

        if self.isSelected():
            self._draw_selection_handles(painter)

    def get_polylines_mm(self) -> List[List[Tuple[float, float]]]:
        if not self._path:
            return []
        from core.text_to_path import _painter_path_to_polylines
        contour_pls = _painter_path_to_polylines(self._path, scale=1.0 / MM_TO_PX)
        if self._enable_infill and self._infill_polylines:
            return contour_pls + self._infill_polylines
        return contour_pls


class SvgItem(BasePlotItem):
    """SVG vector object on canvas with multi-color palette infill."""

    def __init__(
        self,
        item_id: int,
        svg_path: str,
        width_mm: float = 80.0,
        enable_infill: bool = False,
        infill_spacing_mm: float = 0.5,
        color_configs: Optional[List[dict]] = None,
    ):
        super().__init__(item_id)
        self._svg_path = svg_path
        self._width_mm = width_mm
        self._enable_infill = enable_infill
        self._infill_spacing_mm = infill_spacing_mm
        self._renderer = QSvgRenderer(svg_path)
        self._polylines: List[List[Tuple[float, float]]] = []
        self._color_configs: List[dict] = color_configs or []
        self._infill_by_color: List[Tuple[str, List[List[Tuple[float, float]]]]] = []
        self._infill_polylines: List[List[Tuple[float, float]]] = []

        self._load_paths()
        self._init_palette()
        self._update_transform_origin()

    def item_type(self) -> int:
        return self.ITEM_TYPE_SVG

    @property
    def svg_path(self):
        return self._svg_path

    @property
    def width_mm(self):
        return self._width_mm

    @property
    def enable_infill(self) -> bool:
        return self._enable_infill

    @property
    def infill_spacing_mm(self) -> float:
        return self._infill_spacing_mm

    @property
    def color_configs(self) -> List[dict]:
        return self._color_configs

    def _load_paths(self):
        try:
            from core.svg_parser import parse_svg
            self._polylines = parse_svg(self._svg_path, target_width_mm=self._width_mm)
        except Exception as e:
            print(f"SVG parse error: {e}")
            self._polylines = []

    def _render_rgba_buffer(self, max_dim: int = 1000) -> Optional[np.ndarray]:
        """Renders the SVG to an offscreen high-res RGBA numpy buffer."""
        default_size = self._renderer.defaultSize()
        w_orig = max(default_size.width(), 1)
        h_orig = max(default_size.height(), 1)
        aspect = h_orig / w_orig

        if aspect >= 1.0:
            render_h = max_dim
            render_w = max(10, int(round(render_h / aspect)))
        else:
            render_w = max_dim
            render_h = max(10, int(round(render_w * aspect)))

        qimg = QImage(render_w, render_h, QImage.Format_ARGB32)
        qimg.fill(0)
        p = QPainter(qimg)
        self._renderer.render(p, QRectF(0, 0, render_w, render_h))
        p.end()

        ptr = qimg.bits()
        ptr.setsize(qimg.byteCount())
        rgba = np.array(ptr, copy=True).reshape(render_h, qimg.bytesPerLine() // 4, 4)[:, :render_w, :]
        b, g, r, a = rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2], rgba[:, :, 3]
        return np.stack([r, g, b, a], axis=-1)

    def _init_palette(self):
        """Extracts dominant colors from SVG render if not already configured."""
        try:
            from core.raster_tracer import extract_color_palette
            rgba = self._render_rgba_buffer(max_dim=800)
            if rgba is None:
                return

            palette = extract_color_palette(rgba, max_colors=8)
            if not self._color_configs:
                self._color_configs = palette
            else:
                existing_map = {c["hex"].lower(): c for c in self._color_configs}
                merged = []
                for p_col in palette:
                    h = p_col["hex"].lower()
                    if h in existing_map:
                        merged.append({**p_col, **existing_map[h]})
                    else:
                        merged.append(p_col)
                self._color_configs = merged or palette

            if self._enable_infill:
                self._rebuild_infill()
        except Exception as e:
            print(f"SVG palette init error: {e}")
            if not self._color_configs:
                self._color_configs = []

    def set_infill_config(
        self,
        enable_infill: bool,
        infill_spacing_mm: Optional[float] = None,
        color_configs: Optional[List[dict]] = None,
    ):
        changed = False
        if self._enable_infill != enable_infill:
            self._enable_infill = enable_infill
            changed = True
        if infill_spacing_mm is not None and abs(self._infill_spacing_mm - infill_spacing_mm) > 1e-4:
            self._infill_spacing_mm = infill_spacing_mm
            changed = True
        if color_configs is not None:
            self._color_configs = color_configs
            changed = True

        if changed:
            self._rebuild_infill()
            self.update()
            self.signals.changed.emit(self)

    def _rebuild_infill(self):
        if not self._enable_infill or not self._color_configs:
            self._infill_by_color = []
            self._infill_polylines = []
            return

        try:
            from core.raster_tracer import generate_palette_infill
            rgba = self._render_rgba_buffer(max_dim=800)
            if rgba is None:
                return

            active_configs = []
            for c in self._color_configs:
                cfg = dict(c)
                if "spacing_mm" not in cfg or cfg["spacing_mm"] <= 0:
                    cfg["spacing_mm"] = self._infill_spacing_mm
                active_configs.append(cfg)

            self._infill_by_color = generate_palette_infill(
                rgba_img=rgba,
                target_width_mm=self._width_mm,
                color_configs=active_configs,
            )
            self._infill_polylines = []
            for _, strokes in self._infill_by_color:
                self._infill_polylines.extend(strokes)
        except Exception as e:
            print(f"SVG infill error: {e}")
            self._infill_by_color = []
            self._infill_polylines = []

    def shape_bounding_rect(self) -> QRectF:
        default_size = self._renderer.defaultSize()
        aspect = default_size.height() / max(default_size.width(), 1)
        w_px = self._width_mm * MM_TO_PX
        h_px = w_px * aspect
        return QRectF(0, 0, w_px, h_px)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        br = self.shape_bounding_rect()
        self._renderer.render(painter, br)

        # 1. Draw vector contours on top (dotted blue)
        pen = QPen(QColor("#1565C0"), 1, Qt.DotLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for pl in self._polylines:
            if len(pl) < 2:
                continue
            for i in range(len(pl) - 1):
                x1, y1 = pl[i]
                x2, y2 = pl[i + 1]
                painter.drawLine(
                    QPointF(x1 * MM_TO_PX, y1 * MM_TO_PX),
                    QPointF(x2 * MM_TO_PX, y2 * MM_TO_PX)
                )

        # 2. Draw infill strokes in preview color (colored toolpaths)
        if self._enable_infill and self._infill_by_color:
            w_px = br.width()
            scale_x = w_px / max(self._width_mm, 1.0)
            for hex_col, strokes in self._infill_by_color:
                col = QColor(hex_col)
                if col.lightness() > 210:
                    col = col.darker(150)
                pen_inf = QPen(col, 1.1)
                painter.setPen(pen_inf)
                painter.setBrush(Qt.NoBrush)
                for pl in strokes:
                    for i in range(len(pl) - 1):
                        x1, y1 = pl[i]
                        x2, y2 = pl[i + 1]
                        painter.drawLine(
                            QPointF(x1 * scale_x, y1 * scale_x),
                            QPointF(x2 * scale_x, y2 * scale_x)
                        )

        if self.isSelected():
            self._draw_selection_handles(painter)

    def get_polylines_mm(self) -> List[List[Tuple[float, float]]]:
        if self._enable_infill and self._infill_polylines:
            return self._polylines + self._infill_polylines
        return self._polylines


class RasterItem(BasePlotItem):
    """Raster image object with real-time vectorization and infill preview."""

    def __init__(
        self,
        item_id: int,
        image_path: str,
        width_mm: float = 80.0,
        method: str = "contour",
        threshold1: float = 50,
        threshold2: float = 150,
        contour_thresh: int = 128,
        auto_thresh: bool = True,
        invert: bool = False,
        smooth_level: int = 2,
        enable_infill: bool = False,
        infill_pattern: str = "linear",
        infill_spacing_mm: float = 0.5,
        infill_angle: float = 45.0,
        infill_min_area_mm2: float = 2.0,
        pen_width_mm: float = 0.5,
        min_path_len_mm: float = 0.5,
        merge_close_lines: bool = True,
        infill_adaptive_range: int = 128,
    ):
        super().__init__(item_id)
        self._image_path = image_path
        self._width_mm = width_mm

        # Algorithm parameters
        self._method = method
        self._threshold1 = threshold1
        self._threshold2 = threshold2
        self._contour_thresh = contour_thresh
        self._auto_thresh = auto_thresh
        self._invert = invert
        self._smooth_level = smooth_level
        self._pen_width_mm = pen_width_mm
        self._min_path_len_mm = min_path_len_mm
        self._merge_close_lines = merge_close_lines

        # Infill parameters
        self._enable_infill = enable_infill
        self._infill_pattern = infill_pattern
        self._infill_spacing_mm = infill_spacing_mm
        self._infill_angle = infill_angle
        self._infill_min_area_mm2 = infill_min_area_mm2
        self._infill_adaptive_range = infill_adaptive_range

        self._pixmap = QPixmap(image_path)
        self._contour_polylines: List[Polyline] = []
        self._infill_polylines: List[Polyline] = []
        self._show_preview = False

        self._trace()
        self._update_transform_origin()

    def item_type(self) -> int:
        return self.ITEM_TYPE_RASTER

    @property
    def image_path(self) -> str:
        return self._image_path

    @property
    def width_mm(self) -> float:
        return self._width_mm

    @property
    def method(self) -> str:
        return self._method

    @property
    def threshold1(self) -> float:
        return self._threshold1

    @property
    def threshold2(self) -> float:
        return self._threshold2

    @property
    def contour_thresh(self) -> int:
        return self._contour_thresh

    @property
    def auto_thresh(self) -> bool:
        return self._auto_thresh

    @property
    def invert(self) -> bool:
        return self._invert

    @property
    def smooth_level(self) -> int:
        return self._smooth_level

    @property
    def enable_infill(self) -> bool:
        return self._enable_infill

    @property
    def infill_pattern(self) -> str:
        return self._infill_pattern

    @property
    def infill_spacing_mm(self) -> float:
        return self._infill_spacing_mm

    @property
    def infill_angle(self) -> float:
        return self._infill_angle

    @property
    def infill_min_area_mm2(self) -> float:
        return self._infill_min_area_mm2

    @property
    def infill_adaptive_range(self) -> int:
        return self._infill_adaptive_range

    @property
    def pen_width_mm(self) -> float:
        return self._pen_width_mm

    @property
    def min_path_len_mm(self) -> float:
        return self._min_path_len_mm

    @property
    def merge_close_lines(self) -> bool:
        return self._merge_close_lines

    @property
    def show_preview(self) -> bool:
        return self._show_preview

    def set_show_preview(self, show: bool):
        self._show_preview = show
        self.update()

    def retrace(
        self,
        method: Optional[str] = None,
        threshold1: Optional[float] = None,
        threshold2: Optional[float] = None,
        contour_thresh: Optional[int] = None,
        auto_thresh: Optional[bool] = None,
        invert: Optional[bool] = None,
        smooth_level: Optional[int] = None,
        enable_infill: Optional[bool] = None,
        infill_pattern: Optional[str] = None,
        infill_spacing_mm: Optional[float] = None,
        infill_angle: Optional[float] = None,
        infill_min_area_mm2: Optional[float] = None,
        pen_width_mm: Optional[float] = None,
        min_path_len_mm: Optional[float] = None,
        merge_close_lines: Optional[bool] = None,
        infill_adaptive_range: Optional[int] = None,
    ):
        """Re-runs vectorization with updated algorithm and infill parameters."""
        if method is not None:
            self._method = method
        if threshold1 is not None:
            self._threshold1 = threshold1
        if threshold2 is not None:
            self._threshold2 = threshold2
        if contour_thresh is not None:
            self._contour_thresh = contour_thresh
        if auto_thresh is not None:
            self._auto_thresh = auto_thresh
        if invert is not None:
            self._invert = invert
        if smooth_level is not None:
            self._smooth_level = smooth_level
        if enable_infill is not None:
            self._enable_infill = enable_infill
        if infill_pattern is not None:
            self._infill_pattern = infill_pattern
        if infill_spacing_mm is not None:
            self._infill_spacing_mm = infill_spacing_mm
        if infill_angle is not None:
            self._infill_angle = infill_angle
        if infill_min_area_mm2 is not None:
            self._infill_min_area_mm2 = infill_min_area_mm2
        if pen_width_mm is not None:
            self._pen_width_mm = pen_width_mm
        if min_path_len_mm is not None:
            self._min_path_len_mm = min_path_len_mm
        if merge_close_lines is not None:
            self._merge_close_lines = merge_close_lines
        if infill_adaptive_range is not None:
            self._infill_adaptive_range = infill_adaptive_range

        self._trace()
        self.update()
        self.signals.changed.emit(self)

    def _trace(self):
        try:
            from core.raster_tracer import trace_raster_full
            self._contour_polylines, self._infill_polylines = trace_raster_full(
                image_path=self._image_path,
                target_width_mm=self._width_mm,
                method=self._method,
                threshold1=self._threshold1,
                threshold2=self._threshold2,
                contour_thresh=self._contour_thresh,
                auto_thresh=self._auto_thresh,
                invert=self._invert,
                smooth_level=self._smooth_level,
                enable_infill=self._enable_infill,
                infill_pattern=self._infill_pattern,
                infill_spacing_mm=self._infill_spacing_mm,
                infill_angle=self._infill_angle,
                infill_min_area_mm2=self._infill_min_area_mm2,
                pen_width_mm=self._pen_width_mm,
                min_path_len_mm=self._min_path_len_mm,
                merge_close_lines=self._merge_close_lines,
                infill_adaptive_range=self._infill_adaptive_range,
            )
        except Exception as e:
            print(f"Trace error: {e}")
            self._contour_polylines = []
            self._infill_polylines = []

    def shape_bounding_rect(self) -> QRectF:
        if not self._pixmap.isNull():
            aspect = self._pixmap.height() / max(self._pixmap.width(), 1)
            w_px = self._width_mm * MM_TO_PX
            h_px = w_px * aspect
            return QRectF(0, 0, w_px, h_px)
        return QRectF(0, 0, 100, 100)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        br = self.shape_bounding_rect()

        if not self._pixmap.isNull():
            painter.setOpacity(0.35 if self._show_preview else 0.9)
            painter.drawPixmap(br.toRect(), self._pixmap)
            painter.setOpacity(1.0)

        # Draw vectorized preview strokes
        if self._show_preview:
            w_px = br.width()
            scale_x = w_px / max(self._width_mm, 1.0)

            # 1. Infill strokes (Cyan #00ACC1)
            if self._infill_polylines:
                pen_infill = QPen(QColor("#00ACC1"), 1)
                painter.setPen(pen_infill)
                painter.setBrush(Qt.NoBrush)
                for pl in self._infill_polylines:
                    for i in range(len(pl) - 1):
                        x1, y1 = pl[i]
                        x2, y2 = pl[i + 1]
                        painter.drawLine(
                            QPointF(x1 * scale_x, y1 * scale_x),
                            QPointF(x2 * scale_x, y2 * scale_x),
                        )

            # 2. Contour boundary strokes (Red #E53935)
            if self._contour_polylines:
                pen_contour = QPen(QColor("#E53935"), 1.2)
                painter.setPen(pen_contour)
                painter.setBrush(Qt.NoBrush)
                for pl in self._contour_polylines:
                    for i in range(len(pl) - 1):
                        x1, y1 = pl[i]
                        x2, y2 = pl[i + 1]
                        painter.drawLine(
                            QPointF(x1 * scale_x, y1 * scale_x),
                            QPointF(x2 * scale_x, y2 * scale_x),
                        )

        if self.isSelected():
            self._draw_selection_handles(painter)

    def get_polylines_mm(self) -> List[List[Tuple[float, float]]]:
        return self._contour_polylines + self._infill_polylines
