"""Drawing view state management."""

from PySide6.QtCore import QPointF
from typing import List, Tuple, Optional


class DrawingState:
    """Manages the state of the drawing view."""
    
    def __init__(self):
        # Drawing state
        self.points: List[QPointF] = []
        self.guides: List[Tuple[QPointF, QPointF]] = []
        # Indices in points after which a break exists (no segment between i and i+1)
        # Example: if 3 is in breaks, there is no edge between points[3] and points[4]
        self.breaks: List[int] = []
        # If True, the next click in polyline mode starts a new chain (separate subpath)
        self.start_new_chain_pending: bool = False
        self.perimeter_locked = False
        
        # Mode flags
        self.pointer_enabled = True
        self.polyline_enabled = False
        self.guide_enabled = False
        self.pan_enabled = False
        self.free_mode = False
        self.osnap_enabled = True
        
        # Temporary state
        self._guide_start: Optional[QPointF] = None
        self._panning = False
        self._pan_start = QPointF()
        self._dim_input = ""
        self.last_mouse_scene = QPointF()
        
        # History for undo/redo
        self.history = []
        self.future = []
        
        # Overlay data
        self._overlay_data = None
        self.show_overlay = False
        
        # Facade orientation data (μετά το κλείσιμο περιμέτρου)
        self.facade_segments: List[dict] = []
        # Εμφάνιση χρωμάτων προσανατολισμού μόνο κατ' επιλογή (κουμπί "Προσανατολισμός Πλευρών")
        self.show_facade_colors: bool = False
    
    def save_state(self):
        """Save current state for undo/redo."""
        state = {
            "points": list(self.points),
            "guides": list(self.guides),
            "breaks": list(self.breaks),
            "start_new_chain_pending": bool(self.start_new_chain_pending),
            "facade_segments": list(self.facade_segments),
        }
        self.history.append(state)
        self.future.clear()
    
    def restore_state(self, state):
        """Restore state from history."""
        self.points = list(state["points"])
        self.guides = list(state["guides"])
        self.breaks = list(state.get("breaks", []))
        self.start_new_chain_pending = bool(state.get("start_new_chain_pending", False))
        self.facade_segments = list(state.get("facade_segments", []))
    
    def can_undo(self) -> bool:
        return len(self.history) >= 2
    
    def can_redo(self) -> bool:
        return len(self.future) > 0
    
    def undo(self):
        """Undo last action."""
        if not self.can_undo():
            return None
        self.future.append(self.history.pop())
        return self.history[-1]
    
    def redo(self):
        """Redo last undone action."""
        if not self.can_redo():
            return None
        state = self.future.pop()
        self.history.append(state)
        return state
    
    def clear(self):
        """Clear all drawing state."""
        self.points.clear()
        self.guides.clear()
        self.breaks.clear()
        self.start_new_chain_pending = False
        self.perimeter_locked = False
        self._guide_start = None
        self._dim_input = ""
        self._overlay_data = None
        self.facade_segments.clear()
        self.show_facade_colors = False
