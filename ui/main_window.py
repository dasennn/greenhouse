from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QMainWindow, QMessageBox, QToolBar
from services.models import Estimator, MaterialItem
from ui.drawing_view import DrawingView
from PySide6.QtGui import QAction, QActionGroup
from ui.column_height_dialog import ColumnHeightDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Set light mode palette
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(255, 255, 255))
        palette.setColor(QPalette.WindowText, QColor(0, 0, 0))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(240, 240, 240))
        palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
        palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
        palette.setColor(QPalette.Text, QColor(0, 0, 0))
        palette.setColor(QPalette.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ButtonText, QColor(0, 0, 0))
        palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.Highlight, QColor(0, 120, 215))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.setPalette(palette)

        self.resize(1024, 768)

        # Lazy-created estimator (connected to backend/services if available)
        self.estimator = None

        self.view = DrawingView(self)
        self.setCentralWidget(self.view)
        self.resize(1024, 768)
        self.estimator = None  # lazy-created when needed
        self.large_column_height = None
        self.small_column_height = None
        self._create_toolbar()
        self.view.perimeter_closed.connect(self._on_perimeter_closed)

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

        # Add a toolbar action to open the column height dialog
        column_height_action = QAction("Set Column Heights", self)
        column_height_action.triggered.connect(self._set_column_heights)
        toolbar.addAction(column_height_action)

    def _ensure_estimator(self):
        """Create an Estimator once, if available. Returns the instance or None."""
        if getattr(self, "estimator", None) is not None:
            return self.estimator
        if Estimator is None or MaterialItem is None:
            self.estimator = None
            return None
        try:
            # TODO: load real materials/prices from config or file. Keep empty for now.
            materials = {}
            self.estimator = Estimator(materials=materials, scale_factor=self.view.scale_factor)
        except Exception:
            self.estimator = None
        return self.estimator

    def _close_perimeter(self):
        self.view.close_perimeter()

    def _on_perimeter_closed(self, points, perimeter_m, area_m2, full_grid_boxes, partial_grid_boxes):
        # Normalize to list of (x, y) floats and drop duplicated closing point if present
        xy = []
        for p in points:
            try:
                x, y = float(p.x()), float(p.y())
            except AttributeError:
                x, y = float(p[0]), float(p[1])
            xy.append((x, y))
        if len(xy) >= 2 and xy[0] == xy[-1]:
            xy = xy[:-1]

        # Defaults from view
        full = full_grid_boxes
        partial = partial_grid_boxes

        # Only try services.geometry
        _count_boxes = None
        try:
            from services.geometry import count_grid_boxes as _count_boxes
        except Exception:
            _count_boxes = None

        full = partial = None
        if _count_boxes is not None:
            try:
                full, partial = _count_boxes(
                    xy,
                    scale_factor=self.view.scale_factor,
                    grid_w_m=5.0,
                    grid_h_m=3.0,
                )
            except Exception:
                pass

        # Always fallback to local computation if full or partial is None
        if full is None or partial is None:
            try:
                local_full, local_partial = self.view.compute_grid_box_counts(
                    points=xy, grid_w_m=5.0, grid_h_m=3.0, scale_factor=self.view.scale_factor
                )
                if full is None:
                    full = full_grid_boxes if full_grid_boxes is not None else local_full
                if partial is None:
                    partial = local_partial
            except Exception:
                if full is None:
                    full = full_grid_boxes
                if partial is None:
                    partial = 0  # Always set to 0 if cannot compute

        # Show summary dialog to user
        QMessageBox.information(
            self,
            "Perimeter Closed",
            (
            f"Perimeter: {perimeter_m:.2f} m\n"
            f"Area: {area_m2:.2f} m²\n"
            f"Complete grid boxes: {full}\n"
            f"Uncompleted grid boxes: {partial}\n"
            f"Grid size: 5m x 3m"
        )
        )

        # Pass perimeter and grid box info to backend estimator if available
        est = self._ensure_estimator()
        if est is not None:
            try:
                # Pass perimeter points (xy) to backend estimator
                bill = est.compute_bill(xy)
                # bill may include geometry, grid_cells, subtotal, etc.
                # You can use bill.get("grid_cells") to get backend-calculated grid info if needed
            except Exception:
                pass

    def _set_column_heights(self):
        """Open a dialog to set the heights of large and small columns."""
        dialog = ColumnHeightDialog(self)
        if dialog.exec():
            large_height, small_height = dialog.get_values()
            if large_height is not None and small_height is not None:
                self.large_column_height = large_height
                self.small_column_height = small_height
                QMessageBox.information(
                    self,
                    "Column Heights Set",
                    f"Large Column Height: {large_height} m\nSmall Column Height: {small_height} m"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Invalid Input",
                    "Please enter valid numeric values for column heights."
                )