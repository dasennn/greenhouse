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
    
    def refresh_perimeter(self):
        """Redraw the entire perimeter with points and dimension labels."""
        # Clear existing items
        for ln in self.perim_items:
            self.scene.removeItem(ln)
        for lbl in self.length_items:
            self.scene.removeItem(lbl)
        for dot in self.point_items:
            self.scene.removeItem(dot)
        
        self.perim_items.clear()
        self.length_items.clear()
        self.point_items.clear()
        
        # Draw new items
        for i, pt in enumerate(self.state.points):
            # Add draggable point
            dot = DraggablePoint(self.view, i, pt)
            self.scene.addItem(dot)
            self.point_items.append(dot)
            
            # Add line segment if not first point
            if i > 0:
                p0 = self.state.points[i - 1]
                ln = QGraphicsLineItem(p0.x(), p0.y(), pt.x(), pt.y())
                ln.setPen(QPen(QColor("green"), 2))
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
