
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar
from PySide6.QtCore import Qt
from ui.drawing_view import DrawingView
from PySide6.QtGui import QAction, QActionGroup

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Greenhouse Estimator")
        self.view = DrawingView(self)
        self.setCentralWidget(self.view)
        self.resize(1024, 768)
        self._create_toolbar()

    def _create_toolbar(self):
        toolbar = QToolBar("Tools", self)
        self.addToolBar(toolbar)

        # OSnap toggle
        osnap_act = QAction("OSnap", self)
        osnap_act.setCheckable(True)
        osnap_act.setChecked(True)
        osnap_act.toggled.connect(self.view.toggle_osnap_mode)
        toolbar.addAction(osnap_act)
        toolbar.addSeparator()

        # Exclusive modes
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)
        modes = [
            ("Pointer",     self.view.toggle_pointer_mode),
            ("Polyline",    self.view.toggle_polyline_mode),
            ("Guide Lines", self.view.toggle_guide_mode),
            ("Hand Pan",    self.view.toggle_pan_mode),
        ]
        for label, handler in modes:
            act = QAction(label, self)
            act.setObjectName(label)
            act.setCheckable(True)
            act.toggled.connect(handler)
            toolbar.addAction(act)
            mode_group.addAction(act)
        mode_group.actions()[0].setChecked(True)
        toolbar.addSeparator()

        # Other tools
        tools = [
            ("Undo",            self.view.undo,            "Ctrl+Z"),
            ("Redo",            self.view.redo,            "Ctrl+Y"),
            ("Delete",          self.view.delete_selected, "Del"),
            ("Clear All",       self.view.clear_all,       None),
            ("Grid Spacing",    self.view.change_grid,     None),
            ("Grid+",           self.view.increase_grid,   "="),
            ("Grid-",           self.view.decrease_grid,   "-"),
            ("Close Perimeter", self._close_perimeter,     None),
            ("Erase Guides", self.view.clear_guides, None),
        ]
        for label, handler, shortcut in tools:
            act = QAction(label, self)
            act.setObjectName(label)
            if shortcut:
                act.setShortcut(shortcut)
            act.triggered.connect(handler)
            toolbar.addAction(act)

    def _close_perimeter(self):
        if len(self.view.points) >= 3:
            self.view.save_state()
            self.view.points.append(self.view.points[0])
            self.view._refresh_perimeter()
