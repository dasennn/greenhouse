"""Drawing view for greenhouse design."""

import math
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
    QGraphicsSimpleTextItem,
    QInputDialog,
    QMainWindow,
    QMessageBox,
)
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QAction, QFont, QPolygonF
from PySide6.QtCore import Qt, QPointF, QRectF, Signal

from services.geometry_utils import (
    compute_grid_coverage as geom_compute_grid_coverage,
    estimate_triangle_posts_3x5_with_sides,
    estimate_gutters_length,
)
from ui.drawing_state import DrawingState
from ui.drawing_helpers import SnapHelper, GeometryHelper
from ui.draggable_point import DraggablePoint
from ui.triangle_overlay import TriangleOverlayManager
from ui.drawing_renderer import DrawingRenderer
from ui.perimeter_manager import PerimeterManager

EPS = 1e-7


class DrawingView(QGraphicsView):
    """Main drawing view for greenhouse design."""
    
    perimeter_closed = Signal(list, float, float, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Initialize scene
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000, self)
        self.setScene(self.scene)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setCursor(Qt.ArrowCursor)

        # Initialize state management
        self.state = DrawingState()
        
        # Scale and grid settings
        self.scale_factor = 5
        self.grid_meters = 0.1
        self.grid_size = self.grid_meters * self.scale_factor
        self.snap_tol_px = 10
        
        # Greenhouse grid dimensions in meters
        self.grid_w_m = 5.0
        self.grid_h_m = 3.0
        self.greenhouse_type = "3x5_with_sides"

        # Initialize managers
        self.perimeter_manager = PerimeterManager(self.scene, self.state, self.scale_factor, view=self)
        self.triangle_manager = TriangleOverlayManager(self.scene, self.scale_factor, self.grid_w_m, self.grid_h_m)
        
        # Graphics items
        self.guide_items = []
        self.guide_labels = []

        self.snap_marker = QGraphicsEllipseItem(-5, -5, 10, 10)
        self.snap_marker.setPen(QPen(QColor("yellow"), 2))
        self.snap_marker.setBrush(Qt.NoBrush)
        self.snap_marker.setZValue(2)
        self.scene.addItem(self.snap_marker)
        self.snap_marker.hide()

        self.preview_line = QGraphicsLineItem()
        self.preview_line.setPen(QPen(QColor("green"), 1, Qt.DashLine))
        self.preview_line.setZValue(1.5)
        self.scene.addItem(self.preview_line)
        self.preview_line.hide()

        self.preview_label = QGraphicsTextItem()
        self.preview_label.setZValue(1.5)
        self.scene.addItem(self.preview_label)
        self.preview_label.hide()

    def close_perimeter(self):
        if len(self.state.points) < 3:
            QMessageBox.information(self, "Κλείσιμο Περιμέτρου", "Χρειάζονται τουλάχιστον 3 σημεία για να κλείσει η περίμετρος.")
            return
        if self.state.points[0] != self.state.points[-1]:
            self.state.save_state()
            self.state.points.append(self.state.points[0])
        self.perimeter_manager.refresh_perimeter()

        # compute perimeter and area
        perimeter_m = 0.0
        for i in range(1, len(self.state.points)):
            p0, p1 = self.state.points[i - 1], self.state.points[i]
            perimeter_m += math.hypot(p1.x() - p0.x(), p1.y() - p0.y()) / self.scale_factor
        area_m2 = GeometryHelper.polygon_area_m2(self.state.points, self.scale_factor)
        # compute grid coverage via services
        pts = [(p.x(), p.y()) for p in self.state.points]
        coverage = geom_compute_grid_coverage(
            pts,
            grid_w_m=self.grid_w_m,
            grid_h_m=self.grid_h_m,
            scale_factor=self.scale_factor,
        )
        partial_details = []
        full_area = 0.0
        partial_area_sum = 0.0
        if coverage is not None:
            partial_details = coverage.get('partial_details', [])
            full_area = coverage.get('full_area_m2', 0.0)
            partial_area_sum = sum((p.get('area_m2', 0.0) for p in partial_details))

        total_box_area = full_area + partial_area_sum
        diff = area_m2 - total_box_area

        # Build concise popup: polygon area, boxes area vs partials, difference, and per-partial crossing lengths only
        lines = [f"Polygon area: {GeometryHelper.format_area(area_m2)}",
                 f"Full boxes area: {GeometryHelper.format_area(full_area)}",
                 f"Partial boxes area (sum): {GeometryHelper.format_area(partial_area_sum)}",
                 f"Boxes total area: {GeometryHelper.format_area(total_box_area)}",
                 f"Difference (polygon - boxes): {GeometryHelper.format_area(diff)}",
                 "",
                 "Partial boxes (crossing lengths):"]
        for p in partial_details:
            gx, gy = p.get('grid', (None, None))
            cl = p.get('boundary_crossing_length_m', 0.0)
            lines.append(f"{(gx,gy)} crossing={GeometryHelper.format_measure(cl, decimals=2)}")

        # Append posts estimation (3x5 with sides) into the same popup
        try:
            est = estimate_triangle_posts_3x5_with_sides(
                pts,
                grid_w_m=self.grid_w_m,
                grid_h_m=self.grid_h_m,
                scale_factor=self.scale_factor,
            )
            if est:
                lines += [
                    "",
                    "Posts estimation (3x5 with sides):",
                    f"Width: {est['north_width_m']:.2f} m, Depth: {est['depth_m']:.2f} m",
                    f"Rows: {est['rows']}",
                    f"Full triangles/row: {est['full_triangles_per_row']}, Half/row: {int(est['has_half_triangle_per_row'])}",
                    f"Low posts/row: {est['low_posts_per_row']}, Tall posts/row: {est['tall_posts_per_row']}",
                    f"Total low posts: {est['total_low_posts']}, Total tall posts: {est['total_tall_posts']}",
                ]
        except Exception:
            pass

        # Append gutters estimation into the same popup
        try:
            gut = estimate_gutters_length(
                pts,
                grid_w_m=self.grid_w_m,
                grid_h_m=self.grid_h_m,
                scale_factor=self.scale_factor,
            )
            if gut:
                lines += [
                    "",
                    "Gutters estimation:",
                    f"Width: {gut['north_width_m']:.2f} m, Depth: {gut['depth_m']:.2f} m",
                    # Show module width and relation to grid_w
                    (
                        lambda mw, gw: (
                            f"Module width: {mw:.2f} m ("
                            + ("1×grid_w" if abs(mw-gw) < 1e-6 else ("2×grid_w" if abs(mw-2*gw) < 1e-6 else f"~{mw/gw:.2f}×grid_w"))
                            + ")"
                        )
                    )(gut['module_w_m'], self.grid_w_m),
                    f"Vertical lines along Y: {gut['lines_x']} (includes edges)",
                    f"Piece length: {gut['piece_len_m']:.2f} m",
                    f"Pieces per line: {gut['pieces_per_line']}",
                    f"Total gutter pieces: {gut['total_pieces']}",
                ]
        except Exception:
            pass

        # Prepare overlay cache with the latest diagnostics; remove popup
        self.state._overlay_data = {
            "perimeter_m": perimeter_m,
            "area_m2": area_m2,
            "coverage": coverage,
            "posts": est if 'est' in locals() else None,
            "gutters": gut if 'gut' in locals() else None,
        }
        # Trigger repaint to show overlay
        try:
            self.viewport().update()
        except Exception:
            pass

        # Draw greenhouse type-specific features (default: 3x5 with sides)
        try:
            self.triangle_manager.clear_triangles()
            self.triangle_manager.draw_north_triagonals(self.state.points)
        except Exception:
            pass

        self.state.perimeter_locked = True
        self.toggle_pointer_mode(True)
        self.perimeter_closed.emit(list(self.state.points), perimeter_m, area_m2, partial_details)

    def _commit_dimensional_segment(self, length_m: float, alt_held: bool, free_mode: bool):
        """
        Commit a segment with exact length in meters.
        Direction is determined by current mouse vector from the reference point:
          - If free_mode is False (default), lock to horizontal/vertical based on larger delta.
          - If free_mode is True (Shift held), follow the mouse direction freely.
        """
        if not self.state.points:
            return

        ref = self.state.points[0] if alt_held else self.state.points[-1]
        # Determine direction vector from ref to current mouse scene position
        dx = self.state.last_mouse_scene.x() - ref.x()
        dy = self.state.last_mouse_scene.y() - ref.y()

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
            self.state.points.insert(0, new_pt)
        else:
            self.state.points.append(new_pt)

        self.state.save_state()
        self.preview_line.hide()
        self.preview_label.hide()
        self.perimeter_manager.refresh_perimeter()

    def _commit_dimensional_guide(self, length_m: float):
        """
        Commit a guide line with an exact length in meters from the current guide start.
        Direction is axis-locked (horizontal/vertical) and chosen based on the current
        mouse vector from the start point.
        """
        if self.state._guide_start is None:
            return

        s = self.state._guide_start
        # Use current mouse to pick the axis and direction
        dx = self.state.last_mouse_scene.x() - s.x()
        dy = self.state.last_mouse_scene.y() - s.y()

        if abs(dx) >= abs(dy):
            # Horizontal guide
            ux, uy = (1.0 if dx >= 0 else -1.0), 0.0
        else:
            # Vertical guide
            ux, uy = 0.0, (1.0 if dy >= 0 else -1.0)

        L = length_m * self.scale_factor
        e = QPointF(s.x() + ux * L, s.y() + uy * L)

        self.state.guides.append((s, e))
        self.state.save_state()
        self.state._guide_start = None
        self._refresh_guides()
        self.preview_line.hide()
        self.preview_label.hide()
    def save_state(self):
        # Save a deep copy of BOTH perimeter and guide state
        state = {
            "points": list(self.state.points),
            "guides": list(self.state.guides),
        }
        self.state.history.append(state)
        self.state.future.clear()

    def restore_state(self, state):
        self.state.points = list(state["points"])
        self.state.guides = list(state["guides"])
        self.perimeter_manager.refresh_perimeter()
        self._refresh_guides()

    def undo(self):
        if len(self.state.history) < 2:
            return
        self.state.future.append(self.state.history.pop())
        # Use the view's restore which also refreshes the perimeter and guides
        # (calling DrawingState.restore_state directly doesn't update the UI and
        # can leave graphics items out-of-sync, potentially causing handlers
        # to fire and clear the redo stack).
        self.restore_state(self.state.history[-1])

    def redo(self):
        if not self.state.future:
            return
        state = self.state.future.pop()
        self.state.history.append(state)
        # Likewise, restore via the view so the scene is updated immediately.
        self.restore_state(state)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """Draw background grid using DrawingRenderer."""
        grid_w_px = self.grid_w_m * self.scale_factor
        grid_h_px = self.grid_h_m * self.scale_factor
        DrawingRenderer.draw_grid_background(painter, rect, grid_w_px, grid_h_px)


    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    def zoom_to_drawing(self):
        """Zoom and center the view to the current drawing (perimeter and guides).

        Fits the bounding rectangle of all relevant items into the viewport, with
        a small margin. If there are no items, it recenters to scene rect.
        """
        try:
            # Collect candidate points: perimeter points and guide endpoints
            xs, ys = [], []
            for p in self.state.points:
                try:
                    xs.append(p.x()); ys.append(p.y())
                except Exception:
                    try:
                        xs.append(float(p[0])); ys.append(float(p[1]))
                    except Exception:
                        pass
            for s, e in getattr(self.state, 'guides', []) or []:
                try:
                    xs += [s.x(), e.x()]; ys += [s.y(), e.y()]
                except Exception:
                    pass

            if xs and ys:
                minx, maxx = min(xs), max(xs)
                miny, maxy = min(ys), max(ys)
                # Add padding in scene units (px); ~ one grid cell worth of padding
                pad_x = max(20.0, 0.5 * self.grid_w_m * self.scale_factor)
                pad_y = max(20.0, 0.5 * self.grid_h_m * self.scale_factor)
                rect = QRectF(minx - pad_x, miny - pad_y, (maxx - minx) + 2*pad_x, (maxy - miny) + 2*pad_y)
            else:
                # No geometry yet; use a portion of the scene rect
                rect = self.scene.sceneRect()

            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                rect = self.scene.sceneRect()

            # Reset any previous scaling then fit
            self.resetTransform()
            self.fitInView(rect, Qt.KeepAspectRatio)
            # Slight zoom-out for breathing room
            self.scale(0.98, 0.98)
            # Center explicitly
            self.centerOn(rect.center())
        except Exception:
            # Fallback: reset and center to full scene
            try:
                self.resetTransform()
                self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
            except Exception:
                pass

    def toggle_osnap_mode(self, on: bool):
        self.state.osnap_enabled = on
        color = "yellow" if on else "red"
        self.snap_marker.setPen(QPen(QColor(color), 2))

    def toggle_pointer_mode(self, on: bool):
        self.state.pointer_enabled = on
        if on:
            self.state.polyline_enabled = False
            self.state.guide_enabled    = False
            self.state.pan_enabled      = False
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setDragMode(QGraphicsView.NoDrag)

    
    def toggle_polyline_mode(self, on: bool):
        if on and self.state.perimeter_locked:
            return
        self.state.polyline_enabled = on

        if on:
            self.state.pointer_enabled = False
            self.state.guide_enabled   = False
            self.state.pan_enabled     = False
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    
    def toggle_guide_mode(self, on: bool):
        if on and self.state.perimeter_locked:
            QMessageBox.information(self, "Περίμετρος κλειστή", "Το σχέδιο είναι κλειδωμένο. Χρησιμοποιήστε 'Καθαρισμός' για να ξεκινήσετε από την αρχή.")
            on = False
        self.state.guide_enabled = on

        self.state._guide_start  = None
        if on:
            self.state.pointer_enabled  = False
            self.state.polyline_enabled = False
            self.state.pan_enabled      = False
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def toggle_pan_mode(self, on: bool):
        self.state.pan_enabled = on
        if on:
            self.state.pointer_enabled  = False
            self.state.polyline_enabled = False
            self.state.guide_enabled    = False
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.toggle_pointer_mode(True)

    def snap_to_greenhouse_grid(self, scene_p: QPointF) -> QPointF:
        grid_x = self.grid_w_m * self.scale_factor
        grid_y = self.grid_h_m * self.scale_factor
        x = round(scene_p.x() / grid_x) * grid_x
        y = round(scene_p.y() / grid_y) * grid_y
        return QPointF(x, y)

    def snap_to_greenhouse_grid_or_edge_mid_if_close(self, scene_p: QPointF, view_p: QPointF, snap_tol_px=12):
        grid_x = self.grid_w_m * self.scale_factor
        grid_y = self.grid_h_m * self.scale_factor

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
        # Allow drawing even without a named project; startup dialog still offers choices.
        # Clear any live dimension entry on click
        self.state._dim_input = ""
        self.preview_label.hide()
        # Ctrl+Click on triangles toggles their 'open' (window) state — re-added per user request
        if event.button() == Qt.LeftButton and (event.modifiers() & Qt.ControlModifier):
            itm = self.itemAt(event.pos())
            if itm:
                # Walk up to a known triangle polygon in tri_items
                tri_items = self.triangle_manager.get_triangle_items()
                tri = itm
                while tri is not None and tri not in tri_items:
                    tri = tri.parentItem()
                if tri in tri_items:
                    self.triangle_manager.toggle_triangle_open(tri)
                    return
        # If perimeter is locked, restrict to selection and panning; ignore creation clicks
        if self.state.perimeter_locked:
            if event.button() == Qt.MiddleButton:
                self.state._panning = True
                self.state._pan_start = event.pos()
                self.setCursor(Qt.ClosedHandCursor)
                return
            return QGraphicsView.mousePressEvent(self, event)
        # Middle-button drag starts panning
        if event.button() == Qt.MiddleButton:
            self.state._panning = True
            self.state._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        view_p = event.pos()
        scene_p = self.mapToScene(view_p)
        snap_pt, snap_type = self.snap_to_greenhouse_grid_or_edge_mid_if_close(scene_p, view_p)

        grid_x = self.grid_w_m * self.scale_factor
        grid_y = self.grid_h_m * self.scale_factor
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
        # If pointer mode is active, hide the snap marker entirely
        if self.state.pointer_enabled:
            self.snap_marker.hide()
        else:
            self.snap_marker.show()


        if self.state.pointer_enabled and event.button() == Qt.LeftButton:
            # If clicking a triangle while in pointer mode, toggle selection-for-window
            # Ignore Ctrl modifier so Ctrl+Click does not pick triangles
            if not (event.modifiers() & Qt.ControlModifier):
                itm = self.itemAt(view_p)
                if itm:
                    tri = itm
                    while tri is not None and tri not in self.triangle_manager.tri_items:
                        tri = tri.parentItem()
                    if tri in self.triangle_manager.tri_items:
                        # toggle selection-for-window
                        self.triangle_manager.select_triangle(tri)
                        return
            return super().mousePressEvent(event)

        # Guide-line mode
        if self.state.guide_enabled and event.button() == Qt.LeftButton:
            if self.state._guide_start is None:
                self.state._guide_start = snap_pt
            else:
                s, e = self.state._guide_start, snap_pt
                if abs(e.y() - s.y()) > abs(e.x() - s.x()):
                    e = QPointF(s.x(), e.y())
                else:
                    e = QPointF(e.x(), s.y())
                self.state.guides.append((s, e))
                self.state.save_state()
                self.state._guide_start = None
                self._refresh_guides()
            return

        # Polyline mode: axis‐locked by default, free‐angle with Shift
        if self.state.polyline_enabled and event.button() == Qt.LeftButton:
            self.state.free_mode = bool(event.modifiers() & Qt.ShiftModifier)
            raw_pt = snap_pt
            alt_held = bool(event.modifiers() & Qt.AltModifier)

            if not self.state.points:
                self.state.points.append(raw_pt)
                self.state.save_state()
            else:
                ref = self.state.points[0] if alt_held else self.state.points[-1]
                if not self.state.free_mode:
                    dx, dy = raw_pt.x() - ref.x(), raw_pt.y() - ref.y()
                    if abs(dx) > abs(dy):
                        new_pt = QPointF(raw_pt.x(), ref.y())
                    else:
                        new_pt = QPointF(ref.x(), raw_pt.y())
                else:
                    new_pt = raw_pt

                if alt_held:
                    self.state.points.insert(0, new_pt)
                else:
                    self.state.points.append(new_pt)
                self.state.save_state()

            self.preview_line.hide()
            self.preview_label.hide()
            self.perimeter_manager.refresh_perimeter()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Handle panning
        if self.state._panning:
            d = event.pos() - self.state._pan_start
            self.state._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(d.y()))
            return

        view_p = event.pos()
        scene_p = self.mapToScene(view_p)
        self.state.last_mouse_scene = scene_p
        snap_pt, snap_type = self.snap_to_greenhouse_grid_or_edge_mid_if_close(scene_p, view_p)

        grid_x = self.grid_w_m * self.scale_factor
        grid_y = self.grid_h_m * self.scale_factor
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
        if not (self.state.pointer_enabled and snap_type in ("grid", "mid")):
            self.snap_marker.show()
        else:
            self.snap_marker.hide()


        # Polyline preview (free, always follows mouse)
        if self.state.polyline_enabled and self.state.points:
            self.state.free_mode = bool(event.modifiers() & Qt.ShiftModifier)
            alt_held = bool(event.modifiers() & Qt.AltModifier)
            ref = self.state.points[0] if alt_held else self.state.points[-1]
            neighbor = (self.state.points[1] if alt_held and len(self.state.points) > 1
                        else self.state.points[-2] if not alt_held and len(self.state.points) > 1
                        else None)
            snap_pt = scene_p  # Use free mouse position for preview

            if neighbor and not self.state.free_mode:
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
            self.preview_label.setPlainText(GeometryHelper.format_measure(dist))
            self.preview_label.setPos(mid)
            self.preview_line.show()
            self.preview_label.show()
        else:
            self.preview_line.hide()
            self.preview_label.hide()

        # If user is typing a dimension, show that near the cursor
        if (self.state.polyline_enabled or self.state.guide_enabled) and self.state._dim_input:
            self.preview_label.setPlainText(f"{self.state._dim_input} m")
            self.preview_label.setPos(self.state.last_mouse_scene + QPointF(10, 10))
            self.preview_label.show()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self.state._panning:
            self.state._panning = False
            self.setCursor(Qt.ArrowCursor)
            self.snap_marker.hide()
            return

        self.snap_marker.hide()
        self.preview_line.hide()
        self.preview_label.hide()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        # Allow keyboard-driven creation even without a named project.
        if event.key() == Qt.Key_Escape and (self.state.polyline_enabled or self.state.guide_enabled or self.state.pan_enabled):
            self.toggle_pointer_mode(True)
            parent = self.parent()
            if isinstance(parent, QMainWindow):
                ptr_act = parent.findChild(QAction, "Δείκτης") or parent.findChild(QAction, "Pointer")
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
        if self.state.polyline_enabled:
            key = event.key()
            text = event.text()

            # Allow digits and a single decimal point to build up buffer (optional)
            if text and (text.isdigit() or text == "."):
                if text == "." and "." in self.state._dim_input:
                    pass
                else:
                    self.state._dim_input += text
                    # Show live input near cursor
                    self.preview_label.setPlainText(f"{self.state._dim_input} m")
                    self.preview_label.setPos(self.state.last_mouse_scene + QPointF(10, 10))
                    self.preview_label.show()
                return

            # Allow Backspace editing of buffer
            if key == Qt.Key_Backspace and self.state._dim_input:
                self.state._dim_input = self.state._dim_input[:-1]
                if self.state._dim_input:
                    self.preview_label.setPlainText(f"{self.state._dim_input} m")
                    self.preview_label.setPos(self.state.last_mouse_scene + QPointF(10, 10))
                    self.preview_label.show()
                else:
                    self.preview_label.hide()
                return

            # Cancel buffer with Escape (but do not exit polyline mode)
            if key == Qt.Key_Escape and self.state._dim_input:
                self.state._dim_input = ""
                self.preview_label.hide()
                return

            # Commit on Enter / Return
            if key in (Qt.Key_Return, Qt.Key_Enter):
                # If buffer is empty, prompt for length
                if not self.state._dim_input:
                    # Prompt user for length (meters)
                    val, ok = QInputDialog.getDouble(
                        self, "Μήκος Τμήματος", "Εισάγετε μήκος τμήματος (μέτρα):", 1.0, 0.01, 1000.0, 2
                    )
                    if not ok:
                        # Cancelled dialog
                        self.state._dim_input = ""
                        self.preview_label.hide()
                        return
                    length_m = val
                else:
                    try:
                        length_m = float(self.state._dim_input)
                    except ValueError:
                        self.state._dim_input = ""
                        self.preview_label.hide()
                        return
                alt_held = bool(event.modifiers() & Qt.AltModifier)
                free_mode = bool(event.modifiers() & Qt.ShiftModifier)
                self._commit_dimensional_segment(length_m, alt_held, free_mode)
                self.state._dim_input = ""
                self.preview_label.hide()
                return

        # Dimensional input (guide mode): Only commit on Enter/Return
        if self.state.guide_enabled:
            key = event.key()
            text = event.text()

            # Allow digits and a single decimal point
            if text and (text.isdigit() or text == "."):
                if text == "." and "." in self.state._dim_input:
                    pass
                else:
                    self.state._dim_input += text
                    # Show live input near cursor
                    self.preview_label.setPlainText(f"{self.state._dim_input} m")
                    self.preview_label.setPos(self.state.last_mouse_scene + QPointF(10, 10))
                    self.preview_label.show()
                return

            # Allow Backspace editing of buffer
            if key == Qt.Key_Backspace and self.state._dim_input:
                self.state._dim_input = self.state._dim_input[:-1]
                if self.state._dim_input:
                    self.preview_label.setPlainText(f"{self.state._dim_input} m")
                    self.preview_label.setPos(self.state.last_mouse_scene + QPointF(10, 10))
                    self.preview_label.show()
                else:
                    self.preview_label.hide()
                return

            # Commit on Enter / Return (only if a start point exists)
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if self.state._guide_start is None:
                    # No active guide start; ignore Enter in this context
                    self.state._dim_input = ""
                    self.preview_label.hide()
                    return

                # If buffer is empty, prompt for length (meters)
                if not self.state._dim_input:
                    val, ok = QInputDialog.getDouble(
                        self, "Μήκος Οδηγού", "Εισάγετε μήκος οδηγού (μέτρα):", 1.0, 0.01, 1000.0, 2
                    )
                    if not ok:
                        self.state._dim_input = ""
                        self.preview_label.hide()
                        return
                    length_m = val
                else:
                    try:
                        length_m = float(self.state._dim_input)
                    except ValueError:
                        self.state._dim_input = ""
                        self.preview_label.hide()
                        return

                self._commit_dimensional_guide(length_m)
                self.state._dim_input = ""
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
        if (((d1 > EPS and d2 < -EPS) or (d1 < -EPS and d2 > EPS))
                and ((d3 > EPS and d4 < -EPS) or (d3 < -EPS and d4 > EPS))):
            return True
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



    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Draw foreground overlays using DrawingRenderer."""
        show_diagnostics = (getattr(self, 'show_overlay', False) and 
                          self.state._overlay_data and 
                          self.state.perimeter_locked)
        
        DrawingRenderer.draw_foreground_overlays(
            painter,
            self.viewport().width(),
            self.viewport().height(),
            self.state._overlay_data if show_diagnostics else None,
            show_diagnostics,
            self.grid_w_m,
            self.grid_h_m
        )
        
        # Call base to ensure default behavior
        return super().drawForeground(painter, rect)

    def recompute_overlay_if_possible(self):
        """Recompute overlay diagnostics if a closed perimeter exists and is locked."""
        if not self.state.perimeter_locked or len(self.state.points) < 3:
            return
        # compute perimeter and area
        perimeter_m = 0.0
        for i in range(1, len(self.state.points)):
            p0, p1 = self.state.points[i - 1], self.state.points[i]
            perimeter_m += math.hypot(p1.x() - p0.x(), p1.y() - p0.y()) / self.scale_factor
        area_m2 = GeometryHelper.polygon_area_m2(self.state.points, self.scale_factor)
        pts = [(p.x(), p.y()) for p in self.state.points]
        try:
            coverage = geom_compute_grid_coverage(
                pts,
                grid_w_m=self.grid_w_m,
                grid_h_m=self.grid_h_m,
                scale_factor=self.scale_factor,
            )
        except Exception:
            coverage = None
        try:
            posts = estimate_triangle_posts_3x5_with_sides(
                pts,
                grid_w_m=self.grid_w_m,
                grid_h_m=self.grid_h_m,
                scale_factor=self.scale_factor,
            )
        except Exception:
            posts = None
        try:
            gut = estimate_gutters_length(
                pts,
                grid_w_m=self.grid_w_m,
                grid_h_m=self.grid_h_m,
                scale_factor=self.scale_factor,
            )
        except Exception:
            gut = None
        self.state._overlay_data = {
            "perimeter_m": perimeter_m,
            "area_m2": area_m2,
            "coverage": coverage,
            "posts": posts,
            "gutters": gut,
        }
        try:
            self.viewport().update()
        except Exception:
            pass

    def _refresh_guides(self):
        # Remove ALL old lines and labels
        for ln in self.guide_items:
            self.scene.removeItem(ln)
        for lbl in self.guide_labels:
            self.scene.removeItem(lbl)
        self.guide_items.clear()
        self.guide_labels.clear()
        # Recreate lines/labels for current guides
        for s, e in self.state.guides:
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
        self.state.save_state()
        for ln in list(self.guide_items):
            self.scene.removeItem(ln)
        for lbl in list(self.guide_labels):
            self.scene.removeItem(lbl)
        self.guide_items.clear()
        self.guide_labels.clear()
        self.state.guides.clear()
        self._refresh_guides()

    def clear_all(self):
        self.state.points.clear()
        self.state.guides.clear()
        self.state.save_state()
        self.perimeter_manager.refresh_perimeter()
        self._refresh_guides()
        self.triangle_manager.clear_triangles()
        # No need to clear overlay; it's repainted each frame
        self.state._overlay_data = None
        self.snap_marker.hide()
        self.preview_line.hide()
        self.preview_label.hide()
        self.state._dim_input = ""
        self.state.perimeter_locked = False
        self.toggle_pointer_mode(True)
        # Sync UI button state to pointer mode
        parent = self.parent()
        if isinstance(parent, QMainWindow):
            ptr_act = parent.findChild(QAction, "Δείκτης")
            if ptr_act:
                ptr_act.setChecked(True)
        

    def delete_selected(self):
        for item in self.scene.selectedItems():
            # Try to delete via perimeter manager
            if self.perimeter_manager.delete_point_by_item(item):
                return
            
            if item in self.guide_items:
                idx = self.guide_items.index(item)
                del self.state.guides[idx]
                self.state.save_state()  # after deletion
                self._refresh_guides()
                return


    def analyze_grid_coverage(self):
        """Compute and show how many full and partial greenhouse grid boxes are inside the drawn perimeter."""
        if len(self.state.points) < 3:
            QMessageBox.information(self, "Grid Coverage", "Draw at least 3 points to form a perimeter first.")
            return
        # Compute detailed coverage using services
        pts = [(p.x(), p.y()) for p in self.state.points]
        coverage = geom_compute_grid_coverage(
            pts,
            grid_w_m=self.grid_w_m,
            grid_h_m=self.grid_h_m,
            scale_factor=self.scale_factor,
        )
        if coverage is None:
            QMessageBox.information(self, "Grid Coverage", "Could not compute grid coverage.")
            return
        poly_area_m2 = coverage['polygon_area_m2']
        full_count = coverage['full_count']
        full_area_m2 = coverage['full_area_m2']
        partial_details = coverage['partial_details']
        partial_count = len(partial_details)
        partial_area_m2 = sum(p['area_m2'] for p in partial_details)

        msg = (
            f"Polygon area: {poly_area_m2:.3f} m²\n"
            f"Full boxes: {full_count} (area {full_area_m2:.3f} m²)\n"
            f"Partial boxes: {partial_count} (area {partial_area_m2:.3f} m²)\n\n"
            f"Sum full+partial area: {(full_area_m2 + partial_area_m2):.3f} m²\n"
            f"Grid size: {self.grid_w_m:g}m x {self.grid_h_m:g}m"
        )
        QMessageBox.information(self, "Grid Coverage", msg)

    # Coverage helpers now live in services.geometry_utils.
