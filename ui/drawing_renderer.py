"""Drawing renderer for greenhouse visualization.

Handles background grid drawing and foreground overlay rendering
(north arrow and diagnostics panel).
"""

from typing import Optional, Dict, Any
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtCore import QRectF

from ui.drawing_helpers import GeometryHelper


class DrawingRenderer:
    """Handles rendering of background grid and foreground overlays."""
    
    @staticmethod
    def draw_grid_background(painter: QPainter, rect: QRectF, 
                           grid_w_px: float, grid_h_px: float) -> None:
        """Draw background grid lines.
        
        Args:
            painter: QPainter instance
            rect: Rectangle to draw in
            grid_w_px: Grid width in pixels
            grid_h_px: Grid height in pixels
        """
        pen = QPen(QColor(220, 220, 220), 1)
        painter.setPen(pen)
        
        # Find first vertical and horizontal grid line in view
        left = int(rect.left() / grid_w_px) * grid_w_px
        right = rect.right()
        top = int(rect.top() / grid_h_px) * grid_h_px
        bottom = rect.bottom()
        
        # Draw vertical grid lines (columns)
        x = left
        while x < right:
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += grid_w_px
        
        # Draw horizontal grid lines (rows)
        y = top
        while y < bottom:
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += grid_h_px
    
    @staticmethod
    def draw_foreground_overlays(painter: QPainter, viewport_width: int, 
                                viewport_height: int, overlay_data: Optional[Dict[str, Any]],
                                show_diagnostics: bool, grid_w_m: float, 
                                grid_h_m: float) -> None:
        """Draw foreground overlays (north arrow and diagnostics panel).
        
        Args:
            painter: QPainter instance
            viewport_width: Viewport width in pixels
            viewport_height: Viewport height in pixels
            overlay_data: Optional dictionary with diagnostic data
            show_diagnostics: Whether to show diagnostics panel
            grid_w_m: Grid width in meters
            grid_h_m: Grid height in meters
        """
        painter.save()
        try:
            # Reset transforms to device (viewport) coordinates
            painter.resetTransform()
            vw = viewport_width
            vh = viewport_height
            
            # Clip to the viewport to avoid partial clipping from scene rect
            painter.setClipping(True)
            painter.setClipRect(0, 0, vw, vh)
            
            # Draw north arrow at top-right
            DrawingRenderer._draw_north_arrow(painter, vw, vh)
            
            # Draw diagnostics panel at top-left if enabled
            if show_diagnostics and overlay_data:
                DrawingRenderer._draw_diagnostics_panel(
                    painter, overlay_data, grid_w_m, grid_h_m
                )
        finally:
            painter.restore()
    
    @staticmethod
    def _draw_north_arrow(painter: QPainter, vw: int, vh: int) -> None:
        """Draw north arrow indicator at top-right.
        
        Args:
            painter: QPainter instance
            vw: Viewport width
            vh: Viewport height
        """
        margin = 16
        stem_len = 34
        head = 10
        
        # Position arrow head within borders
        x = vw - (margin + head + 8)   # right inset and left shift
        y = margin + head              # top inset
        
        pen = QPen(QColor("#1f77b4"), 2)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(pen)
        
        # Draw stem
        painter.drawLine(x, y + stem_len, x, y)
        
        # Draw arrow head
        painter.drawLine(x - head, y + head, x, y)
        painter.drawLine(x + head, y + head, x, y)
        
        # Draw label "N"
        font = QFont()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(int(x + head + 8), int(y + 6), "N")
    
    @staticmethod
    def _draw_diagnostics_panel(painter: QPainter, overlay_data: Dict[str, Any],
                               grid_w_m: float, grid_h_m: float) -> None:
        """Draw diagnostics panel at top-left corner.
        
        Args:
            painter: QPainter instance
            overlay_data: Dictionary with perimeter, area, coverage, posts, gutters data
            grid_w_m: Grid width in meters
            grid_h_m: Grid height in meters
        """
        lines = []
        
        # Basic measurements
        perim = overlay_data.get("perimeter_m")
        area = overlay_data.get("area_m2")
        
        lines.append(f"Perimeter: {GeometryHelper.format_measure(perim)}")
        lines.append(f"Polygon area: {GeometryHelper.format_area(area)}")
        
        # Coverage data
        cov = overlay_data.get("coverage") or {}
        if cov:
            full_c = cov.get('full_count', 0)
            full_a = cov.get('full_area_m2', 0.0)
            parts = cov.get('partial_details', []) or []
            part_a = sum((p.get('area_m2', 0.0) for p in parts))
            
            lines.append(f"Full boxes: {full_c} (area {GeometryHelper.format_area(full_a)})")
            lines.append(f"Partial boxes: {len(parts)} (area {GeometryHelper.format_area(part_a)})")
            lines.append(f"Full+Partial area: {GeometryHelper.format_area(full_a + part_a)}")
            lines.append(f"Grid: {grid_w_m:g} m × {grid_h_m:g} m")
        
        # Posts data
        posts = overlay_data.get("posts") or {}
        if posts:
            lines.append("")
            lines.append("Posts (3x5 with sides):")
            lines.append(f"North width: {GeometryHelper.format_measure(posts.get('north_width_m', 0.0))}")
            lines.append(f"Depth: {GeometryHelper.format_measure(posts.get('depth_m', 0.0))}")
            lines.append(f"Rows: {posts.get('rows', 0)} | full/row: {posts.get('full_triangles_per_row', 0)} | half/row: {int(posts.get('has_half_triangle_per_row', 0))}")
            lines.append(f"Low posts total: {posts.get('total_low_posts', 0)} | Tall posts total: {posts.get('total_tall_posts', 0)}")
        
        # Gutters data
        gut = overlay_data.get("gutters") or {}
        if gut:
            lines.append("")
            lines.append("Gutters:")
            lines.append(f"Width: {GeometryHelper.format_measure(gut.get('north_width_m', 0.0))} | Depth: {GeometryHelper.format_measure(gut.get('depth_m', 0.0))}")
            lines.append(f"Module: {GeometryHelper.format_measure(gut.get('module_w_m', 0.0))} (2×grid_w)")
            lines.append(f"Vertical lines: {gut.get('lines_x', 0)} | Piece: {GeometryHelper.format_measure(gut.get('piece_len_m', 0.0))}")
            lines.append(f"Total pieces: {gut.get('total_pieces', 0)} | Total len: {GeometryHelper.format_measure(gut.get('total_length_m', 0.0))}")
        
        # Draw text panel
        font = QFont("Monospace", 9)
        painter.setFont(font)
        painter.setPen(QPen(QColor(0, 0, 0, 200)))
        
        x_offset = 12
        y_offset = 20
        line_height = 14
        
        for i, line in enumerate(lines):
            painter.drawText(x_offset, y_offset + i * line_height, line)
