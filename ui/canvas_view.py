"""
canvas_view.py — QGraphicsView workspace with zoom, pan, and millimeter rulers.

Displays two primary zones:
  1. Full printer hardware travel area (printer_max_w × printer_max_h) — semi-transparent orange border
  2. Physical accessible pen drawing canvas (print_area_w × print_area_h) — white paper area
"""
from __future__ import annotations
from typing import List, Tuple, Optional, TYPE_CHECKING

from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsLineItem,
    QGraphicsTextItem,
)
from PyQt5.QtGui import (
    QPainter, QPen, QBrush, QColor, QWheelEvent, QTransform, QFont, QCursor,
)
from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal

from ui.canvas_items import BasePlotItem, MM_TO_PX, PREVIEW_COLOR, TRAVEL_COLOR
from core.i18n import tr, register_listener
from core.theme_manager import get_theme, register_theme_listener

if TYPE_CHECKING:
    from core.canvas_model import PrinterSettings

GRID_MM = 10.0
GRID_COLOR = QColor("#e0e0e0")
GRID_MAJOR_COLOR = QColor("#bdbdbd")

# Zone colors
PAPER_COLOR = QColor("#ffffff")
DEAD_ZONE_COLOR = QColor(255, 152, 0, 60)
PRINTER_AREA_BORDER_COLOR = QColor(255, 152, 0, 180)
CANVAS_BORDER_COLOR = QColor("#1565C0")
BG_COLOR = QColor("#f0f0f0")


class PaperGridItem(QGraphicsRectItem):
    """
    White paper drawing area with high-precision dynamic millimeter grid.

    At normal/fit zoom: divides canvas by centimeters (10 mm) and 5 cm major marks.
    When zoomed in: automatically reveals fine 1 mm subdivisions.
    """

    def __init__(
        self,
        x_px: float,
        y_px: float,
        w_px: float,
        h_px: float,
        show_grid: bool = True,
        parent=None,
    ):
        super().__init__(x_px, y_px, w_px, h_px, parent)
        self.show_grid: bool = show_grid
        self.setZValue(-100)

    def paint(self, painter: QPainter, option, widget=None):
        rect = self.rect()
        painter.fillRect(rect, PAPER_COLOR)

        if self.show_grid:
            scale = painter.transform().m11()
            mm_px = MM_TO_PX
            mm_screen_px = mm_px * scale

            # Clip grid iterations to visible exposed rectangle for performance
            exp = option.exposedRect.intersected(rect) if option else rect
            if exp.isEmpty():
                exp = rect

            x_min_mm = exp.left() / mm_px
            x_max_mm = exp.right() / mm_px
            y_min_mm = exp.top() / mm_px
            y_max_mm = exp.bottom() / mm_px

            painter.setRenderHint(QPainter.Antialiasing, False)

            # 1. Fine 1 mm grid lines (revealed when mm_screen_px >= 6.0)
            if mm_screen_px >= 6.0:
                pen_1mm = QPen(QColor("#e2e8f0"), 1)
                pen_1mm.setCosmetic(True)
                painter.setPen(pen_1mm)

                start_x = int(x_min_mm)
                end_x = int(x_max_mm) + 1
                for cur_x in range(start_x, end_x + 1):
                    if cur_x % 10 != 0:
                        px = cur_x * mm_px
                        if rect.left() <= px <= rect.right():
                            painter.drawLine(QPointF(px, rect.top()), QPointF(px, rect.bottom()))

                start_y = int(y_min_mm)
                end_y = int(y_max_mm) + 1
                for cur_y in range(start_y, end_y + 1):
                    if cur_y % 10 != 0:
                        py = cur_y * mm_px
                        if rect.top() <= py <= rect.bottom():
                            painter.drawLine(QPointF(rect.left(), py), QPointF(rect.right(), py))

            # 2. Centimeter (10 mm) and 50 mm (5 cm) grid lines
            pen_10mm = QPen(QColor("#cbd5e1"), 1)
            pen_10mm.setCosmetic(True)
            pen_50mm = QPen(QColor("#94a3b8"), 1.5)
            pen_50mm.setCosmetic(True)

            start_cm_x = (int(x_min_mm) // 10) * 10
            end_cm_x = (int(x_max_mm) // 10 + 1) * 10
            for cur_x in range(start_cm_x, end_cm_x + 1, 10):
                px = cur_x * mm_px
                if rect.left() <= px <= rect.right():
                    painter.setPen(pen_50mm if cur_x % 50 == 0 else pen_10mm)
                    painter.drawLine(QPointF(px, rect.top()), QPointF(px, rect.bottom()))

            start_cm_y = (int(y_min_mm) // 10) * 10
            end_cm_y = (int(y_max_mm) // 10 + 1) * 10
            for cur_y in range(start_cm_y, end_cm_y + 1, 10):
                py = cur_y * mm_px
                if rect.top() <= py <= rect.bottom():
                    painter.setPen(pen_50mm if cur_y % 50 == 0 else pen_10mm)
                    painter.drawLine(QPointF(rect.left(), py), QPointF(rect.right(), py))

        # Paper outer border (drawn on top of grid lines)
        painter.setPen(self.pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)


class PlotterScene(QGraphicsScene):
    """
    QGraphicsScene managing the plotter workspace layout and zone visualization.
    """

    item_selection_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Hardware dimensions (mm)
        self._printer_max_w: float = 220.0
        self._printer_max_h: float = 220.0
        self._offset_x: float = 39.5
        self._offset_y: float = 0.0

        # Grid visibility
        self._show_grid: bool = True

        # Scene display elements
        self._paper_rect: Optional[PaperGridItem] = None
        self._printer_border: Optional[QGraphicsRectItem] = None
        self._size_lbl: Optional[QGraphicsTextItem] = None
        self._prt_lbl: Optional[QGraphicsTextItem] = None
        self._dead_zone_items: List[QGraphicsItem] = []

        # G-code preview paths
        self._preview_lines: List[QGraphicsLineItem] = []
        self._show_gcode_preview: bool = False
        self._gcode_polylines: List[List[Tuple[float, float]]] = []

        self._setup_zones()
        self.selectionChanged.connect(self._on_selection_changed)
        register_listener(self.retranslate_ui)

    def set_show_grid(self, show: bool):
        """Toggles millimeter grid display across the canvas work area."""
        self._show_grid = show
        if self._paper_rect is not None:
            self._paper_rect.show_grid = show
        self.update()

    def set_printer_config(
        self,
        printer_max_w: float,
        printer_max_h: float,
        offset_x: float,
        offset_y: float,
    ):
        """Updates zone visualization based on new printer settings."""
        self._printer_max_w = printer_max_w
        self._printer_max_h = printer_max_h
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._setup_zones()

    def set_print_area(self, width_mm: float, height_mm: float):
        """Legacy helper for setting available canvas dimensions."""
        self.set_printer_config(
            width_mm + abs(self._offset_x),
            height_mm + abs(self._offset_y),
            self._offset_x,
            self._offset_y,
        )

    @property
    def canvas_w_mm(self) -> float:
        return max(1.0, self._printer_max_w - abs(self._offset_x))

    @property
    def canvas_h_mm(self) -> float:
        return max(1.0, self._printer_max_h - abs(self._offset_y))

    @property
    def paper_x_mm(self) -> float:
        return abs(self._offset_x) if self._offset_x > 0 else 0.0

    @property
    def paper_y_mm(self) -> float:
        return abs(self._offset_y) if self._offset_y > 0 else 0.0

    def set_gcode_preview(
        self,
        polylines: List[List[Tuple[float, float]]],
        show: bool = True,
    ):
        self._gcode_polylines = polylines
        self._show_gcode_preview = show
        self._update_preview_lines()

    def add_plot_item(
        self,
        item: BasePlotItem,
        center: bool = True,
        pos_mm: Optional[Tuple[float, float]] = None,
    ):
        self.addItem(item)
        br = item.shape_bounding_rect()
        if pos_mm is not None:
            x_px = pos_mm[0] * MM_TO_PX - br.width() / 2.0
            y_px = pos_mm[1] * MM_TO_PX - br.height() / 2.0
            item.setPos(x_px, y_px)
        elif center:
            paper_x_px = self.paper_x_mm * MM_TO_PX
            paper_y_px = self.paper_y_mm * MM_TO_PX
            paper_w_px = self.canvas_w_mm * MM_TO_PX
            paper_h_px = self.canvas_h_mm * MM_TO_PX
            cx = paper_x_px + (paper_w_px - br.width()) / 2
            cy = paper_y_px + (paper_h_px - br.height()) / 2
            item.setPos(max(paper_x_px, cx), max(paper_y_px, cy))

    def clear_plot_items(self):
        """Removes all user plot items without affecting background grid and zones."""
        for item in self.get_all_plot_items():
            self.removeItem(item)

    def get_all_plot_items(self) -> List[BasePlotItem]:
        return [item for item in self.items() if isinstance(item, BasePlotItem)]

    def get_all_polylines_mm(self) -> List[List[Tuple[float, float]]]:
        all_polylines = []
        for item in self.get_all_plot_items():
            if getattr(item, "is_hidden", False):
                continue
            all_polylines.extend(item.get_transformed_polylines_mm())
        return all_polylines

    def retranslate_ui(self):
        """Updates text labels on canvas when language changes."""
        self._setup_zones()

    def _setup_zones(self):
        """Builds or rebuilds background zone boundaries and labels."""
        for item in self._dead_zone_items:
            if item.scene() == self:
                self.removeItem(item)
        self._dead_zone_items.clear()

        for attr in ("_paper_rect", "_printer_border", "_size_lbl", "_prt_lbl"):
            item = getattr(self, attr, None)
            if item and item.scene() == self:
                self.removeItem(item)
            setattr(self, attr, None)

        paper_x = self.paper_x_mm
        paper_y = self.paper_y_mm
        canvas_w = self.canvas_w_mm
        canvas_h = self.canvas_h_mm

        printer_w_px = self._printer_max_w * MM_TO_PX
        printer_h_px = self._printer_max_h * MM_TO_PX
        paper_x_px = paper_x * MM_TO_PX
        paper_y_px = paper_y * MM_TO_PX
        paper_w_px = canvas_w * MM_TO_PX
        paper_h_px = canvas_h * MM_TO_PX

        margin = 25 * MM_TO_PX
        self.setSceneRect(
            -margin,
            -margin,
            printer_w_px + 2 * margin,
            printer_h_px + 2 * margin,
        )

        # 1. Total printer physical travel boundary (fixed at 0, 0 to max_w, max_h)
        printer_border = QGraphicsRectItem(0, 0, printer_w_px, printer_h_px)
        printer_border.setPen(QPen(PRINTER_AREA_BORDER_COLOR, 1.5, Qt.DashLine))
        printer_border.setBrush(QBrush(Qt.NoBrush))
        printer_border.setZValue(-200)
        self.addItem(printer_border)
        self._printer_border = printer_border

        # 2. Dead zones
        # X dead zone:
        if abs(self._offset_x) > 0.5:
            if self._offset_x > 0:
                # Pen mounted to right of nozzle -> dead zone on LEFT [0, offset_x]
                dz_x_rect = QRectF(0, 0, paper_x_px, printer_h_px)
                lbl_pos = QPointF(2, 4)
                lbl_text = f"← {tr('canvas_dead_zone')}"
            else:
                # Pen mounted to left of nozzle -> dead zone on RIGHT [printer_w - |ox|, printer_w]
                dz_x_rect = QRectF(paper_x_px + paper_w_px, 0, abs(self._offset_x) * MM_TO_PX, printer_h_px)
                lbl_pos = QPointF(paper_x_px + paper_w_px + 4, 4)
                lbl_text = f"{tr('canvas_dead_zone')} →"

            dz_x_item = QGraphicsRectItem(dz_x_rect)
            dz_x_item.setPen(QPen(Qt.NoPen))
            dz_x_item.setBrush(QBrush(DEAD_ZONE_COLOR))
            dz_x_item.setZValue(-150)
            self.addItem(dz_x_item)
            self._dead_zone_items.append(dz_x_item)

            lbl_item = QGraphicsTextItem(lbl_text)
            lbl_item.setDefaultTextColor(QColor(180, 80, 0))
            lbl_item.setFont(QFont("Segoe UI", 8))
            lbl_item.setPos(lbl_pos)
            lbl_item.setZValue(-140)
            self.addItem(lbl_item)
            self._dead_zone_items.append(lbl_item)

        # Y dead zone:
        if abs(self._offset_y) > 0.5:
            if self._offset_y > 0:
                # Dead zone on TOP [0, offset_y]
                dz_y_rect = QRectF(0, 0, printer_w_px, paper_y_px)
                lbl_pos_y = QPointF(4, 2)
                lbl_text_y = f"↑ {tr('canvas_dead_zone')}"
            else:
                # Dead zone on BOTTOM [printer_h - |oy|, printer_h]
                dz_y_rect = QRectF(0, paper_y_px + paper_h_px, printer_w_px, abs(self._offset_y) * MM_TO_PX)
                lbl_pos_y = QPointF(4, paper_y_px + paper_h_px + 2)
                lbl_text_y = f"{tr('canvas_dead_zone')} ↓"

            dz_y_item = QGraphicsRectItem(dz_y_rect)
            dz_y_item.setPen(QPen(Qt.NoPen))
            dz_y_item.setBrush(QBrush(DEAD_ZONE_COLOR))
            dz_y_item.setZValue(-150)
            self.addItem(dz_y_item)
            self._dead_zone_items.append(dz_y_item)

            lbl_y_item = QGraphicsTextItem(lbl_text_y)
            lbl_y_item.setDefaultTextColor(QColor(180, 80, 0))
            lbl_y_item.setFont(QFont("Segoe UI", 8))
            lbl_y_item.setPos(lbl_pos_y)
            lbl_y_item.setZValue(-140)
            self.addItem(lbl_y_item)
            self._dead_zone_items.append(lbl_y_item)

        # 3. White paper area (accessible drawing area) with dynamic millimeter grid
        paper = PaperGridItem(paper_x_px, paper_y_px, paper_w_px, paper_h_px, show_grid=self._show_grid)
        paper.setPen(QPen(CANVAS_BORDER_COLOR, 2))
        self.addItem(paper)
        self._paper_rect = paper

        unit = tr("unit_mm")

        # 4. Work area dimension badge
        size_lbl = QGraphicsTextItem(f"{canvas_w:.1f} × {canvas_h:.1f} {unit} ({tr('canvas_work_area')})")
        size_lbl.setDefaultTextColor(QColor("#1565C0"))
        size_lbl.setFont(QFont("Segoe UI", 8, QFont.Bold))
        size_lbl.setPos(paper_x_px + 4, paper_y_px + paper_h_px + 3)
        size_lbl.setZValue(-90)
        self.addItem(size_lbl)
        self._size_lbl = size_lbl

        # 5. Printer dimension badge
        prt_lbl = QGraphicsTextItem(
            f"{tr('canvas_printer')}: {self._printer_max_w:.0f} × {self._printer_max_h:.0f} {unit}  |  "
            f"{tr('canvas_offset_x')}: {self._offset_x:.1f} {unit}  |  "
            f"{tr('canvas_offset_y')}: {self._offset_y:.1f} {unit}"
        )
        prt_lbl.setDefaultTextColor(QColor(180, 80, 0))
        prt_lbl.setFont(QFont("Segoe UI", 8))
        prt_lbl.setPos(0, -18)
        prt_lbl.setZValue(-90)
        self.addItem(prt_lbl)
        self._prt_lbl = prt_lbl

    def _update_preview_lines(self):
        for line in self._preview_lines:
            if line.scene() == self:
                self.removeItem(line)
        self._preview_lines.clear()

        if not self._show_gcode_preview:
            return

        draw_pen = QPen(PREVIEW_COLOR, 1)
        draw_pen.setCosmetic(True)

        for pl in self._gcode_polylines:
            for i in range(len(pl) - 1):
                x1, y1 = pl[i]
                x2, y2 = pl[i + 1]
                line = QGraphicsLineItem(
                    x1 * MM_TO_PX, y1 * MM_TO_PX,
                    x2 * MM_TO_PX, y2 * MM_TO_PX,
                )
                line.setPen(draw_pen)
                line.setZValue(100)
                self.addItem(line)
                self._preview_lines.append(line)

        travel_pen = QPen(TRAVEL_COLOR, 1, Qt.DotLine)
        travel_pen.setCosmetic(True)
        for i in range(len(self._gcode_polylines) - 1):
            if self._gcode_polylines[i] and self._gcode_polylines[i + 1]:
                end = self._gcode_polylines[i][-1]
                start = self._gcode_polylines[i + 1][0]
                line = QGraphicsLineItem(
                    end[0] * MM_TO_PX, end[1] * MM_TO_PX,
                    start[0] * MM_TO_PX, start[1] * MM_TO_PX,
                )
                line.setPen(travel_pen)
                line.setZValue(99)
                self.addItem(line)
                self._preview_lines.append(line)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, BG_COLOR)
        if self._show_grid:
            self._draw_grid(painter, rect)

    def _draw_grid(self, painter: QPainter, rect: QRectF):
        grid_px = GRID_MM * MM_TO_PX
        major_every = 5

        left = int(rect.left() / grid_px) * grid_px
        top = int(rect.top() / grid_px) * grid_px

        painter.setRenderHint(QPainter.Antialiasing, False)

        x = left
        col = int(left / grid_px)
        while x < rect.right():
            pen = QPen(GRID_MAJOR_COLOR if col % major_every == 0 else GRID_COLOR, 0.5)
            painter.setPen(pen)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += grid_px
            col += 1

        y = top
        row = int(top / grid_px)
        while y < rect.bottom():
            pen = QPen(GRID_MAJOR_COLOR if row % major_every == 0 else GRID_COLOR, 0.5)
            painter.setPen(pen)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += grid_px
            row += 1

    def _on_selection_changed(self):
        selected = self.selectedItems()
        if selected and isinstance(selected[0], BasePlotItem):
            self.item_selection_changed.emit(selected[0])
        else:
            self.item_selection_changed.emit(None)


class CanvasView(QGraphicsView):
    """Interactive viewport with smooth zoom, pan, millimeter rulers, and tool modes."""

    mouse_moved_mm = pyqtSignal(float, float)
    text_placement_requested = pyqtSignal(float, float)
    file_dropped = pyqtSignal(str, float, float)

    def __init__(self, scene: PlotterScene, parent=None):
        super().__init__(scene, parent)
        self._scene = scene
        self._zoom_factor = 1.0
        self._panning = False
        self._pan_start = QPointF()
        self._tool_mode = "select"  # "select" or "text"

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        self.fit_to_view()
        register_listener(self.retranslate_ui)
        register_theme_listener(self._on_theme_changed)
        self._on_theme_changed(get_theme())

    def _on_theme_changed(self, theme: str):
        """Updates canvas background and forces ruler repaint when theme changes."""
        if theme == "light":
            self.setBackgroundBrush(QBrush(QColor("#dcdce2")))
        else:
            self.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self.viewport().update()

    def set_tool_mode(self, mode: str):
        """Sets tool mode: 'select' (default) or 'text'."""
        self._tool_mode = mode
        if mode == "text":
            self.setCursor(QCursor(Qt.IBeamCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))

    def get_tool_mode(self) -> str:
        return self._tool_mode

    def set_show_grid(self, show: bool):
        """Toggles millimeter grid display on the canvas."""
        self._scene.set_show_grid(show)

    def fit_to_view(self):
        """Scales viewport so that workspace is comfortably visible."""
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_factor = self.transform().m11()

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        self._zoom_factor = max(0.05, min(50.0, self._zoom_factor * factor))
        self.setTransform(QTransform().scale(self._zoom_factor, self._zoom_factor))

    def mousePressEvent(self, event):
        if self._tool_mode == "text" and event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            x_mm = scene_pos.x() / MM_TO_PX
            y_mm = scene_pos.y() / MM_TO_PX
            self.text_placement_requested.emit(x_mm, y_mm)
            self.set_tool_mode("select")
            event.accept()
            return

        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        scene_pos = self.mapToScene(event.pos())
        x_mm = scene_pos.x() / MM_TO_PX
        y_mm = scene_pos.y() / MM_TO_PX
        self.mouse_moved_mm.emit(x_mm, y_mm)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            if self._tool_mode == "text":
                self.setCursor(Qt.IBeamCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            valid_exts = (".svg", ".png", ".jpg", ".jpeg", ".bmp", ".ppen", ".json", ".ppj", ".gcode", ".nc")
            if any(u.toLocalFile().lower().endswith(valid_exts) for u in urls if u.isLocalFile()):
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            valid_exts = (".svg", ".png", ".jpg", ".jpeg", ".bmp", ".ppen", ".json", ".ppj", ".gcode", ".nc")
            if any(u.toLocalFile().lower().endswith(valid_exts) for u in urls if u.isLocalFile()):
                event.acceptProposedAction()
                return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            scene_pos = self.mapToScene(event.pos())
            x_mm = scene_pos.x() / MM_TO_PX
            y_mm = scene_pos.y() / MM_TO_PX
            urls = event.mimeData().urls()
            valid_exts = (".svg", ".png", ".jpg", ".jpeg", ".bmp", ".ppen", ".json", ".ppj", ".gcode", ".nc")
            dropped = False
            for u in urls:
                if u.isLocalFile():
                    path = u.toLocalFile()
                    if path.lower().endswith(valid_exts):
                        self.file_dropped.emit(path, x_mm, y_mm)
                        dropped = True
            if dropped:
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def retranslate_ui(self):
        """Forces viewport repaint to refresh ruler unit text."""
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Draws millimeter rulers fixed to viewport edges."""
        try:
            self._draw_rulers(painter)
        except Exception:
            pass

    def _draw_rulers(self, painter: QPainter):
        # Increased ruler size and fonts for clear readability
        RULER_SIZE = 28
        is_light = (get_theme() == "light")
        if is_light:
            RULER_BG = QColor(245, 245, 247, 245)
            RULER_TEXT = QColor("#1d1d1f")
            RULER_TICK = QColor("#8e8e93")
            RULER_MAJOR_TICK = QColor("#1d1d1f")
        else:
            RULER_BG = QColor(35, 35, 35, 235)
            RULER_TEXT = QColor("#ffffff")
            RULER_TICK = QColor("#aaaaaa")
            RULER_MAJOR_TICK = QColor("#ffffff")

        vp = self.viewport()
        vp_w, vp_h = vp.width(), vp.height()

        zoom = self.transform().m11()
        mm_to_vp = zoom * MM_TO_PX

        step_mm = 100
        for candidate in [2, 5, 10, 20, 50, 100]:
            if candidate * mm_to_vp >= 45:
                step_mm = candidate
                break
        minor_step_mm = max(1, step_mm // 2)

        painter.save()
        try:
            painter.resetTransform()

            # ── Horizontal Ruler (Top) ─────────────────────────
            painter.fillRect(RULER_SIZE, 0, vp_w - RULER_SIZE, RULER_SIZE, RULER_BG)

            tl = self.mapToScene(RULER_SIZE, RULER_SIZE)
            pt_tr = self.mapToScene(vp_w, RULER_SIZE)
            x_mm_start = tl.x() / MM_TO_PX
            x_mm_end = pt_tr.x() / MM_TO_PX
            x_mm = int(x_mm_start / minor_step_mm) * minor_step_mm
            while x_mm <= x_mm_end + minor_step_mm:
                vp_x = int(self.mapFromScene(QPointF(x_mm * MM_TO_PX, 0)).x())
                is_major = (int(round(x_mm)) % step_mm) == 0
                tick_h = 9 if is_major else 5
                painter.setPen(QPen(RULER_MAJOR_TICK if is_major else RULER_TICK, 1))
                painter.drawLine(vp_x, RULER_SIZE - tick_h, vp_x, RULER_SIZE)
                if is_major and vp_x > RULER_SIZE:
                    painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                    painter.setPen(RULER_TEXT)
                    painter.drawText(vp_x + 3, 2, 45, RULER_SIZE - 9,
                                     Qt.AlignLeft | Qt.AlignVCenter, str(int(round(x_mm))))
                x_mm += minor_step_mm

            # ── Vertical Ruler (Left) ──────────────────────────
            painter.fillRect(0, RULER_SIZE, RULER_SIZE, vp_h - RULER_SIZE, RULER_BG)

            tl2 = self.mapToScene(0, RULER_SIZE)
            bl = self.mapToScene(0, vp_h)
            y_mm_start = tl2.y() / MM_TO_PX
            y_mm_end = bl.y() / MM_TO_PX
            y_mm = int(y_mm_start / minor_step_mm) * minor_step_mm
            while y_mm <= y_mm_end + minor_step_mm:
                vp_y = int(self.mapFromScene(QPointF(0, y_mm * MM_TO_PX)).y())
                is_major = (int(round(y_mm)) % step_mm) == 0
                tick_w = 9 if is_major else 5
                painter.setPen(QPen(RULER_MAJOR_TICK if is_major else RULER_TICK, 1))
                painter.drawLine(RULER_SIZE - tick_w, vp_y, RULER_SIZE, vp_y)
                if is_major and vp_y > RULER_SIZE + 15:
                    painter.save()
                    try:
                        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                        painter.setPen(RULER_TEXT)
                        painter.translate(3, vp_y - 2)
                        painter.rotate(-90)
                        painter.drawText(0, 0, 45, RULER_SIZE - 10,
                                         Qt.AlignLeft | Qt.AlignVCenter, str(int(round(y_mm))))
                    finally:
                        painter.restore()
                y_mm += minor_step_mm

            # ── Corner Unit Box ─────────────────────────────────
            painter.fillRect(0, 0, RULER_SIZE, RULER_SIZE, RULER_BG)
            painter.setPen(RULER_TICK)
            painter.drawLine(RULER_SIZE, 0, RULER_SIZE, RULER_SIZE)
            painter.drawLine(0, RULER_SIZE, RULER_SIZE, RULER_SIZE)
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(RULER_TEXT)
            painter.drawText(0, 0, RULER_SIZE, RULER_SIZE, Qt.AlignCenter, tr("unit_mm"))
        finally:
            painter.restore()
