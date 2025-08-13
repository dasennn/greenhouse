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
    QMessageBox,
)
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QAction
from PySide6.QtCore import Qt, QPointF, QRectF, Signal

EPS = 1e-7  # Tolerance for floating-point comparisons

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
    perimeter_closed = Signal(list, float, float, int, int)  # points, perimeter_m, area_m2, full, partial  # points, perimeter_m, full_grid_boxes
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

        # Perimeter lock
        self.perimeter_locked = False

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

        # Dimensional input (type length then Enter)
        self._dim_input = ""
        self.last_mouse_scene = QPointF()
    def _commit_dimensional_segment(self, length_m: float, alt_held: bool, free_mode: bool):
        """
        Commit a segment with exact length in meters.
        Direction is determined by current mouse vector from the reference point:
          - If free_mode is False (default), lock to horizontal/vertical based on larger delta.
          - If free_mode is True (Shift held), follow the mouse direction freely.
        """
        if not self.points:
            return

        ref = self.points[0] if alt_held else self.points[-1]
        # Determine direction vector from ref to current mouse scene position
        dx = self.last_mouse_scene.x() - ref.x()
        dy = self.last_mouse_scene.y() - ref.y()

        if not free_mode:
            # Axis lock: choose axis with larger magnitude
            if abs(dx) >= abs(dy):
                # Horizontal
                ux, uy = (1.0 if dx >= 0 else -1.0), 0.0
            else:
                # Vertical
                ux, uy = 0.0, (1.0 if dy >= 0 else -1.0)
        else:
            # Free: use actual mouse direction; fall back to +X if zero length
            mag = math.hypot(dx, dy)
            if mag == 0:
                ux, uy = 1.0, 0.0
            else:
                ux, uy = dx / mag, dy / mag

        # Convert meters to scene pixels
        L = length_m * self.scale_factor
        new_x = ref.x() + ux * L
        new_y = ref.y() + uy * L
        new_pt = QPointF(new_x, new_y)

        if alt_held:
            self.points.insert(0, new_pt)
        else:
            self.points.append(new_pt)

        self.save_state()
        self.preview_line.hide()
        self.preview_label.hide()
        self._refresh_perimeter()

    def _commit_dimensional_guide(self, length_m: float):
        """
        Commit a guide line with an exact length in meters from the current guide start.
        Direction is axis-locked (horizontal/vertical) and chosen based on the current
        mouse vector from the start point.
        """
        if self._guide_start is None:
            return

        s = self._guide_start
        # Use current mouse to pick the axis and direction
        dx = self.last_mouse_scene.x() - s.x()
        dy = self.last_mouse_scene.y() - s.y()

        if abs(dx) >= abs(dy):
            # Horizontal guide
            ux, uy = (1.0 if dx >= 0 else -1.0), 0.0
        else:
            # Vertical guide
            ux, uy = 0.0, (1.0 if dy >= 0 else -1.0)

        L = length_m * self.scale_factor
        e = QPointF(s.x() + ux * L, s.y() + uy * L)

        self.guides.append((s, e))
        self.save_state()
        self._guide_start = None
        self._refresh_guides()
        self.preview_line.hide()
        self.preview_label.hide()
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
        if on and getattr(self, "perimeter_locked", False):
            QMessageBox.information(self, "Perimeter is closed", "Drawing is locked. Use Clear All to start over.")
            on = False
        self.polyline_enabled = on

        if on:
            self.pointer_enabled = False
            self.guide_enabled   = False
            self.pan_enabled     = False
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    
    def toggle_guide_mode(self, on: bool):
        if on and getattr(self, "perimeter_locked", False):
            QMessageBox.information(self, "Perimeter is closed", "Drawing is locked. Use Clear All to start over.")
            on = False
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
        # Clear any live dimension entry on click
        self._dim_input = ""
        self.preview_label.hide()
        # If perimeter is locked, restrict to selection and panning; ignore creation clicks
        if getattr(self, 'perimeter_locked', False):
            if event.button() == Qt.MiddleButton:
                self._panning = True
                self._pan_start = event.pos()
                self.setCursor(Qt.ClosedHandCursor)
                return
            return QGraphicsView.mousePressEvent(self, event)
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
        self.last_mouse_scene = scene_p
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

        # If user is typing a dimension, show that near the cursor
        if (self.polyline_enabled or self.guide_enabled) and self._dim_input:
            self.preview_label.setPlainText(f"{self._dim_input} m")
            self.preview_label.setPos(self.last_mouse_scene + QPointF(10, 10))
            self.preview_label.show()

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

        # Dimensional input (polyline mode): Only commit on Enter/Return
        if self.polyline_enabled:
            key = event.key()
            text = event.text()

            # Allow digits and a single decimal point to build up buffer (optional)
            if text and (text.isdigit() or text == "."):
                if text == "." and "." in self._dim_input:
                    pass
                else:
                    self._dim_input += text
                    # Show live input near cursor
                    self.preview_label.setPlainText(f"{self._dim_input} m")
                    self.preview_label.setPos(self.last_mouse_scene + QPointF(10, 10))
                    self.preview_label.show()
                return

            # Allow Backspace editing of buffer
            if key == Qt.Key_Backspace and self._dim_input:
                self._dim_input = self._dim_input[:-1]
                if self._dim_input:
                    self.preview_label.setPlainText(f"{self._dim_input} m")
                    self.preview_label.setPos(self.last_mouse_scene + QPointF(10, 10))
                    self.preview_label.show()
                else:
                    self.preview_label.hide()
                return

            # Cancel buffer with Escape (but do not exit polyline mode)
            if key == Qt.Key_Escape and self._dim_input:
                self._dim_input = ""
                self.preview_label.hide()
                return

            # Commit on Enter / Return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                # If buffer is empty, prompt for length
                if not self._dim_input:
                    # Prompt user for length (meters)
                    val, ok = QInputDialog.getDouble(
                        self, "Segment Length", "Enter segment length (meters):", 1.0, 0.01, 1000.0, 2
                    )
                    if not ok:
                        # Cancelled dialog
                        self._dim_input = ""
                        self.preview_label.hide()
                        return
                    length_m = val
                else:
                    try:
                        length_m = float(self._dim_input)
                    except ValueError:
                        self._dim_input = ""
                        self.preview_label.hide()
                        return
                alt_held = bool(event.modifiers() & Qt.AltModifier)
                free_mode = bool(event.modifiers() & Qt.ShiftModifier)
                self._commit_dimensional_segment(length_m, alt_held, free_mode)
                self._dim_input = ""
                self.preview_label.hide()
                return

        # Dimensional input (guide mode): Only commit on Enter/Return
        if self.guide_enabled:
            key = event.key()
            text = event.text()

            # Allow digits and a single decimal point
            if text and (text.isdigit() or text == "."):
                if text == "." and "." in self._dim_input:
                    pass
                else:
                    self._dim_input += text
                    # Show live input near cursor
                    self.preview_label.setPlainText(f"{self._dim_input} m")
                    self.preview_label.setPos(self.last_mouse_scene + QPointF(10, 10))
                    self.preview_label.show()
                return

            # Allow Backspace editing of buffer
            if key == Qt.Key_Backspace and self._dim_input:
                self._dim_input = self._dim_input[:-1]
                if self._dim_input:
                    self.preview_label.setPlainText(f"{self._dim_input} m")
                    self.preview_label.setPos(self.last_mouse_scene + QPointF(10, 10))
                    self.preview_label.show()
                else:
                    self.preview_label.hide()
                return

            # Commit on Enter / Return (only if a start point exists)
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if self._guide_start is None:
                    # No active guide start; ignore Enter in this context
                    self._dim_input = ""
                    self.preview_label.hide()
                    return

                # If buffer is empty, prompt for length (meters)
                if not self._dim_input:
                    val, ok = QInputDialog.getDouble(
                        self, "Guide Length", "Enter guide length (meters):", 1.0, 0.01, 1000.0, 2
                    )
                    if not ok:
                        self._dim_input = ""
                        self.preview_label.hide()
                        return
                    length_m = val
                else:
                    try:
                        length_m = float(self._dim_input)
                    except ValueError:
                        self._dim_input = ""
                        self.preview_label.hide()
                        return

                self._commit_dimensional_guide(length_m)
                self._dim_input = ""
                self.preview_label.hide()
                return

        super().keyPressEvent(event)

    
    def segs_intersect(self, a1, a2, b1, b2):
        """Check if two line segments intersect with stricter conditions."""
        EPS = 1e-7  # Tolerance for floating-point comparisons

        def orient(ax, ay, bx, by, cx, cy):
            return (by - ay) * (cx - bx) - (bx - ax) * (cy - by)

        (x1, y1), (x2, y2) = a1, a2
        (x3, y3), (x4, y4) = b1, b2

        def on_seg(xa, ya, xb, yb, xc, yc):
            return (
                min(xa, xb) - EPS <= xc <= max(xa, xb) + EPS
                and min(ya, yb) - EPS <= yc <= max(ya, yb) + EPS
                and abs((xb - xa) * (yc - ya) - (yb - ya) * (xc - xa)) <= EPS
            )

        d1 = orient(x1, y1, x2, y2, x3, y3)
        d2 = orient(x1, y1, x2, y2, x4, y4)
        d3 = orient(x3, y3, x4, y4, x1, y1)
        d4 = orient(x3, y3, x4, y4, x2, y2)

        # Check if segments straddle each other
        if (
            ((d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS))
            and ((d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS))
        ):
            return True

        # Check if segments are collinear and overlap
        if abs(d1) <= EPS and on_seg(x1, y1, x2, y2, x3, y3):
            return True
        if abs(d2) <= EPS and on_seg(x1, y1, x2, y2, x4, y4):
            return True
        if abs(d3) <= EPS and on_seg(x3, y3, x4, y4, x1, y1):
            return True
        if abs(d4) <= EPS and on_seg(x3, y3, x4, y4, x2, y2):
            return True

        return False

    def _polygon_area_m2(self, pts):
            """Return area (m^2) of polygon given by list of QPointF (closed or open)."""
            if len(pts) < 3:
                return 0.0
            arr = list(pts)
            if arr[0] != arr[-1]:
                arr.append(arr[0])
            s = 0.0
            for i in range(len(arr)-1):
                x1, y1 = arr[i].x(), arr[i].y()
                x2, y2 = arr[i+1].x(), arr[i+1].y()
                s += x1*y2 - x2*y1
            area_px2 = abs(s) * 0.5
            return area_px2 / (self.scale_factor ** 2)

    def close_perimeter(self):
                """Close the current perimeter (if open), lock drawing, and emit perimeter/grid/area info."""
                if len(self.points) < 3:
                    QMessageBox.information(self, "Close Perimeter", "Need at least 3 points to close a perimeter.")
                    return
                if self.points[0] != self.points[-1]:
                    self.save_state()
                    self.points.append(self.points[0])
                self._refresh_perimeter()

                # Calculate perimeter length in meters
                perimeter_m = 0.0
                for i in range(1, len(self.points)):
                    p0, p1 = self.points[i-1], self.points[i]
                    perimeter_m += math.hypot(p1.x()-p0.x(), p1.y()-p0.y()) / self.scale_factor

                # Area in square meters
                area_m2 = self._polygon_area_m2(self.points)

                # Grid boxes
                full, partial = self.compute_grid_box_counts()

                # Hard lock drawing until Clear All
                self.perimeter_locked = True
                self.toggle_pointer_mode(True)

                # Emit extended data
                self.perimeter_closed.emit(list(self.points), perimeter_m, area_m2, full, partial)
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
        self._dim_input = ""
        self.perimeter_locked = False
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


    def analyze_grid_coverage(self):
        """Compute and show how many full and partial greenhouse grid boxes are inside the drawn perimeter."""
        if len(self.points) < 3:
            QMessageBox.information(self, "Grid Coverage", "Draw at least 3 points to form a perimeter first.")
            return
        full, partial = self.compute_grid_box_counts()
        msg = (
            f"Complete grid boxes: {full}\n"
            f"Partial grid boxes:  {partial}\n\n"
            f"Grid size: 5m x 3m"
        )
        QMessageBox.information(self, "Grid Coverage", msg)

    
    def compute_grid_box_counts(self, points=None, grid_w_m: float = 5.0, grid_h_m: float = 3.0, scale_factor=None):
        """
        Count full and partial grid rectangles covered by the polygon.
        - *Full* = all four rectangle corners are inside (or on) the polygon
        - *Partial* = rectangle intersects polygon but is not full
        Accepts optional explicit *points* ([(x,y), ...] in scene coordinates).
        Grid size is in meters; converted to scene units via *scale_factor* (px/m).
        Returns (full_count, partial_count).
        """
        # Resolve inputs
        if scale_factor is None:
            scale_factor = self.scale_factor
        grid_w = grid_w_m * scale_factor
        grid_h = grid_h_m * scale_factor
        # Build polygon in scene coordinates
        if points is None:
            pts = [(p.x(), p.y()) for p in self.points]
        else:
            pts = [(float(x), float(y)) for (x, y) in points]
        if len(pts) < 3:
            return 0, 0
        if pts[0] != pts[-1]:
            pts = pts + [pts[0]]

        # Helpers
        def point_on_seg(px, py, x1, y1, x2, y2):
            # Bounding box check with tolerance
            if (min(x1, x2)-EPS <= px <= max(x1, x2)+EPS and
                min(y1, y2)-EPS <= py <= max(y1, y2)+EPS):
                # Collinearity via cross product
                dx1, dy1 = x2 - x1, y2 - y1
                dx2, dy2 = px - x1, py - y1
                return abs(dx1*dy2 - dy1*dx2) <= EPS
            return False

        def point_in_poly(px, py):
            # Winding / ray-casting with boundary = inside
            inside = False
            for i in range(len(pts)-1):
                x1, y1 = pts[i]
                x2, y2 = pts[i+1]
                # Boundary check
                if point_on_seg(px, py, x1, y1, x2, y2):
                    return True
                # Ray cast
                if ((y1 > py) != (y2 > py)):
                    xint = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
                    if xint >= px - EPS:
                        inside = not inside
            return inside

        def poly_intersects_rect(x0, y0, x1, y1):
            """Check if the polygon intersects the rectangle."""
            print(f"Checking intersection for rect: ({x0}, {y0}), ({x1}, {y1})")

            # Any polygon edge intersects rectangle edges?
            rect_edges = [
                ((x0, y0), (x1, y0)),
                ((x1, y0), (x1, y1)),
                ((x1, y1), (x0, y1)),
                ((x0, y1), (x0, y0))
            ]
            for i in range(len(pts) - 1):
                a1, a2 = pts[i], pts[i + 1]
                for e in rect_edges:
                    if self.segs_intersect(a1, a2, e[0], e[1]):
                        print("Edge intersects rectangle")
                        return True

            # Check if the rectangle is partially contained (at least one corner inside polygon)
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            inside_corners = [point_in_poly(cx, cy) for cx, cy in corners]
            if any(inside_corners) and not all(inside_corners):
                print("Rectangle partially contained")
                return True

            # Check if the rectangle fully contains the polygon (midpoint test)
            mx, my = (x0 + x1) * 0.5, (y0 + y1) * 0.5
            if point_in_poly(mx, my):
                print("Midpoint inside polygon")
                return True

            print("No intersection")
            return False

        # Iterate grid cells covering bounding box of the polygon
        xs = [x for x, _ in pts]
        ys = [y for _, y in pts]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        # Snap bbox to grid index range
        gx0 = int((minx) // grid_w) - 1
        gy0 = int((miny) // grid_h) - 1
        gx1 = int((maxx) // grid_w) + 2
        gy1 = int((maxy) // grid_h) + 2
        full = 0
        partial = 0
        for gy in range(gy0, gy1):
            y0 = gy * grid_h
            y1 = y0 + grid_h
            for gx in range(gx0, gx1):
                x0 = gx * grid_w
                x1 = x0 + grid_w
                corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                inside_flags = [point_in_poly(cx, cy) for (cx, cy) in corners]
                if all(inside_flags):
                    print(f"Full box at grid ({gx}, {gy})")
                    full += 1
                elif poly_intersects_rect(x0, y0, x1, y1):
                    print(f"Partial box at grid ({gx}, {gy})")
                    partial += 1
                else:
                    print(f"Empty box at grid ({gx}, {gy})")

        return full, partial
