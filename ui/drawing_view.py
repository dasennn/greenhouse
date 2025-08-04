from typing import Optional
import math
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsTextItem,
    QGraphicsSimpleTextItem,
    QInputDialog,
    QMainWindow,
)
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QAction
from PySide6.QtCore import Qt, QPointF, QRectF

class DraggablePoint(QGraphicsEllipseItem):
    def __init__(self, view, index, pos):
        super().__init__(-3, -3, 6, 6)
        self.view = view
        self.index = index
        self.setBrush(QColor("black"))
        self.setPen(Qt.NoPen)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(1)
        self.setPos(pos)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # Update the data model while dragging
            new_pos = value
            self.view.points[self.index] = new_pos
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.view.save_state()
        self.view._refresh_perimeter()


class DrawingView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000, self)
        self.setScene(self.scene)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setCursor(Qt.ArrowCursor)

        # Grid & zoom
        self.scale_factor = 5   # pixels per meter
        self.grid_meters  = 0.1
        self.grid_size    = self.grid_meters * self.scale_factor

        # Snapping
        self.osnap_enabled = True
        self.snap_tol_px   = 10

        # Modes
        self.pointer_enabled  = True
        self.polyline_enabled = False
        self.guide_enabled    = False
        self.pan_enabled      = False
        self.free_mode        = False

        # Drawing state
        self.points        = []      # list of QPointF
        self.perim_items   = []      # QGraphicsLineItem
        self.point_items   = []      # DraggablePoint
        self.length_items  = []      # QGraphicsSimpleTextItem

        self._guide_start  = None
        self.guides        = []      # list of (start,end)
        self.guide_items   = []      # QGraphicsLineItem
        self.guide_labels  = []      # QGraphicsSimpleTextItem

        # Global undo/redo stack
        self.history = []
        self.future = []

        # Snap marker
        self.snap_marker = QGraphicsEllipseItem(-5, -5, 10, 10)
        self.snap_marker.setPen(QPen(QColor("yellow"), 2))
        self.snap_marker.setBrush(Qt.NoBrush)
        self.snap_marker.setZValue(2)
        self.scene.addItem(self.snap_marker)
        self.snap_marker.hide()

        # Preview line & label
        self.preview_line = QGraphicsLineItem()
        self.preview_line.setPen(QPen(QColor("green"), 1, Qt.DashLine))
        self.preview_line.setZValue(1.5)
        self.scene.addItem(self.preview_line)
        self.preview_line.hide()

        self.preview_label = QGraphicsTextItem()
        self.preview_label.setZValue(1.5)
        self.scene.addItem(self.preview_label)
        self.preview_label.hide()

        # Panning
        self._panning   = False
        self._pan_start = QPointF()

        # Initialize undo stack
        self.save_state()

    def save_state(self):
        # Save a deep copy of BOTH perimeter and guide state
        state = {
            "points": list(self.points),
            "guides": list(self.guides),
        }
        self.history.append(state)
        self.future.clear()

    def restore_state(self, state):
        self.points = list(state["points"])
        self.guides = list(state["guides"])
        self._refresh_perimeter()
        self._refresh_guides()

    def undo(self):
        if len(self.history) < 2:
            return
        self.future.append(self.history.pop())
        self.restore_state(self.history[-1])

    def redo(self):
        if not self.future:
            return
        state = self.future.pop()
        self.history.append(state)
        self.restore_state(state)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        pen = QPen(QColor(220, 220, 220), 1)
        painter.setPen(pen)
        # Greenhouse grid: 5m between columns (vertical), 3m between rows (horizontal)
        grid_x = 5 * self.scale_factor  # 5 meters horizontally (columns)
        grid_y = 3 * self.scale_factor  # 3 meters vertically (rows)

        # Find first vertical and horizontal grid line in view
        left = int(rect.left() / grid_x) * grid_x
        right = rect.right()
        top = int(rect.top() / grid_y) * grid_y
        bottom = rect.bottom()

        # Draw vertical grid lines (columns every 5m)
        x = left
        while x < right:
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += grid_x

        # Draw horizontal grid lines (rows every 3m)
        y = top
        while y < bottom:
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += grid_y


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

    def toggle_osnap_mode(self, on: bool):
        self.osnap_enabled = on
        color = "yellow" if on else "red"
        self.snap_marker.setPen(QPen(QColor(color), 2))

    def toggle_pointer_mode(self, on: bool):
        self.pointer_enabled = on
        if on:
            self.polyline_enabled = False
            self.guide_enabled    = False
            self.pan_enabled      = False
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setDragMode(QGraphicsView.NoDrag)

    def toggle_polyline_mode(self, on: bool):
        self.polyline_enabled = on
        if on:
            self.pointer_enabled = False
            self.guide_enabled   = False
            self.pan_enabled     = False
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def toggle_guide_mode(self, on: bool):
        self.guide_enabled = on
        self._guide_start  = None
        if on:
            self.pointer_enabled  = False
            self.polyline_enabled = False
            self.pan_enabled      = False
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def toggle_pan_mode(self, on: bool):
        self.pan_enabled = on
        if on:
            self.pointer_enabled  = False
            self.polyline_enabled = False
            self.guide_enabled    = False
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.toggle_pointer_mode(True)

    def snap_to_greenhouse_grid(self, scene_p: QPointF) -> QPointF:
        grid_x = 5 * self.scale_factor
        grid_y = 3 * self.scale_factor
        x = round(scene_p.x() / grid_x) * grid_x
        y = round(scene_p.y() / grid_y) * grid_y
        return QPointF(x, y)

    def snap_to_greenhouse_grid_or_edge_mid_if_close(self, scene_p: QPointF, view_p: QPointF, snap_tol_px=12):
        grid_x = 5 * self.scale_factor
        grid_y = 3 * self.scale_factor

        # Nearest grid intersection
        gx = round(scene_p.x() / grid_x) * grid_x
        gy = round(scene_p.y() / grid_y) * grid_y
        grid_pt = QPointF(gx, gy)
        grid_vp = self.mapFromScene(grid_pt)
        dist_grid = (grid_vp.x() - view_p.x()) ** 2 + (grid_vp.y() - view_p.y()) ** 2

        # Midpoint on vertical grid line (halfway in y, x on grid)
        mx_v = gx
        my_v = (round(scene_p.y() / grid_y - 0.5) + 0.5) * grid_y
        vert_mid_pt = QPointF(mx_v, my_v)
        vert_mid_vp = self.mapFromScene(vert_mid_pt)
        dist_vert_mid = (vert_mid_vp.x() - view_p.x()) ** 2 + (vert_mid_vp.y() - view_p.y()) ** 2

        # Midpoint on horizontal grid line (halfway in x, y on grid)
        mx_h = (round(scene_p.x() / grid_x - 0.5) + 0.5) * grid_x
        my_h = gy
        horiz_mid_pt = QPointF(mx_h, my_h)
        horiz_mid_vp = self.mapFromScene(horiz_mid_pt)
        dist_horiz_mid = (horiz_mid_vp.x() - view_p.x()) ** 2 + (horiz_mid_vp.y() - view_p.y()) ** 2

        # Find closest candidate
        min_dist = min(dist_grid, dist_vert_mid, dist_horiz_mid)
        if min_dist <= snap_tol_px ** 2:
            if min_dist == dist_grid:
                return grid_pt, "grid"
            else:
                # "mid" for both edge cases, both will show blue
                if min_dist == dist_vert_mid:
                    return vert_mid_pt, "mid"
                else:
                    return horiz_mid_pt, "mid"
        else:
            return scene_p, None

    def mousePressEvent(self, event):
        # Middle-button drag starts panning
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        view_p = event.pos()
        scene_p = self.mapToScene(view_p)
        snap_pt, snap_type = self.snap_to_greenhouse_grid_or_edge_mid_if_close(scene_p, view_p)

        grid_x = 5 * self.scale_factor
        grid_y = 3 * self.scale_factor
        nearest_grid = QPointF(
            round(scene_p.x() / grid_x) * grid_x,
            round(scene_p.y() / grid_y) * grid_y
        )

        if snap_type == "grid":
            marker_pt = snap_pt
            color = "red"
        elif snap_type == "mid":
            marker_pt = snap_pt
            color = "blue"
        else:
            marker_pt = nearest_grid
            color = "gray"

        self.snap_marker.setPen(QPen(QColor(color), 3))
        self.snap_marker.setRect(marker_pt.x() - 7, marker_pt.y() - 7, 14, 14)
        self.snap_marker.show()


        if self.pointer_enabled and event.button() == Qt.LeftButton:
            return super().mousePressEvent(event)

        # Guide-line mode
        if self.guide_enabled and event.button() == Qt.LeftButton:
            if self._guide_start is None:
                self._guide_start = snap_pt
            else:
                s, e = self._guide_start, snap_pt
                if abs(e.y() - s.y()) > abs(e.x() - s.x()):
                    e = QPointF(s.x(), e.y())
                else:
                    e = QPointF(e.x(), s.y())
                self.guides.append((s, e))
                self.save_state()
                self._guide_start = None
                self._refresh_guides()
            return

        # Polyline mode: axis‐locked by default, free‐angle with Shift
        if self.polyline_enabled and event.button() == Qt.LeftButton:
            self.free_mode = bool(event.modifiers() & Qt.ShiftModifier)
            raw_pt = snap_pt
            alt_held = bool(event.modifiers() & Qt.AltModifier)

            if not self.points:
                self.points.append(raw_pt)
                self.save_state()
            else:
                ref = self.points[0] if alt_held else self.points[-1]
                if not self.free_mode:
                    dx, dy = raw_pt.x() - ref.x(), raw_pt.y() - ref.y()
                    if abs(dx) > abs(dy):
                        new_pt = QPointF(raw_pt.x(), ref.y())
                    else:
                        new_pt = QPointF(ref.x(), raw_pt.y())
                else:
                    new_pt = raw_pt

                if alt_held:
                    self.points.insert(0, new_pt)
                else:
                    self.points.append(new_pt)
                self.save_state()

            self.preview_line.hide()
            self.preview_label.hide()
            self._refresh_perimeter()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Handle panning
        if self._panning:
            d = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(d.y()))
            return

        view_p = event.pos()
        scene_p = self.mapToScene(view_p)
        snap_pt, snap_type = self.snap_to_greenhouse_grid_or_edge_mid_if_close(scene_p, view_p)

        grid_x = 5 * self.scale_factor
        grid_y = 3 * self.scale_factor
        nearest_grid = QPointF(
            round(scene_p.x() / grid_x) * grid_x,
            round(scene_p.y() / grid_y) * grid_y
        )

        if snap_type == "grid":
            marker_pt = snap_pt
            color = "red"
        elif snap_type == "mid":
            marker_pt = snap_pt
            color = "blue"
        else:
            marker_pt = nearest_grid
            color = "gray"

        self.snap_marker.setPen(QPen(QColor(color), 3))
        self.snap_marker.setRect(marker_pt.x() - 7, marker_pt.y() - 7, 14, 14)
        self.snap_marker.show()


        # Polyline preview (free, always follows mouse)
        if self.polyline_enabled and self.points:
            self.free_mode = bool(event.modifiers() & Qt.ShiftModifier)
            alt_held = bool(event.modifiers() & Qt.AltModifier)
            ref = self.points[0] if alt_held else self.points[-1]
            neighbor = (self.points[1] if alt_held and len(self.points) > 1
                        else self.points[-2] if not alt_held and len(self.points) > 1
                        else None)
            snap_pt = scene_p  # Use free mouse position for preview

            if neighbor and not self.free_mode:
                dx, dy = snap_pt.x() - ref.x(), snap_pt.y() - ref.y()
                if abs(dx) > abs(dy):
                    target = QPointF(snap_pt.x(), ref.y())
                else:
                    target = QPointF(ref.x(), snap_pt.y())
            else:
                target = snap_pt

            self.preview_line.setLine(ref.x(), ref.y(), target.x(), target.y())
            dist = math.hypot(target.x() - ref.x(), target.y() - ref.y()) / self.scale_factor
            mid = QPointF((ref.x() + target.x()) / 2, (ref.y() + target.y()) / 2)
            self.preview_label.setPlainText(f"{dist:.2f} m")
            self.preview_label.setPos(mid)
            self.preview_line.show()
            self.preview_label.show()
        else:
            self.preview_line.hide()
            self.preview_label.hide()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            self.snap_marker.hide()
            return

        self.snap_marker.hide()
        self.preview_line.hide()
        self.preview_label.hide()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and (self.polyline_enabled or self.guide_enabled or self.pan_enabled):
            self.toggle_pointer_mode(True)
            parent = self.parent()
            if isinstance(parent, QMainWindow):
                ptr_act = parent.findChild(QAction, "Pointer")
                if ptr_act:
                    ptr_act.setChecked(True)
            return

        if event.key() == Qt.Key_Delete:
            self.delete_selected()
            return
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_Z:
                self.undo()
                return
            if event.key() == Qt.Key_Y:
                self.redo()
                return

        super().keyPressEvent(event)

    def _refresh_perimeter(self):
        for ln in self.perim_items:
            self.scene.removeItem(ln)
        for lbl in self.length_items:
            self.scene.removeItem(lbl)
        for dot in self.point_items:
            self.scene.removeItem(dot)
        self.perim_items.clear()
        self.length_items.clear()
        self.point_items.clear()

        for i, pt in enumerate(self.points):
            dot = DraggablePoint(self, i, pt)
            self.scene.addItem(dot)
            self.point_items.append(dot)
            if i > 0:
                p0 = self.points[i - 1]
                ln = QGraphicsLineItem(p0.x(), p0.y(), pt.x(), pt.y())
                ln.setPen(QPen(QColor("green"), 2))
                ln.setFlag(QGraphicsItem.ItemIsSelectable, True)
                self.scene.addItem(ln)
                self.perim_items.append(ln)
                dist = math.hypot(pt.x()-p0.x(), pt.y()-p0.y()) / self.scale_factor
                mid  = QPointF((p0.x()+pt.x())/2, (p0.y()+pt.y())/2)
                lbl  = QGraphicsSimpleTextItem(f"{dist:.2f} m")
                lbl.setPos(mid)
                lbl.setZValue(1)
                self.scene.addItem(lbl)
                self.length_items.append(lbl)

    def _refresh_guides(self):
        # Remove ALL old lines and labels
        for ln in self.guide_items:
            self.scene.removeItem(ln)
        for lbl in self.guide_labels:
            self.scene.removeItem(lbl)
        self.guide_items.clear()
        self.guide_labels.clear()
        # Recreate lines/labels for current guides
        for s, e in self.guides:
            ln = QGraphicsLineItem(s.x(), s.y(), e.x(), e.y())
            ln.setPen(QPen(QColor("red"), 1))
            ln.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self.scene.addItem(ln)
            self.guide_items.append(ln)
            lbl = QGraphicsSimpleTextItem(
                f"{math.hypot(e.x()-s.x(), e.y()-s.y())/self.scale_factor:.2f} m"
            )
            lbl.setBrush(QBrush(QColor("red")))
            mid = QPointF((s.x()+e.x())/2, (s.y()+e.y())/2)
            lbl.setPos(mid)
            lbl.setZValue(1)
            self.scene.addItem(lbl)
            self.guide_labels.append(lbl)


    def _add_guide_length_label(self, s, e):
        lbl = QGraphicsSimpleTextItem(
            f"{math.hypot(e.x()-s.x(), e.y()-s.y())/self.scale_factor:.2f} m"
        )
        lbl.setBrush(QBrush(QColor("red")))
        mid = QPointF((s.x()+e.x())/2, (s.y()+e.y())/2)
        lbl.setPos(mid)
        lbl.setZValue(1)
        self.scene.addItem(lbl)
        return lbl

    def clear_guides(self):
        """
        Remove all guide lines and their labels, preserving undo history.
        """
        self.save_state()
        for ln in list(self.guide_items):
            self.scene.removeItem(ln)
        for lbl in list(self.guide_labels):
            self.scene.removeItem(lbl)
        self.guide_items.clear()
        self.guide_labels.clear()
        self.guides.clear()
        self._refresh_guides()

    def clear_all(self):
        self.points.clear()
        self.guides.clear()
        self.save_state()
        self._refresh_perimeter()
        self._refresh_guides()
        self.snap_marker.hide()
        self.preview_line.hide()
        self.preview_label.hide()
        self.toggle_pointer_mode(True)
        

    def delete_selected(self):
        for item in self.scene.selectedItems():
            if item in self.point_items or item in self.perim_items:
                if item in self.point_items:
                    idx = self.point_items.index(item)
                else:
                    idx = self.perim_items.index(item) + 1
                del self.points[idx]
                self.save_state()  # after deletion
                self._refresh_perimeter()
                return
            if item in self.guide_items:
                idx = self.guide_items.index(item)
                del self.guides[idx]
                self.save_state()  # after deletion
                self._refresh_guides()
                return

