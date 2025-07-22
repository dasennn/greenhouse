from PySide6.QtWidgets import QMainWindow, QToolBar
from PySide6.QtGui import QAction
from .drawing_view import DrawingView

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Greenhouse Estimator")
        self.view = DrawingView()
        self.setCentralWidget(self.view)
        self.resize(800, 600)
        self._create_toolbar()

    def _create_toolbar(self):
        toolbar = QToolBar("Tools", self)
        self.addToolBar(toolbar)

        # Core actions: (label, handler, is_checkable)
        actions = [
            ("Free Draw",       self.view.toggle_free_mode,  True),
            ("Undo",            self.view.undo,              False),
            ("Redo",            self.view.redo,              False),
            ("Clear All",       self.view.clear,             False),
            ("Grid Spacing",    self.view.change_grid,       False),
            ("Grid+",           self.view.increase_grid,     False),
            ("Grid-",           self.view.decrease_grid,     False),
            ("Close Perimeter", self._close_perimeter,       False),
        ]
        for text, handler, checkable in actions:
            act = QAction(text, self)
            if checkable:
                act.setCheckable(True)
                act.toggled.connect(handler)
            else:
                act.triggered.connect(handler)
            toolbar.addAction(act)

        # Guide Lines toggle
        guide_act = QAction("Guide Lines", self)
        guide_act.setCheckable(True)
        guide_act.toggled.connect(self.view.toggle_guide_mode)
        toolbar.addAction(guide_act)

        # Erase Guides button
        erase_act = QAction("Erase Guides", self)
        erase_act.triggered.connect(self.view.erase_guides)
        toolbar.addAction(erase_act)

    def _close_perimeter(self):
        if len(self.view.points) >= 3:
            self.view.save_perimeter_state()
            # close the loop
            self.view.points.append(self.view.points[0])
            self.view._refresh()
