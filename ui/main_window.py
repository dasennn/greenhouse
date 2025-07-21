# ui/main_window.py
from PySide6.QtWidgets import QMainWindow, QGraphicsView, QGraphicsScene, QWidget, QVBoxLayout
from PySide6.QtGui import QPen, QPolygonF
from PySide6.QtCore import Qt, QPointF

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Greenhouse Builder")
        self._pts = []  # list of QPointF

        # Scene & View
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(self.view.renderHints() | Qt.Antialiasing)
        self.view.setDragMode(QGraphicsView.NoDrag)

        # Layout
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.view)
        self.setCentralWidget(container)

    def mousePressEvent(self, event):
        # Map window click to scene coords
        if event.button() == Qt.LeftButton:
            pos = self.view.mapToScene(event.pos())
            self._pts.append(QPointF(pos))
            self._redraw_polygon()

    def _redraw_polygon(self):
        self.scene.clear()
        pen = QPen(Qt.blue, 2)
        if len(self._pts) > 1:
            poly = QPolygonF(self._pts)
            self.scene.addPolygon(poly, pen)
        # Draw points
        for p in self._pts:
            self.scene.addEllipse(p.x()-2, p.y()-2, 4, 4, pen)

    # (Later: add keyPressEvent for undo, right-click to close polygon, etc.)
