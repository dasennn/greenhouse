"""Triangle overlay manager for greenhouse visualization.

Handles drawing and management of triangular braces along the north side
of the greenhouse perimeter. Supports toggling triangles to 'window' state.
"""

from typing import List
from PySide6.QtWidgets import QGraphicsScene, QGraphicsItem, QGraphicsPolygonItem
from PySide6.QtGui import QPen, QColor, QBrush, QPolygonF
from PySide6.QtCore import Qt, QPointF

from services.geometry import group_facade_segments


class TriangleOverlayManager:
    """Manages triangular brace overlays on the greenhouse drawing."""
    
    def __init__(self, scene: QGraphicsScene, scale_factor: float, grid_w_m: float, grid_h_m: float):
        """Initialize triangle overlay manager.
        
        Args:
            scene: QGraphicsScene to draw triangles on
            scale_factor: Pixels per meter
            grid_w_m: Grid width in meters
            grid_h_m: Grid height in meters
        """
        self.scene = scene
        self.scale_factor = scale_factor
        self.grid_w_m = grid_w_m
        self.grid_h_m = grid_h_m
        self.tri_items: List[QGraphicsPolygonItem] = []
    
    def draw_north_triagonals(self, points: List[QPointF]) -> None:
        """Draw triangular braces along the north side every 1 grid box (5 m).

        If leftover >= half box (2.5 m), draw a half triangle.
        
        Args:
            points: List of perimeter points
        """
        if len(points) < 3:
            return
        
        # Resolve Βόρεια (top) horizontal chain
        pts = [(p.x(), p.y()) for p in points]
        groups = group_facade_segments(pts)
        north_chain = groups.get("Βόρεια") if groups else None
        if not north_chain:
            return

        # The Βόρεια chain is now a list of segments.
        # We need to find the overall start and end points of the chain.
        if not north_chain:
            return
            
        # Extract all points from the chain and find the leftmost and rightmost
        all_points = []
        for seg in north_chain:
            all_points.append(seg['p1'])
            all_points.append(seg['p2'])
        
        # Get unique points, as segments share them
        unique_points = sorted(list(set(all_points)), key=lambda p: p[0])
        
        start_point = unique_points[0]
        end_point = unique_points[-1]

        # Create a main segment representing the general direction of the Βόρεια chain
        main_segment = {
            "p1": start_point,
            "p2": end_point,
            "midpoint": ((start_point[0] + end_point[0]) / 2, (start_point[1] + end_point[1]) / 2)
        }
        
        self.draw_triangles_for_chain(main_segment)

    def draw_triangles_for_chain(self, segment: dict):
        """Draws triangular structures over a given segment representing a chain."""
        grid_w = self.grid_w_m * self.scale_factor
        grid_h = self.grid_h_m * self.scale_factor
        if grid_w <= 0:
            return

        p1 = segment["p1"]
        p2 = segment["p2"]
        
        # The points are already scaled from the service, so we use them directly
        x1, y1 = p1[0], p1[1]
        x2, y2 = p2[0], p2[1]

        # Use the average y-value of the segment as the base for the triangles
        y0 = (y1 + y2) / 2

        if x1 > x2:
            x1, x2 = x2, x1

        length = x2 - x1
        if length <= 0:
            return

        module = grid_w  # one column wide (e.g., 5 m)
        apex_y = y0 - grid_h  # point upwards by one grid height
        pen = QPen(QColor("#555"), 2)

        # Full triangles
        n_full = int(length // module)
        x = x1
        for _ in range(n_full):
            bx0 = x
            bx1 = x + module
            ax = x + 0.5 * module
            # Full triangle polygon (base-left, apex, base-right)
            poly = QPolygonF([QPointF(bx0, y0), QPointF(ax, apex_y), QPointF(bx1, y0)])
            self._create_triangle_item(poly, pen)
            x += module

        # Half triangle if remainder >= half box
        rem = length - n_full * module
        half_w = 0.5 * grid_w
        if rem >= (half_w - 1e-6):
            bx0 = x
            bx1 = min(x2, x + half_w)
            top_y = y0 - grid_h
            # Right triangle for half module
            poly = QPolygonF([QPointF(bx0, y0), QPointF(bx1, top_y), QPointF(bx1, y0)])
            self._create_triangle_item(poly, pen)
    
    def _create_triangle_item(self, poly: QPolygonF, pen: QPen) -> QGraphicsPolygonItem:
        """Create a triangle graphics item with standard properties.
        
        Args:
            poly: Triangle polygon
            pen: Pen for drawing
            
        Returns:
            QGraphicsPolygonItem configured for triangle display
        """
        item = QGraphicsPolygonItem(poly)
        item.setPen(pen)
        item.setBrush(Qt.NoBrush)
        item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        
        # Custom state attributes
        item._is_open = False
        item._selected_for_window = False
        item._base_pen = pen
        
        self.scene.addItem(item)
        self.tri_items.append(item)
        return item
    
    def toggle_triangle_open(self, tri_item: QGraphicsPolygonItem) -> None:
        """Toggle visual 'open' state for a triangle (window).
        
        Args:
            tri_item: Triangle item to toggle
        """
        try:
            is_open = getattr(tri_item, '_is_open', False)
            if not is_open:
                # Open: fill with a light blue and slightly lower opacity
                tri_item.setBrush(QBrush(QColor(173, 216, 230, 160)))
                tri_item.setOpacity(0.9)
                tri_item._is_open = True
            else:
                # Closed: remove fill
                tri_item.setBrush(Qt.NoBrush)
                tri_item.setOpacity(1.0)
                tri_item._is_open = False
        except Exception:
            pass
    
    def select_triangle(self, tri_item: QGraphicsPolygonItem, toggle: bool = True) -> None:
        """Mark triangle as selected-for-windowing (visual flag).
        
        Args:
            tri_item: Triangle item to select
            toggle: If True, flip the selection state
        """
        try:
            sel = getattr(tri_item, '_selected_for_window', False)
            if toggle:
                sel = not sel
            tri_item._selected_for_window = sel
            
            # Update visual appearance
            if sel:
                tri_item.setPen(QPen(QColor("orange"), 3))
            else:
                base_pen = getattr(tri_item, '_base_pen', QPen(QColor("#555"), 2))
                tri_item.setPen(base_pen)
        except Exception:
            pass
    
    def clear_triangles(self) -> None:
        """Remove all triangle items from the scene."""
        if not self.tri_items:
            return
        
        for item in list(self.tri_items):
            try:
                self.scene.removeItem(item)
            except Exception:
                pass
        
        self.tri_items.clear()
    
    def get_triangle_items(self) -> List[QGraphicsPolygonItem]:
        """Get list of all triangle items.
        
        Returns:
            List of triangle graphics items
        """
        return self.tri_items
