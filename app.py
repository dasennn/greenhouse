import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QGraphicsSimpleTextItem, QInputDialog, QToolBar
)
from PySide6.QtGui import QPainter, QPen, QColor, QAction, QPainterPath, QCursor
from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtCore import Qt, QPointF, QRectF

class DrawingView(QGraphicsView):
    def __init__(self):
        super().__init__()
        # Scene setup
        self.scene = QGraphicsScene(-2000, -2000, 4000, 4000, self)
        self.setScene(self.scene)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

        # Drawing state
        self.points = []
        self.free_mode = False
        self.scale_factor = 100  # pixels per meter
        self.grid_meters = 0.1   # default grid spacing in meters
        self.grid_size = self.grid_meters * self.scale_factor
        self.history = []
        self.future = []

        # Panning state
        self._panning = False
        self._pan_start = QPointF()

        # Snapping tolerance
        self.snap_tol = 10

        # Graphics items: open polyline
        pen = QPen(QColor("green"), 2)
        self.path_item = QGraphicsPathItem()
        self.path_item.setPen(pen)
        self.path_item.setZValue(0)
        self.scene.addItem(self.path_item)
        self.length_items = []

    def drawBackground(self, painter: QPainter, rect: QRectF):
        pen = QPen(QColor(220, 220, 220), 1)
        painter.setPen(pen)
        left = int(rect.left() / self.grid_size) * self.grid_size
        top = int(rect.top() / self.grid_size) * self.grid_size
        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += self.grid_size
        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += self.grid_size

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    def increase_grid(self):
        self.grid_meters += 0.1
        self.grid_size = self.grid_meters * self.scale_factor
        self.viewport().update()

    def decrease_grid(self):
        self.grid_meters = max(0.1, self.grid_meters - 0.1)
        self.grid_size = self.grid_meters * self.scale_factor
        self.viewport().update()

    def change_grid(self):
        meters, ok = QInputDialog.getDouble(
            self, "Grid Spacing", "Enter grid spacing (meters):",
            self.grid_meters, 0.01, 100.0, 2
        )
        if ok:
            self.grid_meters = meters
            self.grid_size = self.grid_meters * self.scale_factor
            self.viewport().update()

    def toggle_free_mode(self, enabled: bool):
        self.free_mode = enabled

    def save_state(self):
        self.history.append(list(self.points))
        self.future.clear()

    def undo(self):
        if not self.history:
            return
        self.future.append(list(self.points))
        self.points = self.history.pop()
        self._refresh()

    def redo(self):
        if not self.future:
            return
        self.history.append(list(self.points))
        self.points = self.future.pop()
        self._refresh()

    def clear(self):
        self.save_state()
        self.points = []
        self._refresh()

    def _refresh(self):
        path = QPainterPath()
        if self.points:
            path.moveTo(self.points[0])
            for p in self.points[1:]:
                path.lineTo(p)
        self.path_item.setPath(path)
        for item in self.length_items:
            self.scene.removeItem(item)
        self.length_items.clear()
        for i in range(1, len(self.points)):
            self._add_length_label(self.points[i-1], self.points[i])

    def snap_to_grid(self, pos: QPointF) -> QPointF:
        x = round(pos.x() / self.grid_size) * self.grid_size
        y = round(pos.y() / self.grid_size) * self.grid_size
        return QPointF(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            pt = self.snap_to_grid(scene_pos)
            if self.points:
                last = self.points[-1]
                if not self.free_mode:
                    dx = pt.x() - last.x()
                    dy = pt.y() - last.y()
                    if abs(dx) > abs(dy):
                        pt = QPointF(pt.x(), last.y())
                    else:
                        pt = QPointF(last.x(), pt.y())
            self.save_state()
            self.points.append(pt)
            self._refresh()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CrossCursor)
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_Z:
                self.undo()
                return
            elif event.key() == Qt.Key_Y:
                self.redo()
                return
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.increase_grid()
            return
        if event.key() == Qt.Key_Minus:
            self.decrease_grid()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.points:
            self.prompt_length_input()
            return
        super().keyPressEvent(event)

    def prompt_length_input(self):
        length, ok = QInputDialog.getDouble(
            self, "Segment Length", "Enter length (meters):",
            1.0, 0.01, 10000.0, 2
        )
        if not ok:
            return
        last = self.points[-1]
        # determine direction by mouse pointer
        cursor_pos = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        vec_x = cursor_pos.x() - last.x()
        vec_y = cursor_pos.y() - last.y()
        if self.free_mode:
            norm = (vec_x**2 + vec_y**2)**0.5
            if norm == 0:
                return
            ux, uy = vec_x/norm, vec_y/norm
        else:
            if abs(vec_x) > abs(vec_y):
                ux, uy = 1 if vec_x>0 else -1, 0
            else:
                ux, uy = 0, 1 if vec_y>0 else -1
        pt = QPointF(last.x() + ux*length*self.scale_factor,
                     last.y() + uy*length*self.scale_factor)
        pt = self.snap_to_grid(pt)
        self.save_state()
        self.points.append(pt)
        self._refresh()

    def _add_length_label(self, p1: QPointF, p2: QPointF):
        dist_px = ((p2.x() - p1.x())**2 + (p2.y() - p1.y())**2)**0.5
        dist_m = dist_px / self.scale_factor
        mid = QPointF((p1.x()+p2.x())/2, (p1.y()+p2.y())/2)
        label = QGraphicsSimpleTextItem(f"{dist_m:.2f} m")
        label.setPos(mid)
        label.setZValue(1)
        self.scene.addItem(label)
        self.length_items.append(label)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Greenhouse Estimator")
        self.view = DrawingView()
        self.setCentralWidget(self.view)
        self.resize(800, 600)

        toolbar = QToolBar("Tools", self)
        self.addToolBar(toolbar)
        free_action = QAction("Free Draw", self)
        free_action.setCheckable(True)
        free_action.toggled.connect(self.view.toggle_free_mode)
        toolbar.addAction(free_action)
        undo_action = QAction("Undo", self)
        undo_action.triggered.connect(self.view.undo)
        toolbar.addAction(undo_action)
        redo_action = QAction("Redo", self)
        redo_action.triggered.connect(self.view.redo)
        toolbar.addAction(redo_action)
        clear_action = QAction("Clear All", self)
        clear_action.triggered.connect(self.view.clear)
        toolbar.addAction(clear_action)
        grid_action = QAction("Grid Spacing", self)
        grid_action.triggered.connect(self.view.change_grid)
        toolbar.addAction(grid_action)
        inc_action = QAction("Grid+", self)
        inc_action.triggered.connect(self.view.increase_grid)
        toolbar.addAction(inc_action)
        dec_action = QAction("Grid-", self)
        dec_action.triggered.connect(self.view.decrease_grid)
        toolbar.addAction(dec_action)
        close_action = QAction("Close Perimeter", self)
        def close_perimeter():
            if len(self.view.points) >= 3:
                self.view.save_state()
                self.view.points.append(self.view.points[0])
                self.view._refresh()
        close_action.triggered.connect(close_perimeter)
        toolbar.addAction(close_action)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
