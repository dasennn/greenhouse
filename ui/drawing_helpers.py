"""Snap-to-grid and geometry helper functions for drawing."""

import math
from PySide6.QtCore import QPointF
from typing import Tuple, Optional


class SnapHelper:
    """Helper for snapping to grid points and edges."""
    
    @staticmethod
    def snap_to_grid(scene_p: QPointF, grid_w: float, grid_h: float) -> QPointF:
        """Snap to nearest grid intersection."""
        x = round(scene_p.x() / grid_w) * grid_w
        y = round(scene_p.y() / grid_h) * grid_h
        return QPointF(x, y)
    
    @staticmethod
    def snap_to_grid_or_edge_mid(
        scene_p: QPointF, 
        view_p: QPointF,
        grid_w: float, 
        grid_h: float,
        snap_tol_px: float = 12.0,
        mapFromScene = None
    ) -> Tuple[QPointF, Optional[str]]:
        """
        Snap to grid intersection or edge midpoint if close enough.
        
        Returns:
            (snap_point, snap_type) where snap_type is 'grid', 'mid', or None
        """
        # Nearest grid intersection
        gx = round(scene_p.x() / grid_w) * grid_w
        gy = round(scene_p.y() / grid_h) * grid_h
        grid_pt = QPointF(gx, gy)
        grid_vp = mapFromScene(grid_pt) if mapFromScene else view_p
        dist_grid = (grid_vp.x() - view_p.x()) ** 2 + (grid_vp.y() - view_p.y()) ** 2
        
        # Midpoint on vertical grid line
        mx_v = gx
        my_v = (round(scene_p.y() / grid_h - 0.5) + 0.5) * grid_h
        vert_mid_pt = QPointF(mx_v, my_v)
        vert_mid_vp = mapFromScene(vert_mid_pt) if mapFromScene else view_p
        dist_vert_mid = (vert_mid_vp.x() - view_p.x()) ** 2 + (vert_mid_vp.y() - view_p.y()) ** 2
        
        # Midpoint on horizontal grid line
        mx_h = (round(scene_p.x() / grid_w - 0.5) + 0.5) * grid_w
        my_h = gy
        horiz_mid_pt = QPointF(mx_h, my_h)
        horiz_mid_vp = mapFromScene(horiz_mid_pt) if mapFromScene else view_p
        dist_horiz_mid = (horiz_mid_vp.x() - view_p.x()) ** 2 + (horiz_mid_vp.y() - view_p.y()) ** 2
        
        # Find closest candidate
        min_dist = min(dist_grid, dist_vert_mid, dist_horiz_mid)
        if min_dist <= snap_tol_px ** 2:
            if min_dist == dist_grid:
                return grid_pt, "grid"
            elif min_dist == dist_vert_mid:
                return vert_mid_pt, "mid"
            else:
                return horiz_mid_pt, "mid"
        else:
            return scene_p, None


class GeometryHelper:
    """Helper for geometry calculations."""
    
    @staticmethod
    def polygon_area_m2(points, scale_factor: float) -> float:
        """Calculate area of polygon in square meters."""
        if len(points) < 3:
            return 0.0
        arr = list(points)
        if arr[0] != arr[-1]:
            arr.append(arr[0])
        s = 0.0
        for i in range(len(arr) - 1):
            x1, y1 = arr[i].x(), arr[i].y()
            x2, y2 = arr[i + 1].x(), arr[i + 1].y()
            s += x1 * y2 - x2 * y1
        area_px2 = abs(s) * 0.5
        return area_px2 / (scale_factor ** 2)
    
    @staticmethod
    def format_measure(val, unit='m', decimals=2) -> str:
        """Format a measurement with optional unit."""
        try:
            if val is None:
                return "—"
            v = float(val)
            if abs(v - round(v)) < 1e-6:
                return f"{int(round(v))} {unit}"
            return f"{v:.{decimals}f} {unit}"
        except Exception:
            return str(val)
    
    @staticmethod
    def format_area(val, decimals=3) -> str:
        """Format area measurement."""
        try:
            if val is None:
                return "—"
            v = float(val)
            if abs(v - round(v)) < 1e-6:
                return f"{int(round(v))} m²"
            return f"{v:.{decimals}f} m²"
        except Exception:
            return str(val)
