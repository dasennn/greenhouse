"""Draggable point graphics item for drawing view."""

from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt


class DraggablePoint(QGraphicsEllipseItem):
    """Draggable point for perimeter editing."""
    
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
            new_pos = value
            was_closed = False
            if len(self.view.state.points) > 1:
                try:
                    was_closed = (self.view.state.points[0] == self.view.state.points[-1])
                except Exception:
                    was_closed = False
            self.view.state.points[self.index] = new_pos
            if was_closed:
                if self.index == 0 and len(self.view.state.points) > 1:
                    self.view.state.points[-1] = new_pos
                elif self.index == len(self.view.state.points) - 1 and len(self.view.state.points) > 1:
                    self.view.state.points[0] = new_pos
        return super().itemChange(change, value)
    
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.view.state.save_state()
        self.view._refresh_perimeter()
