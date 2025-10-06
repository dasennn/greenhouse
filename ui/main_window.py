from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QMainWindow, QMessageBox, QToolBar, QComboBox
from services.models import Estimator, MaterialItem
from ui.drawing_view import DrawingView
from PySide6.QtGui import QAction, QActionGroup
from ui.column_height_dialog import ColumnHeightDialog
from services.geometry_utils import compute_grid_coverage as geom_compute_grid_coverage

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

        # Greenhouse type / grid selector
        self.grid_selector = QComboBox(self)
        self.grid_selector.setObjectName("GreenhouseTypeSelector")
        # Presets: label -> (grid_w_m, grid_h_m)
        self._grid_presets = {
            "3x5 with sides (5x3 m)": (5.0, 3.0),
            "5x4 (5x4 m)": (5.0, 4.0),
            "4x4 (4x4 m)": (4.0, 4.0),
            "Custom…": None,
        }
        for label in self._grid_presets.keys():
            self.grid_selector.addItem(label)
        # Set default to 5x3
        self.grid_selector.setCurrentIndex(0)
        self.grid_selector.currentTextChanged.connect(self._on_grid_selector_changed)
        toolbar.addWidget(self.grid_selector)

    def _on_grid_selector_changed(self, text: str):
        preset = self._grid_presets.get(text)
        if preset is None:
            # Custom dimensions
            try:
                w, ok_w = ColumnHeightDialog.getDouble(self, "Custom Grid Width", "Width of one grid box (m):", value=self.view.grid_w_m, min=0.1, max=100.0, decimals=2)
            except Exception:
                # Fallback to QInputDialog if ColumnHeightDialog doesn't provide getDouble
                from PySide6.QtWidgets import QInputDialog
                w, ok_w = QInputDialog.getDouble(self, "Custom Grid Width", "Width of one grid box (m):", value=self.view.grid_w_m, min=0.1, max=100.0, decimals=2)
            if not ok_w:
                # Revert selection to previous (5x3)
                self.grid_selector.blockSignals(True)
                self.grid_selector.setCurrentIndex(0)
                self.grid_selector.blockSignals(False)
                return
            try:
                h, ok_h = ColumnHeightDialog.getDouble(self, "Custom Grid Height", "Height of one grid box (m):", value=self.view.grid_h_m, min=0.1, max=100.0, decimals=2)
            except Exception:
                from PySide6.QtWidgets import QInputDialog
                h, ok_h = QInputDialog.getDouble(self, "Custom Grid Height", "Height of one grid box (m):", value=self.view.grid_h_m, min=0.1, max=100.0, decimals=2)
            if not ok_h:
                self.grid_selector.blockSignals(True)
                self.grid_selector.setCurrentIndex(0)
                self.grid_selector.blockSignals(False)
                return
            self.view.grid_w_m = float(w)
            self.view.grid_h_m = float(h)
        else:
            gw, gh = preset
            self.view.grid_w_m = float(gw)
            self.view.grid_h_m = float(gh)
        # Update view state and refresh drawing
        self.view.greenhouse_type = "3x5_with_sides"  # keep current logic; pattern depends only on grid size for now
        try:
            self.view.viewport().update()
        except Exception:
            pass

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

    def _on_perimeter_closed(self, points, perimeter_m, area_m2, partial_details):
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

        # Compute grid coverage summary (full + partial areas)
        try:
            coverage = geom_compute_grid_coverage(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
            )
        except Exception:
            coverage = None

        if coverage:
            poly_area = coverage['polygon_area_m2']
            full_count = coverage['full_count']
            full_area = coverage['full_area_m2']
            partials = coverage['partial_details']
            partial_count = len(partials)
            partial_area = sum(p['area_m2'] for p in partials)

            msg = (
                f"Perimeter: {perimeter_m:.2f} m\n"
                f"Polygon area: {poly_area:.3f} m²\n"
                f"Full boxes: {full_count} (area {full_area:.3f} m²)\n"
                f"Partial boxes: {partial_count} (area {partial_area:.3f} m²)\n"
                f"Sum full+partial area: {(full_area + partial_area):.3f} m²\n"
                f"Grid size: {getattr(self.view, 'grid_w_m', 5.0):g}m x {getattr(self.view, 'grid_h_m', 3.0):g}m\n"
            )
            if partials:
                msg += "\nPartial Box Details:\n"
                for p in partials:
                    msg += f"  Grid {p['grid']}: {p['area_m2']:.3f} m², perimeter inside = {p.get('boundary_length_m', 0.0):.3f} m\n"
        else:
            # Fallback: show minimal info
            msg = (
                f"Perimeter: {perimeter_m:.2f} m\n"
                f"Area: {area_m2:.2f} m²\n"
                f"Partial (cut) grid boxes: {len(partial_details)}\n"
                f"Grid size: {getattr(self.view, 'grid_w_m', 5.0):g}m x {getattr(self.view, 'grid_h_m', 3.0):g}m\n"
            )
            if partial_details:
                msg += "\nPartial Box Details:\n"
                for pd in partial_details:
                    grid = pd['grid']
                    area_px2 = pd['intersection_area']
                    sf = self.view.scale_factor
                    area_m2 = area_px2 / (sf * sf) if sf and sf != 0 else 0.0
                    msg += f"  Grid {grid}: Area inside = {area_m2:.3f} m²\n"

        # Only show a short summary in the status bar here; the detailed popup is shown
        # by DrawingView when the perimeter is closed. Print full details to console for
        # debugging/history so we don't pop a second modal dialog.
        try:
            summary = f"Perimeter closed: {perimeter_m:.2f} m, area {poly_area:.3f} m², full+partial {(full_area + partial_area):.3f} m²"
        except Exception:
            summary = f"Perimeter closed: {perimeter_m:.2f} m, area {area_m2:.3f} m²"
        # show brief message in status bar for a short time
        try:
            self.statusBar().showMessage(summary, 8000)
        except Exception:
            # if no status bar, quietly ignore (don't print to console)
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