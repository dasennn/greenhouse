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
    geometry_changed = Signal()

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
        
        # Ortho mode (axis-locked drawing)
        self.ortho_mode = False

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

        self.preview_polyline_pen = QPen(QColor("green"), 1, Qt.DashLine)
        self.preview_guide_pen = QPen(QColor("#d32f2f"), 1, Qt.DashLine)

        self.preview_line = QGraphicsLineItem()
        self.preview_line.setPen(self.preview_polyline_pen)
        self.preview_line.setZValue(1.5)
        self.scene.addItem(self.preview_line)
        self.preview_line.hide()

        self.preview_label = QGraphicsTextItem()
        self.preview_label.setZValue(1.5)
        self.scene.addItem(self.preview_label)
        self.preview_label.hide()

    def close_perimeter(self):
        """Close the perimeter by reconstructing the drawn polyline graph-style (AutoCAD-like)."""
        if len(self.state.points) < 3:
            QMessageBox.information(
                self,
                "Κλείσιμο Περιμέτρου",
                "Χρειάζονται τουλάχιστον 3 σημεία για να κλείσει η περίμετρος."
            )
            return

        self.state.save_state()

        tol = 0.5  # pixels tolerance for merging snapped points
        breaks = set(getattr(self.state, "breaks", []) or [])

        # Map every point to a merged vertex (union of coincident points)
        merged_vertices: list[QPointF] = []
        vertex_index_map: list[int] = []
        for pt in self.state.points:
            idx = None
            for vidx, vpt in enumerate(merged_vertices):
                if math.hypot(pt.x() - vpt.x(), pt.y() - vpt.y()) <= tol:
                    idx = vidx
                    break
            if idx is None:
                merged_vertices.append(QPointF(pt))
                vertex_index_map.append(len(merged_vertices) - 1)
            else:
                vertex_index_map.append(idx)

        if len(merged_vertices) < 2:
            QMessageBox.information(
                self,
                "Κλείσιμο Περιμέτρου",
                "Δεν υπάρχουν αρκετές συνδέσεις για κλείσιμο."
            )
            return

        # Build adjacency based on sequential segments (respecting breaks)
        adjacency: list[set[int]] = [set() for _ in merged_vertices]
        for i in range(len(self.state.points) - 1):
            if i in breaks:
                continue
            a = vertex_index_map[i]
            b = vertex_index_map[i + 1]
            if a == b:
                continue
            adjacency[a].add(b)
            adjacency[b].add(a)

        # Consider only vertices participating in edges
        active_vertices = {idx for idx, nbrs in enumerate(adjacency) if nbrs}
        if not active_vertices:
            QMessageBox.information(
                self,
                "Κλείσιμο Περιμέτρου",
                "Δεν βρέθηκαν συνδεδεμένες γραμμές για κλείσιμο."
            )
            return

        # Ensure everything is in a single connected component
        start_vertex = next(iter(active_vertices))
        component: set[int] = set()
        stack = [start_vertex]
        while stack:
            v = stack.pop()
            if v in component:
                continue
            component.add(v)
            for nbr in adjacency[v]:
                if nbr in active_vertices:
                    stack.append(nbr)

        if component != active_vertices:
            dangling = active_vertices - component
            QMessageBox.information(
                self,
                "Κλείσιμο Περιμέτρου",
                "Υπάρχουν τμήματα που δεν είναι συνδεδεμένα μεταξύ τους. Συνδέστε τα πρώτα με snap."
            )
            return

        degrees = {idx: len(adjacency[idx]) for idx in component}
        branch_vertices = [idx for idx, deg in degrees.items() if deg > 2]
        if branch_vertices:
            QMessageBox.information(
                self,
                "Κλείσιμο Περιμέτρου",
                "Υπάρχουν διακλαδώσεις (κόμβοι με πάνω από 2 συνδέσεις). Η τρέχουσα έκδοση υποστηρίζει μόνο polylines χωρίς κλαδιά."
            )
            return

        endpoints = [idx for idx, deg in degrees.items() if deg == 1]
        if len(endpoints) not in (0, 2):
            QMessageBox.information(
                self,
                "Κλείσιμο Περιμέτρου",
                f"Βρέθηκαν {len(endpoints)} ελεύθερα άκρα. Συνδέστε τα πρώτα ώστε να παραμείνουν 0 ή 2."
            )
            return

        # Helper to linearise the component (path or cycle)
        def build_order(start_idx: int, end_idx: int | None) -> list[int] | None:
            ordered: list[int] = [start_idx]
            prev = None
            current = start_idx
            visited_edges: set[tuple[int, int]] = set()

            while True:
                if end_idx is not None and current == end_idx:
                    break

                neighbours = adjacency[current].copy()
                if prev is not None:
                    neighbours.discard(prev)

                if not neighbours:
                    if end_idx is None:
                        break
                    # Dead-end before reaching target
                    return None

                if len(neighbours) > 1:
                    # Branching inside supposed polyline
                    return None

                nxt = neighbours.pop()
                edge = (current, nxt)
                if edge in visited_edges:
                    break
                visited_edges.add(edge)
                visited_edges.add((nxt, current))

                ordered.append(nxt)
                prev = current
                current = nxt

                if end_idx is None and current == start_idx:
                    break

            return ordered

        if len(endpoints) == 0:
            # Closed loop already; traverse once around the cycle
            node_order = build_order(start_vertex, None)
            if not node_order or len(set(node_order)) != len(component):
                QMessageBox.information(
                    self,
                    "Κλείσιμο Περιμέτρου",
                    "Αδυναμία ανασύνθεσης της κλειστής γραμμής. Ελέγξτε για διακλαδώσεις."
                )
                return
            if node_order[-1] == node_order[0]:
                node_order = node_order[:-1]
        else:
            node_order = build_order(endpoints[0], endpoints[1])
            if not node_order or node_order[-1] != endpoints[1]:
                QMessageBox.information(
                    self,
                    "Κλείσιμο Περιμέτρου",
                    "Δεν βρέθηκε μονοπάτι που να ενώνει τα δύο ελεύθερα άκρα."
                )
                return
            if set(node_order) != component:
                QMessageBox.information(
                    self,
                    "Κλείσιμο Περιμέτρου",
                    "Ορισμένα τμήματα δεν συμπεριλήφθηκαν στο τελικό πολύγωνο. Συνδέστε τα σε μία συνεχόμενη γραμμή."
                )
                return

        # Rebuild ordered perimeter points
        ordered_points = [QPointF(merged_vertices[idx]) for idx in node_order]
        if len(ordered_points) < 3:
            QMessageBox.information(
                self,
                "Κλείσιμο Περιμέτρου",
                "Το σχήμα χρειάζεται τουλάχιστον 3 μη ομοιόμορφα σημεία."
            )
            return

        self.state.points = ordered_points
        self.state.breaks.clear()
        self.state.start_new_chain_pending = False

        # Append starting point to close the loop explicitly
        self.state.points.append(QPointF(self.state.points[0]))

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

    def _commit_dimensional_segment(self, length_m: float, alt_held: bool):
        """
        Commit a segment with exact length in meters.
        Direction respects ortho_mode setting.
        """
        if not self.state.points:
            return

        ref = self.state.points[0] if alt_held else self.state.points[-1]
        # Determine direction vector from ref to current mouse scene position
        dx = self.state.last_mouse_scene.x() - ref.x()
        dy = self.state.last_mouse_scene.y() - ref.y()

        if self.ortho_mode:
            # Axis-locked: choose axis with larger magnitude
            if abs(dx) >= abs(dy):
                # Horizontal
                ux, uy = (1.0 if dx >= 0 else -1.0), 0.0
            else:
                # Vertical
                ux, uy = 0.0, (1.0 if dy >= 0 else -1.0)
        else:
            # Free mode: use actual mouse direction; fall back to +X if zero length
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
        try:
            self.geometry_changed.emit()
        except Exception:
            pass

    def _commit_dimensional_guide(self, length_m: float):
        """
        Commit a guide line with an exact length in meters from the current guide start.
        Direction respects ortho_mode setting.
        """
        if self.state._guide_start is None:
            return

        s = self.state._guide_start
        # Use current mouse to determine direction
        dx = self.state.last_mouse_scene.x() - s.x()
        dy = self.state.last_mouse_scene.y() - s.y()

        if self.ortho_mode:
            # Axis-locked: choose H or V
            if abs(dx) >= abs(dy):
                # Horizontal guide
                ux, uy = (1.0 if dx >= 0 else -1.0), 0.0
            else:
                # Vertical guide
                ux, uy = 0.0, (1.0 if dy >= 0 else -1.0)
        else:
            # Free: use actual direction
            mag = math.hypot(dx, dy)
            if mag == 0:
                ux, uy = 1.0, 0.0
            else:
                ux, uy = dx / mag, dy / mag

        L = length_m * self.scale_factor
        e = QPointF(s.x() + ux * L, s.y() + uy * L)

        self.state.guides.append((s, e))
        self.state.save_state()
        self.state._guide_start = None
        self._refresh_guides()
        self.preview_line.hide()
        self.preview_label.hide()
        try:
            self.geometry_changed.emit()
        except Exception:
            pass
    def save_state(self):
        # Save a deep copy of BOTH perimeter and guide state
        state = {
            "points": list(self.state.points),
            "guides": list(self.state.guides),
            "breaks": list(getattr(self.state, 'breaks', []) or []),
            "start_new_chain_pending": bool(getattr(self.state, 'start_new_chain_pending', False)),
        }
        self.state.history.append(state)
        self.state.future.clear()

    def restore_state(self, state):
        self.state.points = list(state["points"])
        self.state.guides = list(state["guides"])
        self.state.breaks = list(state.get("breaks", []))
        self.state.start_new_chain_pending = bool(state.get("start_new_chain_pending", False))
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
        try:
            self.geometry_changed.emit()
        except Exception:
            pass

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

        # PRIORITY 1: Check perimeter vertices (HIGHEST priority for connections)
        closest_vertex_dist = float('inf')
        closest_vertex_pt = None
        closest_vertex_idx = None
        for idx, pt in enumerate(self.state.points):
            vp = self.mapFromScene(pt)
            d = (vp.x() - view_p.x()) ** 2 + (vp.y() - view_p.y()) ** 2
            if d < closest_vertex_dist:
                closest_vertex_dist = d
                closest_vertex_pt = pt
                closest_vertex_idx = idx

        # If vertex is close enough, ALWAYS prefer it (ignore grid)
        if closest_vertex_pt is not None and closest_vertex_dist <= snap_tol_px ** 2:
            return closest_vertex_pt, "vertex", closest_vertex_idx

        # PRIORITY 2: Check guide endpoints
        closest_guide_dist = float('inf')
        closest_guide_pt = None
        for s, e in getattr(self.state, 'guides', []) or []:
            for gpt in (s, e):
                vp = self.mapFromScene(gpt)
                d = (vp.x() - view_p.x()) ** 2 + (vp.y() - view_p.y()) ** 2
                if d < closest_guide_dist:
                    closest_guide_dist = d
                    closest_guide_pt = gpt

        # If guide endpoint is close enough, prefer it over grid
        if closest_guide_pt is not None and closest_guide_dist <= snap_tol_px ** 2:
            return closest_guide_pt, "guide", None

        # PRIORITY 3: Grid intersection (fallback)
        gx = round(scene_p.x() / grid_x) * grid_x
        gy = round(scene_p.y() / grid_y) * grid_y
        grid_pt = QPointF(gx, gy)
        grid_vp = self.mapFromScene(grid_pt)
        dist_grid = (grid_vp.x() - view_p.x()) ** 2 + (grid_vp.y() - view_p.y()) ** 2
        
        if dist_grid <= snap_tol_px ** 2:
            return grid_pt, "grid", None
        
        # No snap - return original point
        return scene_p, None, None

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
        snap_pt, snap_type, _ = self.snap_to_greenhouse_grid_or_edge_mid_if_close(scene_p, view_p)

        # Color-code snap markers
        if snap_type == "grid":
            color = "red"
        elif snap_type == "vertex":
            color = "cyan"  # Perimeter vertex
        elif snap_type == "guide":
            color = "magenta"  # Guide endpoint
        else:
            # No snap; fallback to nearest grid for marker position
            grid_x = self.grid_w_m * self.scale_factor
            grid_y = self.grid_h_m * self.scale_factor
            snap_pt = QPointF(
                round(scene_p.x() / grid_x) * grid_x,
                round(scene_p.y() / grid_y) * grid_y
            )
            color = "gray"

        self.snap_marker.setPen(QPen(QColor(color), 3))
        self.snap_marker.setRect(snap_pt.x() - 7, snap_pt.y() - 7, 14, 14)
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

        # Guide-line mode: respect ortho_mode flag
        if self.state.guide_enabled and event.button() == Qt.LeftButton:
            if self.state._guide_start is None:
                self.state._guide_start = snap_pt
            else:
                s, e = self.state._guide_start, snap_pt
                if self.ortho_mode:
                    # Axis-locked: choose H or V
                    if abs(e.y() - s.y()) > abs(e.x() - s.x()):
                        e = QPointF(s.x(), e.y())
                    else:
                        e = QPointF(e.x(), s.y())
                self.state.guides.append((s, e))
                self.state.save_state()
                self.state._guide_start = None
                self._refresh_guides()
                self.preview_line.hide()
                self.preview_label.hide()
            return

        # Polyline mode: respect ortho_mode flag
        if self.state.polyline_enabled and event.button() == Qt.LeftButton:
            raw_pt = snap_pt
            alt_held = bool(event.modifiers() & Qt.AltModifier)

            # Check if snapped to an existing vertex (connection point)
            snapped_to_vertex = (snap_type == "vertex")
            
            if not self.state.points or getattr(self.state, 'start_new_chain_pending', False):
                # Start a new chain
                if getattr(self.state, 'start_new_chain_pending', False) and self.state.points:
                    # Record a break between previous last and the new first
                    try:
                        self.state.breaks.append(len(self.state.points) - 1)
                    except Exception:
                        pass
                self.state.start_new_chain_pending = False
                # First point of new chain is placed as-is
                self.state.points.append(raw_pt)
                self.state.save_state()
            else:
                # Check ortho mode
                ref = self.state.points[0] if alt_held else self.state.points[-1]
                if self.ortho_mode:
                    # Axis-locked: choose H or V based on larger delta
                    dx, dy = raw_pt.x() - ref.x(), raw_pt.y() - ref.y()
                    if abs(dx) > abs(dy):
                        new_pt = QPointF(raw_pt.x(), ref.y())
                    else:
                        new_pt = QPointF(ref.x(), raw_pt.y())
                else:
                    # Free mode
                    new_pt = raw_pt

                if alt_held:
                    self.state.points.insert(0, new_pt)
                else:
                    self.state.points.append(new_pt)
                self.state.save_state()
                
                # If we snapped to an existing vertex, end this chain automatically
                # (user is connecting to existing geometry)
                if snapped_to_vertex:
                    self.state.start_new_chain_pending = True

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
        snap_pt, snap_type, _ = self.snap_to_greenhouse_grid_or_edge_mid_if_close(scene_p, view_p)

        # Color-code snap markers for mouse move
        if snap_type == "grid":
            color = "red"
        elif snap_type == "vertex":
            color = "cyan"
        elif snap_type == "guide":
            color = "magenta"
        else:
            grid_x = self.grid_w_m * self.scale_factor
            grid_y = self.grid_h_m * self.scale_factor
            snap_pt = QPointF(
                round(scene_p.x() / grid_x) * grid_x,
                round(scene_p.y() / grid_y) * grid_y
            )
            color = "gray"

        self.snap_marker.setPen(QPen(QColor(color), 3))
        self.snap_marker.setRect(snap_pt.x() - 7, snap_pt.y() - 7, 14, 14)
        if not (self.state.pointer_enabled and snap_type in ("grid", "vertex", "guide")):
            self.snap_marker.show()
        else:
            self.snap_marker.hide()


        preview_active = False

        # Polyline preview: respect ortho_mode
        if self.state.polyline_enabled and self.state.points and not getattr(self.state, 'start_new_chain_pending', False):
            alt_held = bool(event.modifiers() & Qt.AltModifier)
            ref = self.state.points[0] if alt_held else self.state.points[-1]

            if self.ortho_mode:
                # Axis-locked preview
                dx, dy = scene_p.x() - ref.x(), scene_p.y() - ref.y()
                if abs(dx) > abs(dy):
                    target = QPointF(scene_p.x(), ref.y())
                else:
                    target = QPointF(ref.x(), scene_p.y())
            else:
                # Free preview
                target = scene_p

            self.preview_line.setPen(self.preview_polyline_pen)
            self.preview_label.setDefaultTextColor(self.preview_polyline_pen.color())
            self.preview_line.setLine(ref.x(), ref.y(), target.x(), target.y())
            dist = math.hypot(target.x() - ref.x(), target.y() - ref.y()) / self.scale_factor
            mid = QPointF((ref.x() + target.x()) / 2, (ref.y() + target.y()) / 2)
            self.preview_label.setPlainText(GeometryHelper.format_measure(dist))
            self.preview_label.setPos(mid)
            self.preview_line.show()
            self.preview_label.show()
            preview_active = True

        # Guide preview when drawing helper lines
        if (not preview_active and self.state.guide_enabled and 
                self.state._guide_start is not None):
            s = self.state._guide_start
            target = snap_pt
            if self.ortho_mode:
                dx = target.x() - s.x()
                dy = target.y() - s.y()
                if abs(dy) > abs(dx):
                    target = QPointF(s.x(), target.y())
                else:
                    target = QPointF(target.x(), s.y())

            self.preview_line.setPen(self.preview_guide_pen)
            self.preview_label.setDefaultTextColor(self.preview_guide_pen.color())
            self.preview_line.setLine(s.x(), s.y(), target.x(), target.y())
            dist = math.hypot(target.x() - s.x(), target.y() - s.y()) / self.scale_factor
            mid = QPointF((s.x() + target.x()) / 2, (s.y() + target.y()) / 2)
            self.preview_label.setPlainText(GeometryHelper.format_measure(dist))
            self.preview_label.setPos(mid)
            self.preview_line.show()
            self.preview_label.show()
            preview_active = True

        if not preview_active:
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
        if event.key() == Qt.Key_Escape:
            # If user is typing a dimension, cancel buffer but keep current mode
            if self.state._dim_input:
                self.state._dim_input = ""
                self.preview_label.hide()
                return
            # ESC always returns to Pointer mode (Δείκτης)
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
                if self.state._dim_input:
                    # Dimensional segment commit (always free mode now)
                    try:
                        length_m = float(self.state._dim_input)
                    except ValueError:
                        self.state._dim_input = ""
                        self.preview_label.hide()
                        return
                    alt_held = bool(event.modifiers() & Qt.AltModifier)
                    self._commit_dimensional_segment(length_m, alt_held)
                    self.state._dim_input = ""
                    self.preview_label.hide()
                    return
                else:
                    # No dimensional input: end current small shape and start a new chain
                    if self.state.points:
                        self.state.save_state()
                        self.state.start_new_chain_pending = True
                        # Visual reset of preview of current segment
                        self.preview_line.hide()
                        self.preview_label.hide()
                        try:
                            self.geometry_changed.emit()
                        except Exception:
                            pass
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
        try:
            self.geometry_changed.emit()
        except Exception:
            pass

    def clear_all(self):
        self.state.points.clear()
        self.state.guides.clear()
        try:
            self.state.breaks.clear()
            self.state.start_new_chain_pending = False
        except Exception:
            pass
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
        try:
            self.geometry_changed.emit()
        except Exception:
            pass
        

    def delete_selected(self):
        for item in self.scene.selectedItems():
            # Try to delete via perimeter manager
            if self.perimeter_manager.delete_point_by_item(item):
                try:
                    self.geometry_changed.emit()
                except Exception:
                    pass
                return
            
            if item in self.guide_items:
                idx = self.guide_items.index(item)
                del self.state.guides[idx]
                self.state.save_state()  # after deletion
                self._refresh_guides()
                try:
                    self.geometry_changed.emit()
                except Exception:
                    pass
                return

    def _refresh_perimeter(self):
        """Helper used by DraggablePoint to refresh UI after drag/move."""
        try:
            self.perimeter_manager.refresh_perimeter()
        finally:
            try:
                self.geometry_changed.emit()
            except Exception:
                pass


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
