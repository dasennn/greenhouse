# src/ui/drawing_view.py
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene,
    QGraphicsSimpleTextItem, QInputDialog,
    QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsPathItem, QGraphicsBlurEffect, QGraphicsTextItem
)
from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor, QCursor, QBrush
from PySide6.QtCore import Qt, QPointF, QRectF

class DrawingView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        # ─── Scene & view setup ─────────────────────────────
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000, self)
        self.setScene(self.scene)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setDragMode(QGraphicsView.NoDrag)

        # ─── Perimeter state & history ────────────────────────
        self.points        = []
        self.free_mode     = False
        self.scale_factor  = 100     # px per meter
        self.grid_meters   = 0.1     # default 0.1 m
        self.grid_size     = self.grid_meters * self.scale_factor
        self.perim_history = []
        self.perim_future  = []

        # ─── Guide state & history ────────────────────────────
        self.guide_enabled = False
        self._guide_start  = None
        self.guides        = []      # list of (start_pt, end_pt)
        self.guide_items   = []
        self.guide_labels  = []
        self.guide_history = [[]]    # seed with empty state
        self.guide_future  = []

        # ─── Perimeter path & markers ──────────────────────────
        pen = QPen(QColor("green"), 2)
        self.path_item = QGraphicsPathItem()
        self.path_item.setPen(pen)
        self.scene.addItem(self.path_item)
        self.length_items = []
        self.point_items  = []

        # ─── Snap-marker ───────────────────────────────────────
        self.snap_marker = QGraphicsEllipseItem(-5, -5, 10, 10)
        self.snap_marker.setPen(QPen(QColor("red"), 2))
        self.snap_marker.setBrush(Qt.NoBrush)
        self.snap_marker.setZValue(2)
        self.scene.addItem(self.snap_marker)
        self.snap_marker.hide()

        # ─── Preview line & label ──────────────────────────────
        self.preview_line = QGraphicsLineItem()
        self.preview_line.setPen(QPen(QColor("green"), 1, Qt.DashLine))
        self.preview_line.setZValue(1.5)
        self.scene.addItem(self.preview_line)
        self.preview_line.hide()

        self.preview_label = QGraphicsTextItem()
        self.preview_label.setZValue(1.5)
        self.scene.addItem(self.preview_label)
        self.preview_label.hide()

        # ─── Panning ───────────────────────────────────────────
        self._panning   = False
        self._pan_start = QPointF()

    # ─── GRID & ZOOM ────────────────────────────────────────────────────
    def drawBackground(self, painter: QPainter, rect: QRectF):
        pen = QPen(QColor(220, 220, 220), 1)
        painter.setPen(pen)
        left = int(rect.left() / self.grid_size) * self.grid_size
        top  = int(rect.top()  / self.grid_size) * self.grid_size
        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += self.grid_size
        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += self.grid_size

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    def increase_grid(self):
        self.grid_meters += 0.1
        self.grid_size   = self.grid_meters * self.scale_factor
        self.viewport().update()

    def decrease_grid(self):
        self.grid_meters = max(0.01, self.grid_meters - 0.1)
        self.grid_size   = self.grid_meters * self.scale_factor
        self.viewport().update()

    def change_grid(self):
        m, ok = QInputDialog.getDouble(
            self, "Grid Spacing", "Enter grid spacing (meters):",
            self.grid_meters, 0.01, 100.0, 2
        )
        if ok:
            self.grid_meters = m
            self.grid_size   = m * self.scale_factor
            self.viewport().update()

    # ─── MODE TOGGLES ─────────────────────────────────────────────────
    def toggle_free_mode(self, on: bool):
        self.free_mode = on

    def toggle_guide_mode(self, on: bool):
        self.guide_enabled = on
        self._guide_start  = None

    # ─── PERIMETER HISTORY ────────────────────────────────────────────
    def save_perimeter_state(self):
        self.perim_history.append(list(self.points))
        self.perim_future.clear()

    def undo_perimeter(self):
        if not self.perim_history: return
        self.perim_future.append(list(self.points))
        self.points = self.perim_history.pop()
        self._refresh()

    def redo_perimeter(self):
        if not self.perim_future: return
        self.perim_history.append(list(self.points))
        self.points = self.perim_future.pop()
        self._refresh()

    # ─── GUIDE HISTORY ────────────────────────────────────────────────
    def save_guide_state(self):
        self.guide_history.append(list(self.guides))
        self.guide_future.clear()

    def undo_guide(self):
        if not self.guide_history: return
        self.guide_future.append(list(self.guides))
        self.guides = self.guide_history.pop()
        self._refresh_guides()

    def redo_guide(self):
        if not self.guide_future: return
        self.guide_history.append(list(self.guides))
        self.guides = self.guide_future.pop()
        self._refresh_guides()

    # ─── UNIFIED undo/redo ─────────────────────────────────────────────
    def undo(self):
        if self.guide_enabled:
            self.undo_guide()
        else:
            self.undo_perimeter()

    def redo(self):
        if self.guide_enabled:
            self.redo_guide()
        else:
            self.redo_perimeter()

    # ─── CLEAR / ERASE ─────────────────────────────────────────────────
    def clear(self):
        self.save_perimeter_state()
        self.points.clear()
        self._refresh()

    def erase_guides(self):
        self.save_guide_state()
        for itm in self.guide_items + self.guide_labels:
            self.scene.removeItem(itm)
        self.guide_items.clear()
        self.guides.clear()
        self.guide_labels.clear()

    # ─── REDRAW PERIMETER ───────────────────────────────────────────────
    def _refresh(self):
        path = QPainterPath()
        if self.points:
            path.moveTo(self.points[0])
            for p in self.points[1:]:
                path.lineTo(p)
        self.path_item.setPath(path)

        for m in self.point_items:
            self.scene.removeItem(m)
        for l in self.length_items:
            self.scene.removeItem(l)
        self.point_items.clear()
        self.length_items.clear()

        for i, pt in enumerate(self.points):
            r = 3
            dot = QGraphicsEllipseItem(pt.x()-r, pt.y()-r, 2*r, 2*r)
            dot.setBrush(QColor("black"))
            dot.setPen(QPen(Qt.NoPen))
            dot.setZValue(1)
            self.scene.addItem(dot)
            self.point_items.append(dot)
            if i > 0:
                self._add_length_label(self.points[i-1], pt)

    # ─── REDRAW GUIDES ─────────────────────────────────────────────────
    def _refresh_guides(self):
        for itm in self.guide_items:
            self.scene.removeItem(itm)
        for lbl in self.guide_labels:
            self.scene.removeItem(lbl)
        self.guide_items.clear()
        self.guide_labels.clear()

        for start, end in self.guides:
            line = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
            pen  = QPen(QColor("red"), 1, Qt.SolidLine)
            line.setPen(pen)
            self.scene.addItem(line)
            self.guide_items.append(line)
            lbl = self._add_guide_length_label(start, end)
            self.guide_labels.append(lbl)

    # ─── UTILITY ───────────────────────────────────────────────────────
    def snap_to_grid(self, pos: QPointF) -> QPointF:
        x = round(pos.x() / self.grid_size) * self.grid_size
        y = round(pos.y() / self.grid_size) * self.grid_size
        return QPointF(x, y)

    # ─── MOUSE EVENTS ──────────────────────────────────────────────────
    def mousePressEvent(self, event):
        # Panning
        if event.button() == Qt.MiddleButton:
            self._panning   = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        # Guide-mode
        if event.button() == Qt.LeftButton and self.guide_enabled:
            scene_p = self.mapToScene(event.pos())
            snap_p  = self.snap_to_grid(scene_p)
            if self._guide_start is None:
                self._guide_start = snap_p
            else:
                self.save_guide_state()
                sx, sy = self._guide_start.x(), self._guide_start.y()
                dx, dy = snap_p.x()-sx, snap_p.y()-sy
                if abs(dy) > abs(dx):
                    x      = sx
                    y0, y1 = sorted([sy, snap_p.y()])
                    start, end = QPointF(x, y0), QPointF(x, y1)
                else:
                    y      = sy
                    x0, x1 = sorted([sx, snap_p.x()])
                    start, end = QPointF(x0, y), QPointF(x1, y)
                pen  = QPen(QColor("red"), 1, Qt.SolidLine)
                line = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
                line.setPen(pen)
                self.scene.addItem(line)
                self.guides.append((start, end))
                self.guide_items.append(line)
                lbl = self._add_guide_length_label(start, end)
                self.guide_labels.append(lbl)
                self._guide_start = None
            return

        # Perimeter-mode
        if event.button() == Qt.LeftButton:
            scene_p = self.mapToScene(event.pos())
            pt      = self.snap_to_grid(scene_p)
            if self.points:
                last = self.points[-1]
                if not self.free_mode:
                    dx, dy = pt.x()-last.x(), pt.y()-last.y()
                    if abs(dx) > abs(dy):
                        pt = QPointF(pt.x(), last.y())
                    else:
                        pt = QPointF(last.x(), pt.y())
            self.save_perimeter_state()
            self.points.append(pt)
            self._refresh()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 1) snap-marker
        scene_p = self.mapToScene(event.pos())
        snap_p  = self.snap_to_grid(scene_p)
        self.snap_marker.setRect(snap_p.x()-5, snap_p.y()-5, 10, 10)
        self.snap_marker.show()

        # 2) preview
        preview = False
        if self.guide_enabled and self._guide_start is not None:
            start = self._guide_start
            dx, dy = snap_p.x()-start.x(), snap_p.y()-start.y()
            if abs(dy) > abs(dx):
                end = QPointF(start.x(), snap_p.y())
            else:
                end = QPointF(snap_p.x(), start.y())
            pen = QPen(QColor("red"), 1, Qt.DashLine)
            preview = True
        elif not self.guide_enabled and self.points:
            start = self.points[-1]
            dx, dy = snap_p.x()-start.x(), snap_p.y()-start.y()
            if not self.free_mode:
                if abs(dx) > abs(dy):
                    end = QPointF(snap_p.x(), start.y())
                else:
                    end = QPointF(start.x(), snap_p.y())
            else:
                end = snap_p
            pen = QPen(QColor("green"), 1, Qt.DashLine)
            preview = True

        if preview:
            self.preview_line.setPen(pen)
            self.preview_line.setLine(start.x(), start.y(), end.x(), end.y())
            self.preview_line.show()
            dist_m = ((end.x()-start.x())**2 + (end.y()-start.y())**2)**0.5 / self.scale_factor
            mid = QPointF((start.x()+end.x())/2, (start.y()+end.y())/2)
            color = QColor("red") if self.guide_enabled else QColor("green")
            self.preview_label.setDefaultTextColor(color)
            self.preview_label.setPlainText(f"{dist_m:.2f} m")
            self.preview_label.setPos(mid)
            self.preview_label.show()
        else:
            self.preview_line.hide()
            self.preview_label.hide()

        # 3) panning
        if getattr(self, '_panning', False):
            d = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CrossCursor)
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        # undo/redo
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_Z:
                self.undo(); return
            if event.key() == Qt.Key_Y:
                self.redo(); return

        # grid shortcuts
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.increase_grid(); return
        if event.key() == Qt.Key_Minus:
            self.decrease_grid(); return

        # enter length prompt
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.guide_enabled and self._guide_start is not None:
                self.prompt_guide_length_input(); return
            if self.points:
                self.prompt_length_input(); return

        super().keyPressEvent(event)

    # ─── LENGTH INPUTS & LABELS ────────────────────────────────────────
    def prompt_length_input(self):
        length, ok = QInputDialog.getDouble(
            self, "Segment Length", "Enter length (meters):",
            1.0, 0.01, 10000.0, 2
        )
        if not ok:
            return
        last = self.points[-1]
        cursor_p = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        dx, dy   = cursor_p.x()-last.x(), cursor_p.y()-last.y()
        if self.free_mode:
            # vector direction
            norm = (dx*dx + dy*dy)**0.5
            if norm == 0: return
            ux, uy = dx/norm, dy/norm
        else:
            # axis constrained
            if abs(dx) > abs(dy):
                ux, uy = (1 if dx>0 else -1), 0
            else:
                ux, uy = 0, (1 if dy>0 else -1)
        pt = QPointF(
            last.x() + ux * length * self.scale_factor,
            last.y() + uy * length * self.scale_factor
        )
        pt = self.snap_to_grid(pt)
        self.save_perimeter_state()
        self.points.append(pt)
        self._refresh()

    def prompt_guide_length_input(self):
        length, ok = QInputDialog.getDouble(
            self, "Guide Length", "Enter guide length (meters):",
            1.0, 0.01, 10000.0, 2
        )
        if not ok or self._guide_start is None:
            return
        sx, sy = self._guide_start.x(), self._guide_start.y()
        cursor_p = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        dx, dy   = cursor_p.x()-sx, cursor_p.y()-sy
        if abs(dy) > abs(dx):
            sign = 1 if dy>0 else -1
            start = QPointF(sx, sy)
            end   = QPointF(sx, sy + sign * length * self.scale_factor)
        else:
            sign = 1 if dx>0 else -1
            start = QPointF(sx, sy)
            end   = QPointF(sx + sign * length * self.scale_factor, sy)
        end = self.snap_to_grid(end)
        pen  = QPen(QColor("red"), 1, Qt.SolidLine)
        line = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
        line.setPen(pen)
        self.scene.addItem(line)
        self.save_guide_state()
        self.guides.append((start, end))
        self.guide_items.append(line)
        lbl = self._add_guide_length_label(start, end)
        self.guide_labels.append(lbl)
        self._guide_start = None

    def _add_length_label(self, p1: QPointF, p2: QPointF):
        dist_px = ((p2.x()-p1.x())**2 + (p2.y()-p1.y())**2)**0.5
        dist_m  = dist_px / self.scale_factor
        mid     = QPointF((p1.x()+p2.x())/2, (p1.y()+p2.y())/2)
        lbl     = QGraphicsSimpleTextItem(f"{dist_m:.2f} m")
        lbl.setPos(mid)
        lbl.setZValue(1)
        self.scene.addItem(lbl)
        self.length_items.append(lbl)

    def _add_guide_length_label(self, p1: QPointF, p2: QPointF):
        dist_px = ((p2.x()-p1.x())**2 + (p2.y()-p1.y())**2)**0.5
        dist_m  = dist_px / self.scale_factor
        mid     = QPointF((p1.x()+p2.x())/2, (p1.y()+p2.y())/2)
        lbl     = QGraphicsSimpleTextItem(f"{dist_m:.2f} m")
        lbl.setBrush(QBrush(QColor("red")))
        lbl.setPos(mid)
        lbl.setZValue(1)
        self.scene.addItem(lbl)
        return lbl
