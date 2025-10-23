"""Perimeter management module for drawing view.

This module handles all perimeter-related functionality:
- Drawing perimeter lines and points
- Managing draggable points
- Showing dimension labels
- Refreshing graphics items
"""

import math
from typing import List
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsLineItem,
    QGraphicsSimpleTextItem,
    QGraphicsItem,
)
from PySide6.QtGui import QPen, QColor
from PySide6.QtCore import QPointF

from ui.drawing_state import DrawingState
from ui.draggable_point import DraggablePoint


class PerimeterManager:
    """Manages perimeter rendering and interaction."""
    
    def __init__(self, scene: QGraphicsScene, state: DrawingState, scale_factor: float, view=None):
        """Initialize perimeter manager.
        
        Args:
            scene: QGraphicsScene to add items to
            state: DrawingState containing points data
            scale_factor: Pixels per meter conversion factor
            view: Reference to parent DrawingView (needed for DraggablePoint)
        """
        self.scene = scene
        self.state = state
        self.scale_factor = scale_factor
        self.view = view
        
        # Graphics items lists
        self.perim_items: List[QGraphicsLineItem] = []
        self.point_items: List[DraggablePoint] = []
        self.length_items: List[QGraphicsSimpleTextItem] = []
        
        # Highlight state
        self._highlighted_item = None
        self._original_pen = None
    
    def refresh_perimeter(self):
        """Redraw the entire perimeter with points and dimension labels."""
        # Clear existing items
        self._clear_highlight()
        for ln in self.perim_items:
            self.scene.removeItem(ln)
        for lbl in self.length_items:
            self.scene.removeItem(lbl)
        for dot in self.point_items:
            self.scene.removeItem(dot)
        
        self.perim_items.clear()
        self.length_items.clear()
        self.point_items.clear()
        
        # Ελέγχουμε αν υπάρχουν facade segments (μετά το κλείσιμο)
        facade_segments = getattr(self.state, 'facade_segments', [])
        use_colors = (
            self.state.perimeter_locked
            and getattr(self.state, 'show_facade_colors', False)
            and len(facade_segments) > 0
        )
        
        # Δημιουργούμε map για γρήγορη αναζήτηση
        facade_map = {}
        if use_colors:
            for seg in facade_segments:
                idx = seg.get("index", -1)
                facade_map[idx] = seg
        
        # Draw new items
        breaks = set(getattr(self.state, 'breaks', []) or [])
        for i, pt in enumerate(self.state.points):
            # Add draggable point
            dot = DraggablePoint(self.view, i, pt)
            self.scene.addItem(dot)
            self.point_items.append(dot)

            # Add line segment if not first point and not a break between (i-1) and i
            if i > 0 and (i - 1) not in breaks:
                p0 = self.state.points[i - 1]
                ln = QGraphicsLineItem(p0.x(), p0.y(), pt.x(), pt.y())
                
                # Χρωματισμός με βάση προσανατολισμό (αν υπάρχει)
                color = QColor("green")
                width = 2
                if use_colors and (i - 1) in facade_map:
                    seg_color = facade_map[i - 1].get("color", "#00FF00")
                    color = QColor(seg_color)
                    width = 3
                
                ln.setPen(QPen(color, width))
                ln.setFlag(QGraphicsItem.ItemIsSelectable, True)
                self.scene.addItem(ln)
                self.perim_items.append(ln)

                # Add dimension label
                dist = math.hypot(pt.x() - p0.x(), pt.y() - p0.y()) / self.scale_factor
                mid = QPointF((p0.x() + pt.x()) / 2, (p0.y() + pt.y()) / 2)
                lbl = QGraphicsSimpleTextItem(f"{dist:.2f} m")
                lbl.setPos(mid)
                lbl.setZValue(1)
                self.scene.addItem(lbl)
                self.length_items.append(lbl)
    
    def highlight_segment(self, index: int):
        """Τονίζει ένα segment."""
        self._clear_highlight()
        
        if 0 <= index < len(self.perim_items):
            item = self.perim_items[index]
            self._original_pen = item.pen()
            self._highlighted_item = item
            
            # Κίτρινο χοντρό pen
            highlight_pen = QPen(QColor("#FFEB3B"), 5)
            item.setPen(highlight_pen)
            item.setZValue(10)
    
    def _clear_highlight(self):
        """Καθαρισμός highlight."""
        if self._highlighted_item and self._original_pen:
            self._highlighted_item.setPen(self._original_pen)
            self._highlighted_item.setZValue(0)
        self._highlighted_item = None
        self._original_pen = None
    
    def clear(self):
        """Remove all perimeter graphics items from scene."""
        for ln in self.perim_items:
            self.scene.removeItem(ln)
        for lbl in self.length_items:
            self.scene.removeItem(lbl)
        for dot in self.point_items:
            self.scene.removeItem(dot)
        
        self.perim_items.clear()
        self.length_items.clear()
        self.point_items.clear()
    
    def delete_point_by_item(self, item) -> bool:
        """Delete a point by its graphics item.
        
        Args:
            item: The graphics item (DraggablePoint or line segment)
        
        Returns:
            True if point was deleted, False otherwise
        """
        if item in self.point_items or item in self.perim_items:
            if item in self.point_items:
                idx = self.point_items.index(item)
            else:
                idx = self.perim_items.index(item) + 1
            
            # If the perimeter is closed (first == last) and we're deleting
            # the first point (idx == 0), also remove the duplicate closing
            # point at the end of the list so the polygon remains consistent.
            try:
                was_closed = len(self.state.points) > 1 and (self.state.points[0] == self.state.points[-1])
            except Exception:
                was_closed = False

            # Delete the requested index
            del self.state.points[idx]

            # Update subpath breaks to reflect the deletion
            try:
                new_breaks = []
                for b in list(getattr(self.state, 'breaks', []) or []):
                    # If the break is exactly at the removed edge boundary, drop it
                    if b == idx or b == idx - 1:
                        continue
                    # Shift breaks after the deleted index
                    if b > idx:
                        nb = b - 1
                    else:
                        nb = b
                    # Keep only valid break positions (between 0 and len(points)-2)
                    if 0 <= nb <= len(self.state.points) - 2:
                        new_breaks.append(nb)
                # De-duplicate and sort
                self.state.breaks = sorted(set(new_breaks))
            except Exception:
                try:
                    self.state.breaks = [b for b in getattr(self.state, 'breaks', []) if 0 <= b <= len(self.state.points) - 2]
                except Exception:
                    pass

            # If it was closed and we removed the original first point,
            # remove the trailing duplicate closing point (if any).
            if was_closed and idx == 0 and self.state.points:
                # After removing index 0 from [p0, p1, ..., p0] we get
                # [p1, ..., p0] where the last element is the old duplicate.
                # Remove it to produce [p1, ...].
                try:
                    self.state.points.pop()
                except Exception:
                    pass

            self.state.save_state()
            self.refresh_perimeter()
            return True
        return False
    
    def get_point_index(self, item) -> int:
        """Get the index of a point in the state.points list.
        
        Args:
            item: The DraggablePoint graphics item
        
        Returns:
            Index in state.points, or -1 if not found
        """
        if item in self.point_items:
            return self.point_items.index(item)
        return -1
