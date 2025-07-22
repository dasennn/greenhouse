from PySide6.QtCore import QPointF

def snap_to_grid(pos: QPointF, grid_size: float) -> QPointF:
    x = round(pos.x() / grid_size) * grid_size
    y = round(pos.y() / grid_size) * grid_size
    return QPointF(x, y)

# You can add geometry utilities here (distance, area, intersections, etc.)
