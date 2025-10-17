from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QToolBar,
    QComboBox,
    QDockWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QWidget,
    QVBoxLayout,
    QFileDialog,
    QToolButton,
    QMenu,
    QDialog,
    QLineEdit,
    QFormLayout,
    QDialogButtonBox,
    QDoubleSpinBox,
)
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QAction, QActionGroup

from services.estimator import Estimator, default_material_catalog
from services.models import MaterialItem, BillOfMaterials
from services.geometry_utils import (
    compute_grid_coverage as geom_compute_grid_coverage,
    estimate_triangle_posts_3x5_with_sides,
    estimate_gutters_length,
)
from ui.drawing_view import DrawingView
from ui.column_height_dialog import ColumnHeightDialog
from ui.delegates import PriceOnlyDelegate

from pathlib import Path
import csv
import json

PROJECT_EXT = ".ghp"


class NewProjectDialog(QDialog):
    """Dialog to create a new project: asks for name and greenhouse type (grid)."""
    def __init__(self, parent=None, presets: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Νέα Μελέτη")
        self._presets = presets or {}

        form = QFormLayout(self)

        # Type (grid preset)
        self.type_combo = QComboBox(self)
        labels = list(self._presets.keys()) if self._presets else []
        for lbl in labels:
            self.type_combo.addItem(lbl)
        if labels:
            self.type_combo.setCurrentIndex(0)
        form.addRow("Τύπος θερμοκηπίου:", self.type_combo)

        # Custom grid inputs (hidden unless 'Προσαρμοσμένο…')
        self.spin_w = QDoubleSpinBox(self)
        self.spin_w.setRange(0.1, 100.0)
        self.spin_w.setDecimals(2)
        self.spin_w.setValue(5.0)
        self.spin_h = QDoubleSpinBox(self)
        self.spin_h.setRange(0.1, 100.0)
        self.spin_h.setDecimals(2)
        self.spin_h.setValue(3.0)
        form.addRow("Πλάτος κελιού (m):", self.spin_w)
        form.addRow("Ύψος κελιού (m):", self.spin_h)

        # Toggle visibility based on selection
        def on_type_changed(_):
            sel = self.type_combo.currentText()
            is_custom = (sel.strip() == "Προσαρμοσμένο…")
            self.spin_w.setVisible(is_custom)
            self.spin_h.setVisible(is_custom)
            # Optionally prefill custom with selected preset values
            if not is_custom and sel in self._presets and self._presets[sel]:
                gw, gh = self._presets[sel]
                try:
                    self.spin_w.setValue(float(gw))
                    self.spin_h.setValue(float(gh))
                except Exception:
                    pass

        self.type_combo.currentTextChanged.connect(on_type_changed)
        on_type_changed(0)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def get_values(self):
        """Return (type_label, grid_w_m, grid_h_m)."""
        type_label = self.type_combo.currentText()
        w = float(self.spin_w.value())
        h = float(self.spin_h.value())
        return type_label, w, h

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
        self.estimator = None  # lazy-created when needed

        self.view = DrawingView(self)
        self.setCentralWidget(self.view)
        self.large_column_height = None
        self.small_column_height = None
        # Κατάσταση τελευταίας φόρτωσης τιμών από αρχείο
        self._last_loaded_codes = set()
        self._last_loaded_errors = set()
        # Τρέχουσα διαδρομή CSV για αποθήκευση/φόρτωση τιμών
        self._current_csv_path = None
        # Flag για να δείξουμε μήνυμα status μόνο την πρώτη φορά
        self._price_source_announced = False
        # Flag: αν οι τιμές από το τρέχον CSV είναι *εφαρμοσμένες* (όχι απλώς διαθέσιμες ως path)
        # Μπορεί να υπάρχει path αλλά μετά από reset να μην είναι εφαρμοσμένο μέχρι reload.
        self._csv_applied = False
        # Χρήστη προσαρμοσμένες προεπιλογές (αν υπάρχουν) σε config/userdefaults.csv
        self._user_defaults_path = self._user_defaults_csv_path()
        self._user_defaults_active = False
        # Project state
        self._project_path = None
        self._project_name = None
        self._project_defined = False
        self._autosave_timer = None
        self._autosave_path = self._autosave_file_path()
        self._autosave_enabled = True
        self._dirty = False
        # Optional project type label (human-friendly preset label)
        self._project_type_label = None
        # Status bar permanent labels
        try:
            self.status_project_label = QLabel("")
            self.status_type_label = QLabel("")
            self.status_grid_label = QLabel("")
            sb = self.statusBar()
            sb.addPermanentWidget(self.status_project_label)
            sb.addPermanentWidget(self.status_type_label)
            sb.addPermanentWidget(self.status_grid_label)
        except Exception:
            pass
        # Suppress repeated save prompts when user chose "Don't Save" for current changes
        self._suppress_save_prompt = False

        # Menubar and primary UI
        self._create_menubar()
        # Create toolbar first, then docks so toggles can be added
        self._create_toolbar()
        # Create BOM dock then info dock, then stack them on the right
        self._create_bom_dock()
        self._create_info_dock()
        self.view.perimeter_closed.connect(self._on_perimeter_closed)
        self._last_xy = None  # cache last perimeter points for optional recompute
        # Window title
        try:
            self._update_window_title()
        except Exception:
            pass
        # Initial status labels
        try:
            self._update_status_labels()
        except Exception:
            pass
        # Ensure estimator (and user defaults) are loaded immediately at startup
        try:
            self._ensure_estimator()
        except Exception:
            pass

        # Startup prompt is deferred until the window is shown
        self._startup_prompt_scheduled = False

        # Mark project dirty on any geometry change while drawing
        try:
            self.view.geometry_changed.connect(self._mark_dirty)
        except Exception:
            pass

    def _create_toolbar(self):
        self.toolbar = QToolBar("Εργαλεία", self)
        self.addToolBar(self.toolbar)

        # Κατάσταση λειτουργίας (αμοιβαία αποκλειόμενες)
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)
        modes = [
            ("Δείκτης",      self.view.toggle_pointer_mode),
            ("Γραμμή",   self.view.toggle_polyline_mode),
            ("Βοηθητικές",       self.view.toggle_guide_mode),
            ("Μετακίνηση",   self.view.toggle_pan_mode),
        ]
        for label, handler in modes:
            act = QAction(label, self)
            act.setObjectName(label)
            act.setCheckable(True)
            act.toggled.connect(handler)
            self.toolbar.addAction(act)
            mode_group.addAction(act)
        mode_group.actions()[0].setChecked(True)
        self.toolbar.addSeparator()

        # Ορθό (Axis Lock) toggle
        ortho_act = QAction("Ορθό", self)
        ortho_act.setCheckable(True)
        ortho_act.setChecked(False)  # Start with free drawing
        ortho_act.toggled.connect(self._toggle_ortho_mode)
        self.toolbar.addAction(ortho_act)
        self.toolbar.addSeparator()

        # Άλλα εργαλεία
        tools = [
            ("Undo",            self.view.undo,            "Ctrl+Z"),
            ("Redo",           self.view.redo,            "Ctrl+Y"),
            ("Διαγραφή",            self._delete_selected_and_mark_dirty, "Del"),
            ("Διαγραφή Βοηθητικών",     self._clear_guides_and_mark_dirty,    None),
            ("Διαγραφή όλων",       self._clear_all_and_reset, None),
            ("Κλείσιμο Περιμέτρου", self._close_perimeter,     None),            
            ("Zoom στο Σχέδιο",     self._zoom_to_drawing,     "Ctrl+0"),
        ]
        for label, handler, shortcut in tools:
            act = QAction(label, self)
            act.setObjectName(label)
            if shortcut:
                act.setShortcut(shortcut)
            act.triggered.connect(handler)
            self.toolbar.addAction(act)

        # Presets: label -> (grid_w_m, grid_h_m) (kept for New Project dialog and status mapping)
        self._grid_presets = {
            "5x3": (5.0, 3.0),
            "5x4": (5.0, 4.0),
            "4x4": (4.0, 4.0),
            "Προσαρμοσμένο…": None,
        }

        # Διαχείριση Τιμών: ενοποιημένο dropdown (Import, Save, Save As, Reload, Reset)
        self.prices_button = QToolButton(self.toolbar)
        self.prices_button.setText("Τιμές Υλικών")
        self.prices_button.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.prices_button)

        act_import = QAction("Εισαγωγή (CSV)", self)
        act_import.triggered.connect(self._import_prices_csv_dialog)
        menu.addAction(act_import)

        act_save = QAction("Αποθήκευση (CSV)", self)
        act_save.triggered.connect(self._save_prices_csv_as_action)
        menu.addAction(act_save)

        menu.addSeparator()
        act_save_user_defaults = QAction("Ορισμός ως Προεπιλογές Χρήστη", self)
        act_save_user_defaults.triggered.connect(self._save_user_defaults)
        menu.addAction(act_save_user_defaults)

        act_reset = QAction("Επαναφορά Προεπιλογών", self)
        act_reset.triggered.connect(self._reset_prices_to_defaults)
        menu.addAction(act_reset)

        act_factory_reset = QAction("Επαναφορά Εργοστασιακών", self)
        act_factory_reset.triggered.connect(self._factory_reset)
        menu.addAction(act_factory_reset)

        act_restore_backup = QAction("Επαναφορά από Backup", self)
        act_restore_backup.triggered.connect(self._restore_user_defaults_from_backup)
        menu.addAction(act_restore_backup)

        self.prices_button.setMenu(menu)
        self.toolbar.addWidget(self.prices_button)

    def _zoom_to_drawing(self):
        try:
            self.view.zoom_to_drawing()
        except Exception:
            pass

    def _create_bom_dock(self):
        self.bom_dock = QDockWidget("Υλικά & Κόστος", self)
        self.bom_dock.setObjectName("MaterialsCostDock")
        container = QWidget(self.bom_dock)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)

        self.bom_tree = QTreeWidget(container)
        self.bom_tree.setColumnCount(6)
        self.bom_tree.setHeaderLabels(["Είδος", "Μονάδα", "Ποσότητα", "Τιμή Μονάδας", "Υποσύνολο", "Κατάσταση"]) 
        self.bom_tree.setRootIsDecorated(False)
        self.bom_tree.setItemDelegate(PriceOnlyDelegate(self.bom_tree))
        self.bom_tree.itemChanged.connect(self._on_bom_item_changed)
        layout.addWidget(self.bom_tree)

        self.bom_total_label = QLabel("Σύνολο: 0.00 EUR", container)
        layout.addWidget(self.bom_total_label)

        self.price_source_label = QLabel("Αρχείο τιμών: Αρχικές", container)
        self.price_source_label.setObjectName("PriceSourceLabel")
        layout.addWidget(self.price_source_label)

        container.setLayout(layout)
        self.bom_dock.setWidget(container)
        self.addDockWidget(Qt.RightDockWidgetArea, self.bom_dock)
        try:
            toggle_action = self.bom_dock.toggleViewAction()
            toggle_action.setText("Πάνελ Υλικών & Κόστους")
            self.toolbar.addAction(toggle_action)
        except Exception:
            pass

    def _create_info_dock(self):
        self.info_dock = QDockWidget("Στοιχεία Σχεδίου", self)
        self.info_dock.setObjectName("DrawingInfoDock")
        container = QWidget(self.info_dock)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        self.info_tree = QTreeWidget(container)
        self.info_tree.setColumnCount(2)
        self.info_tree.setHeaderLabels(["Πεδίο", "Τιμή"])
        self.info_tree.setRootIsDecorated(False)
        layout.addWidget(self.info_tree)
        container.setLayout(layout)
        self.info_dock.setWidget(container)
        self.addDockWidget(Qt.RightDockWidgetArea, self.info_dock)
        try:
            self.splitDockWidget(self.bom_dock, self.info_dock, Qt.Vertical)
        except Exception:
            pass
        try:
            info_toggle = self.info_dock.toggleViewAction()
            info_toggle.setText("Πάνελ Στοιχείων Σχεδίου")
            self.toolbar.addAction(info_toggle)
        except Exception:
            pass

    def _on_grid_selector_changed(self, text: str):
        preset = self._grid_presets.get(text)
        if preset is None:
            # Custom dimensions
            try:
                w, ok_w = ColumnHeightDialog.getDouble(self, "Πλάτος Κελιού Πλέγματος", "Πλάτος κελιού (m):", value=self.view.grid_w_m, min=0.1, max=100.0, decimals=2)
            except Exception:
                # Fallback to QInputDialog if ColumnHeightDialog doesn't provide getDouble
                from PySide6.QtWidgets import QInputDialog
                w, ok_w = QInputDialog.getDouble(self, "Πλάτος Κελιού Πλέγματος", "Πλάτος κελιού (m):", value=self.view.grid_w_m, min=0.1, max=100.0, decimals=2)
            if not ok_w:
                # Revert selection to previous (5x3)
                self.grid_selector.blockSignals(True)
                self.grid_selector.setCurrentIndex(0)
                self.grid_selector.blockSignals(False)
                return
            try:
                h, ok_h = ColumnHeightDialog.getDouble(self, "Ύψος Κελιού Πλέγματος", "Ύψος κελιού (m):", value=self.view.grid_h_m, min=0.1, max=100.0, decimals=2)
            except Exception:
                from PySide6.QtWidgets import QInputDialog
                h, ok_h = QInputDialog.getDouble(self, "Ύψος Κελιού Πλέγματος", "Ύψος κελιού (m):", value=self.view.grid_h_m, min=0.1, max=100.0, decimals=2)
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
            # Redraw triangles according to new grid
            try:
                self.view.triangle_manager.grid_w_m = self.view.grid_w_m
                self.view.triangle_manager.grid_h_m = self.view.grid_h_m
                if getattr(self.view.state, 'perimeter_locked', False):
                    self.view.triangle_manager.clear_triangles()
                    self.view.triangle_manager.draw_north_triagonals(self.view.state.points)
                    # Also refresh overlay diagnostics (posts/gutters/coverage)
                    self.view.recompute_overlay_if_possible()
            except Exception:
                pass
            self.view.viewport().update()
        except Exception:
            pass
        # Optionally recompute BOM and info if a perimeter exists (using cached xy)
        self._recompute_bom_if_possible()
        self._recompute_info_if_possible()
        # Changing grid is a project-level change
        try:
            self._mark_dirty()
        except Exception:
            pass
        try:
            self._update_status_labels()
        except Exception:
            pass

    def _settings_max_zoom(self):
        """Allow user to change the maximum grid size when zooming out."""
        try:
            from PySide6.QtWidgets import QInputDialog
            current_limit = getattr(self.view, 'max_grid_meters', 500)
            
            # QInputDialog.getDouble signature: (parent, title, label, value, min, max, decimals)
            value, ok = QInputDialog.getDouble(
                self,
                "Μέγιστο Όριο Zoom Out",
                "Μέγιστο μέγεθος πλέγματος κατά το zoom out (μέτρα):\n\n"
                "Όσο μεγαλύτερη η τιμή, τόσο περισσότερο μπορείτε να κάνετε zoom out.\n"
                "Προτεινόμενη τιμή: 500",
                current_limit,  # value
                10,             # min
                10000,          # max
                0               # decimals
            )
            
            if ok:
                self.view.max_grid_meters = float(value)
                self.statusBar().showMessage(f"Το μέγιστο όριο zoom out ορίστηκε σε {value} μέτρα", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία αλλαγής ορίου: {e}")

    def _ensure_estimator(self):
        """Create an Estimator once, if available. Returns the instance or None."""
        if getattr(self, "estimator", None) is not None:
            return self.estimator
        if Estimator is None or MaterialItem is None:
            self.estimator = None
            return None
        try:
            # Δημιουργία estimator με καθαρά defaults (χωρίς αυτόματη φόρτωση CSV)
            self.estimator = Estimator(scale_factor=self.view.scale_factor)
            # Εφαρμογή user defaults εάν υπάρχει αρχείο userdefaults.csv (μόνιμες προσαρμογές χρήστη)
            try:
                user_defs = self._load_user_defaults()
                if user_defs:
                    self.estimator.materials.update(user_defs)
                    self._user_defaults_active = True
            except Exception:
                pass
        except Exception:
            self.estimator = None
        # Ενημέρωση ένδειξης πηγής τιμών
        try:
            self._update_price_source_label()
        except Exception:
            pass
        # Εμφάνιση μηνύματος status για την πηγή τιμών (μόνο την πρώτη φορά)
        if not getattr(self, '_price_source_announced', True):
            try:
                if self._current_csv_path:
                    name = (self._current_csv_path.name
                            if isinstance(self._current_csv_path, Path)
                            else Path(str(self._current_csv_path)).name)
                    self.statusBar().showMessage(f"Φορτώθηκαν τιμές από: {name}", 5000)
                else:
                    self.statusBar().showMessage("Χρήση προεπιλεγμένων τιμών υλικών", 5000)
            except Exception:
                pass
            self._price_source_announced = True
        return self.estimator

    def _toggle_ortho_mode(self, enabled: bool):
        """Toggle orthogonal (axis-locked) drawing mode."""
        self.view.ortho_mode = enabled

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
        # Cache for possible recompute on grid change
        self._last_xy = xy

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
            # Update info dock
            self._update_info_pane({
                "Περίμετρος": f"{perimeter_m:.2f} m",
                "Εμβαδόν Πολυγώνου": f"{poly_area:.3f} m²",
                "Πλήρη Κελιά": f"{full_count} (εμβαδόν {full_area:.3f} m²)",
                "Μερικά Κελιά": f"{partial_count} (εμβαδόν {partial_area:.3f} m²)",
                "Σύνολο Πλήρη+Μερικά": f"{(full_area + partial_area):.3f} m²",
                "Πλέγμα": f"{getattr(self.view, 'grid_w_m', 5.0):g} m × {getattr(self.view, 'grid_h_m', 3.0):g} m",
            })
        else:
            # Fallback: show minimal info in dock
            self._update_info_pane({
                "Περίμετρος": f"{perimeter_m:.2f} m",
                "Εμβαδόν": f"{area_m2:.2f} m²",
                "Μερικά Κελιά": f"{len(partial_details)}",
                "Πλέγμα": f"{getattr(self.view, 'grid_w_m', 5.0):g} m × {getattr(self.view, 'grid_h_m', 3.0):g} m",
            })

        # Build/update Materials & Cost pane (BOM)
        try:
            posts = estimate_triangle_posts_3x5_with_sides(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
            )
        except Exception:
            posts = None
        try:
            gutters = estimate_gutters_length(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
            )
        except Exception:
            gutters = None
        est = self._ensure_estimator()
        if est is not None:
            try:
                bom = est.compute_bom(posts, gutters, grid_h_m=getattr(self.view, 'grid_h_m', 3.0))
                self._update_bom_pane(bom)
            except Exception:
                pass

        # Only show a short summary in the status bar here; the detailed popup is shown
        # by DrawingView when the perimeter is closed. Print full details to console for
        # debugging/history so we don't pop a second modal dialog.
        try:
            summary = f"Κλείστηκε το περίγραμμα: {perimeter_m:.2f} m, εμβαδόν {poly_area:.3f} m², σύνολο {(full_area + partial_area):.3f} m²"
        except Exception:
            summary = f"Κλείστηκε το περίγραμμα: {perimeter_m:.2f} m, εμβαδόν {area_m2:.3f} m²"
        # show brief message in status bar for a short time
        try:
            self.statusBar().showMessage(summary, 8000)
        except Exception:
            # if no status bar, quietly ignore (don't print to console)
            pass
        # Mark project as modified due to geometry change
        try:
            self._mark_dirty()
        except Exception:
            pass

    def _update_bom_pane(self, bom: BillOfMaterials | None):
        if bom is None:
            return
        try:
            # Αποφυγή αναδράσεων κατά το γέμισμα
            self.bom_tree.blockSignals(True)
            self.bom_tree.clear()
            for line in bom.lines:
                # Υπολογισμός κατάστασης ενημέρωσης, αν υπάρχει πρόσφατο load
                status = ""
                if self._last_loaded_codes or self._last_loaded_errors:
                    if line.code in self._last_loaded_errors:
                        status = "Σφάλμα από αρχείο"
                    elif line.code in self._last_loaded_codes:
                        status = "Ενημερώθηκε"
                    else:
                        status = "Δεν βρέθηκε στο αρχείο"

                item = QTreeWidgetItem([
                    line.name,
                    line.unit,
                    f"{line.quantity:g}",
                    f"{line.unit_price:.2f}",
                    f"{line.total:.2f}",
                    status,
                ])
                # Αποθήκευση του code για να ξέρουμε ποιο υλικό επεξεργαζόμαστε
                item.setData(0, Qt.UserRole, line.code)
                # Επιτρέπουμε edit συνολικά, αλλά το delegate θα ενεργοποιήσει editor μόνο στη στήλη 3
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.bom_tree.addTopLevelItem(item)
            self.bom_total_label.setText(f"Σύνολο: {bom.subtotal:.2f} {bom.currency}")
            self.bom_tree.blockSignals(False)
        except Exception:
            # Safe no-op if dock isn't ready
            try:
                self.bom_tree.blockSignals(False)
            except Exception:
                pass
            pass

    def _on_bom_item_changed(self, item: QTreeWidgetItem, column: int):
        # Μόνο επεξεργασία στη στήλη 3 (Τιμή Μονάδας)
        try:
            if column != 3:
                return
            code = item.data(0, Qt.UserRole)
            if not code:
                return
            est = self._ensure_estimator()
            if est is None:
                return
            # Parse value allowing comma or dot, then force fixed 2-decimal format to avoid scientific notation.
            raw_txt = item.text(3)
            txt = (raw_txt or "").strip().replace(",", ".")
            try:
                new_price = float(txt) if txt else 0.0
            except Exception:
                new_price = 0.0
            # Ενημέρωση υλικού στον estimator
            mat = est.materials.get(code)
            if mat is None:
                est.materials[code] = MaterialItem(code=code, name=item.text(0), unit=item.text(1), unit_price=new_price)
            else:
                mat.unit_price = new_price
            # Αναυπολογισμός γραμμής και υποσυνόλου
            try:
                qty = float(item.text(2)) if item.text(2) else 0.0
            except Exception:
                qty = 0.0
            total = qty * new_price
            self.bom_tree.blockSignals(True)
            # Reformat edited cell (unit price) consistently
            item.setText(3, f"{new_price:.2f}")
            item.setText(4, f"{total:.2f}")
            # Σήμανση ότι η αλλαγή ήταν χειροκίνητη
            try:
                item.setText(5, "Χειροκίνητη αλλαγή")
            except Exception:
                pass
            # Επαναϋπολογισμός υποσυνόλου από όλα τα items
            subtotal = 0.0
            for i in range(self.bom_tree.topLevelItemCount()):
                it = self.bom_tree.topLevelItem(i)
                try:
                    subtotal += float(it.text(4))
                except Exception:
                    pass
            curr = getattr(est, 'currency', 'EUR')
            self.bom_total_label.setText(f"Υποσύνολο: {subtotal:.2f} {curr}")

        finally:
            try:
                self.bom_tree.blockSignals(False)
            except Exception:
                pass

    def _save_materials_to_csv(self, path: Path) -> bool:
        est = self._ensure_estimator()
        if est is None:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Backup αν υπάρχει ήδη
            if path.exists():
                try:
                    backup = path.parent / (path.name + ".bak")
                    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                except Exception:
                    pass
            # Γράψιμο σε προσωρινό αρχείο και atomic replace
            tmp = path.parent / (path.name + ".tmp")
            with tmp.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["code", "name", "unit", "unit_price"])
                for code in sorted(est.materials.keys()):
                    m = est.materials[code]
                    price_str = f"{float(m.unit_price or 0.0):.2f}"
                    writer.writerow([m.code, m.name, m.unit, price_str])
            tmp.replace(path)
            return True
        except Exception:
            return False


    def _save_prices_csv_as_action(self):
        # Αποθήκευση Ως… CSV
        try:
            fname, _ = QFileDialog.getSaveFileName(
                self,
                "Αποθήκευση τιμών ως (CSV)",
                str(self._materials_csv_path()),
                "CSV αρχεία (*.csv);;Όλα τα αρχεία (*)",
            )
            if not fname:
                return
            path = Path(fname)
            ok = self._save_materials_to_csv(path)
            if ok:
                self._current_csv_path = path
                self._csv_applied = True
                try:
                    self.statusBar().showMessage(f"Αποθηκεύτηκαν οι τιμές στο {path.name}", 5000)
                except Exception:
                    pass
                self._update_price_source_label()
            else:
                QMessageBox.warning(self, "Σφάλμα", "Η αποθήκευση τιμών σε CSV απέτυχε.")
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία αποθήκευσης τιμών CSV: {e}")

    def _reset_prices_to_defaults(self):
        """Επαναφορά σε προεπιλεγμένες τιμές (καθαρίζει import και γυρνάει στα embedded defaults ή user defaults)."""
        try:
            est = self._ensure_estimator()
            if est is None:
                return
            # Reload defaults + user defaults (if any)
            est.materials = default_material_catalog()
            try:
                user_defs = self._load_user_defaults()
                if user_defs:
                    est.materials.update(user_defs)
                    self._user_defaults_active = True
                else:
                    self._user_defaults_active = False
            except Exception:
                self._user_defaults_active = False
            # Καθαρισμός κατάστασης import
            self._current_csv_path = None
            self._csv_applied = False
            self._last_loaded_codes = set()
            self._last_loaded_errors = set()
            self._recompute_bom_if_possible()
            self._update_price_source_label()
            try:
                self.statusBar().showMessage("Επαναφέρθηκαν προεπιλογές.", 5000)
            except Exception:
                pass
            try:
                self._mark_dirty()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία επαναφοράς προεπιλογών: {e}")

    def _materials_csv_path(self) -> Path:
        # Default CSV path in repo root
        try:
            return Path(__file__).resolve().parent.parent / "materials.csv"
        except Exception:
            return Path.cwd() / "materials.csv"

    def _user_defaults_csv_path(self) -> Path:
        try:
            root = Path(__file__).resolve().parent.parent
        except Exception:
            root = Path.cwd()
        cfg = root / "config"
        cfg.mkdir(exist_ok=True)
        return cfg / "userdefaults.csv"

    def _load_user_defaults(self) -> dict:
        path = self._user_defaults_path
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                materials = {}
                for row in reader:
                    code = (row.get("code") or "").strip()
                    if not code:
                        continue
                    name = (row.get("name") or code).strip()
                    unit = (row.get("unit") or "piece").strip()
                    try:
                        unit_price = float((row.get("unit_price") or "0").replace(",", "."))
                    except Exception:
                        unit_price = 0.0
                    materials[code] = MaterialItem(code=code, name=name, unit=unit, unit_price=unit_price)
                return materials
        except Exception:
            return {}

    def _save_user_defaults(self):
        """Αποθηκεύει τις τρέχουσες τιμές ως μόνιμες user defaults (config/userdefaults.csv)."""
        est = self._ensure_estimator()
        if est is None:
            QMessageBox.warning(self, "User Defaults", "Δεν υπάρχει estimator.")
            return
        path = self._user_defaults_path
        try:
            with path.open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["code", "name", "unit", "unit_price"])
                for code in sorted(est.materials.keys()):
                    m = est.materials[code]
                    w.writerow([m.code, m.name, m.unit, f"{float(m.unit_price or 0.0):.2f}"])
            self._user_defaults_active = True
            self._update_price_source_label()
            QMessageBox.information(self, "Προεπιλογές", f"Αποθηκεύτηκαν οι τιμές ως μόνιμες προεπιλογές.\n\nΑρχείο: {path.name}\n\nΣτην επόμενη εκκίνηση θα φορτώνονται αυτόματα.")
            try:
                self.statusBar().showMessage(f"Αποθηκεύτηκαν user defaults: {path.name}", 5000)
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "User Defaults", f"Αποτυχία αποθήκευσης: {e}")

    def _factory_reset(self):
        """Επαναφορά εργοστασιακών ρυθμίσεων: διαγραφή user defaults και επιστροφή στα hardcore defaults."""
        try:
            path = self._user_defaults_path
            has_user_defaults = path.exists()
            
            if has_user_defaults:
                reply = QMessageBox.question(
                    self,
                    "Επαναφορά Εργοστασιακών",
                    "Θα διαγραφούν οι μόνιμες προεπιλογές σου (User Defaults) και θα επανέλθουν οι εργοστασιακές τιμές.\n\n"
                    f"Αρχείο: {path.name}\n(Θα δημιουργηθεί backup: {path.name}.bak)\n\n"
                    "Θέλεις να συνεχίσεις;",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
                # Δημιουργία backup
                try:
                    backup = path.with_suffix(".bak")
                    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                except Exception:
                    pass
                # Διαγραφή user defaults
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
            
            # Επιστροφή σε hardcore defaults
            est = self._ensure_estimator()
            if est is None:
                return
            est.materials = default_material_catalog()
            self._user_defaults_active = False
            self._current_csv_path = None
            self._csv_applied = False
            self._last_loaded_codes = set()
            self._last_loaded_errors = set()
            self._recompute_bom_if_possible()
            self._update_price_source_label()
            
            if has_user_defaults:
                QMessageBox.information(self, "Εργοστασιακές Ρυθμίσεις", "Επαναφέρθηκαν οι εργοστασιακές τιμές.\n\nΤα User Defaults διαγράφηκαν.")
            try:
                self.statusBar().showMessage("Επαναφέρθηκαν εργοστασιακές ρυθμίσεις.", 5000)
            except Exception:
                pass
            try:
                self._mark_dirty()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία επαναφοράς εργοστασιακών: {e}")

    def _restore_user_defaults_from_backup(self):
        """Restore a userdefaults backup (.bak) into config/userdefaults.csv and reload it.

        Opens a file dialog in the config directory to pick a .bak file. After confirmation
        the selected backup is copied over the active userdefaults file and the estimator
        is reloaded with the restored values.
        """
        try:
            cfg_dir = self._user_defaults_path.parent if hasattr(self, '_user_defaults_path') else self._user_defaults_csv_path().parent
            # Let the user choose a .bak file (start in config/)
            fname, _ = QFileDialog.getOpenFileName(
                self,
                "Επιλογή αντιγράφου ασφαλείας (Backup)",
                str(cfg_dir),
                "Backup αρχεία (*.bak);;Όλα τα αρχεία (*)",
            )
            if not fname:
                return
            bak = Path(fname)
            if not bak.exists():
                QMessageBox.warning(self, "Σφάλμα", "Το επιλεγμένο αρχείο αντιγράφου ασφαλείας δεν υπάρχει.")
                return

            # Confirm with the user
            reply = QMessageBox.question(
                self,
                "Επαναφορά από Backup",
                f"Επαναφορά του backup:\n{bak.name}\n\nΘέλεις να αντιγραφεί στο {self._user_defaults_path.name} και να εφαρμοστεί;",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            # Ensure config dir exists and copy contents
            try:
                self._user_defaults_path.parent.mkdir(parents=True, exist_ok=True)
                self._user_defaults_path.write_text(bak.read_text(encoding='utf-8'), encoding='utf-8')
            except Exception as e:
                QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία επαναφοράς backup: {e}")
                return

            # Reload user defaults into estimator
            est = self._ensure_estimator()
            try:
                user_defs = self._load_user_defaults()
                if user_defs:
                    if est is not None:
                        est.materials.update(user_defs)
                    self._user_defaults_active = True
                else:
                    # If the restored file contained no valid rows, clear the flag
                    self._user_defaults_active = False
            except Exception:
                self._user_defaults_active = False

            # Reflect changes in UI
            self._current_csv_path = None
            self._csv_applied = False
            self._last_loaded_codes = set()
            self._last_loaded_errors = set()
            self._recompute_bom_if_possible()
            self._update_price_source_label()

            QMessageBox.information(self, "Επαναφορά Backup", f"Επαναφέρθηκαν τα User Defaults από: {bak.name}")
            try:
                self.statusBar().showMessage(f"Επαναφέρθηκαν user defaults από: {bak.name}", 5000)
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Απέτυχε η επαναφορά από backup: {e}")

    def _read_csv_materials(self, path: Path):
        """Διαβάζει ένα CSV αρχείο υλικών και επιστρέφει (materials_dict, loaded_codes_set, error_codes_set)."""
        materials = {}
        loaded_codes = set()
        error_codes = set()
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = (row.get("code") or "").strip()
                    if not code:
                        continue
                    name = (row.get("name") or code).strip()
                    unit = (row.get("unit") or "piece").strip()
                    try:
                        unit_price = float((row.get("unit_price") or "0").replace(",", "."))
                    except Exception:
                        unit_price = None
                    if unit_price is None:
                        error_codes.add(code)
                        continue
                    materials[code] = MaterialItem(code=code, name=name, unit=unit, unit_price=unit_price)
                    loaded_codes.add(code)
        except Exception:
            pass
        return materials, loaded_codes, error_codes

    def _import_prices_csv_dialog(self):
        # Άνοιγμα διαλόγου για CSV και εισαγωγή τιμών
        try:
            fname, _ = QFileDialog.getOpenFileName(
                self,
                "Επιλογή αρχείου τιμών (CSV)",
                str(self._materials_csv_path().parent),
                "CSV αρχεία (*.csv);;Όλα τα αρχεία (*)",
            )
            if not fname:
                return
            path = Path(fname)
            if not path.exists():
                QMessageBox.warning(self, "Σφάλμα", "Το αρχείο δεν υπάρχει.")
                return
            materials, loaded_codes, error_codes = self._read_csv_materials(path)

            est = self._ensure_estimator()
            if est is None:
                return

            if materials:
                # Συγχώνευση με τα ήδη υπάρχοντα (κρατάμε defaults και ενημερώνουμε/προσθέτουμε όσα υπάρχουν στο CSV)
                est.materials.update(materials)
                # Θυμόμαστε το μονοπάτι του CSV για μελλοντική αποθήκευση
                self._current_csv_path = path
                self._last_loaded_codes = loaded_codes
                self._last_loaded_errors = error_codes
                self._csv_applied = True
                self._recompute_bom_if_possible()
                try:
                    self._update_price_source_label()
                except Exception:
                    pass
                # Mark session dirty due to materials change
                try:
                    self._mark_dirty()
                except Exception:
                    pass
                updated_list = sorted(list(loaded_codes - error_codes))
                error_list = sorted(list(error_codes))
                msg = [
                    f"Ενημερώθηκαν: {len(updated_list)}",
                    f"Με σφάλμα: {len(error_list)}",
                ]
                if updated_list:
                    msg.append("\nΚωδικοί ενημερώθηκαν (ενδεικτικά): " + ", ".join(updated_list[:10]) + (" …" if len(updated_list) > 10 else ""))
                if error_list:
                    msg.append("Κωδικοί με σφάλμα: " + ", ".join(error_list[:10]) + (" …" if len(error_list) > 10 else ""))
                QMessageBox.information(self, "Εισαγωγή Τιμών", "\n".join(msg))
                try:
                    self.statusBar().showMessage(f"Φορτώθηκαν τιμές από: {path.name}", 5000)
                except Exception:
                    pass
            else:
                QMessageBox.information(self, "Εισαγωγή Τιμών", "Δεν βρέθηκαν έγκυρες τιμές στο αρχείο.")
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία φόρτωσης τιμών CSV: {e}")

    def _update_info_pane(self, info: dict | None):
        if info is None:
            return
        try:
            self.info_tree.clear()
            for k, v in info.items():
                item = QTreeWidgetItem([str(k), str(v)])
                self.info_tree.addTopLevelItem(item)
        except Exception:
            pass

    # ---------------------------
    # Project (Μελέτη) menu
    # ---------------------------
    def _create_menubar(self):
        mb = self.menuBar()
        proj = mb.addMenu("Μελέτη")
        # New Project
        act_new = QAction("Νέα Μελέτη", self)
        act_new.setShortcut("Ctrl+N")
        act_new.triggered.connect(self._project_new)
        proj.addAction(act_new)
        # Open Project
        act_open = QAction("Φόρτωση Μελέτης…", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._project_open)
        proj.addAction(act_open)
        proj.addSeparator()
        # Save / Save As
        act_save = QAction("Αποθήκευση Μελέτης", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self._project_save)
        proj.addAction(act_save)

        act_save_as = QAction("Αποθήκευση Μελέτης ως…", self)
        act_save_as.setShortcut("Ctrl+Shift+S")
        act_save_as.triggered.connect(self._project_save_as)
        proj.addAction(act_save_as)

        # Settings menu (Ρυθμίσεις)
        settings = mb.addMenu("Ρυθμίσεις")
        act_max_zoom = QAction("Μέγιστο Όριο Zoom Out…", self)
        act_max_zoom.triggered.connect(self._settings_max_zoom)
        settings.addAction(act_max_zoom)

    def _project_title(self) -> str:
        name = None
        try:
            name = self._project_name or (self._project_path.stem if self._project_path else None)
        except Exception:
            name = self._project_name
        if name:
            return f"Greenhouse – {name}"
        return "Greenhouse – Νέα Μελέτη"

    def _update_window_title(self):
        t = self._project_title()
        if getattr(self, '_dirty', False):
            t += " *"
        self.setWindowTitle(t)

    def _mark_dirty(self):
        self._dirty = True
        # New edits reactivate prompting
        self._suppress_save_prompt = False
        try:
            self._update_window_title()
        except Exception:
            pass

    def _maybe_save_before_loss(self) -> bool:
        """If there are unsaved changes, prompt to save/discard/cancel.
        Returns True to proceed (after optional save), False to cancel.
        """
        if not getattr(self, '_dirty', False):
            return True
        # If user already chose Don't Save for the current dirty state, don't nag again
        if getattr(self, '_suppress_save_prompt', False):
            return True
        m = QMessageBox(self)
        m.setWindowTitle("Μη αποθηκευμένες αλλαγές")
        m.setText("Θέλεις να αποθηκεύσεις τις αλλαγές στη μελέτη;")
        save_btn = m.addButton("Αποθήκευση", QMessageBox.AcceptRole)
        discard_btn = m.addButton("Να μην αποθηκευτεί", QMessageBox.DestructiveRole)
        cancel_btn = m.addButton("Άκυρο", QMessageBox.RejectRole)
        m.setIcon(QMessageBox.Warning)
        m.exec()
        clicked = m.clickedButton()
        if clicked is save_btn:
            ok = self._project_save()
            return bool(ok)
        if clicked is cancel_btn:
            return False
        # Discard: suppress further prompts until new edits happen
        self._suppress_save_prompt = True
        return True

    def _project_new(self, from_startup: bool = False) -> bool:
        """Create a new project after asking for name and greenhouse type (grid)."""
        # Ask to save unsaved changes unless invoked from startup dialog
        if not from_startup:
            if not self._maybe_save_before_loss():
                return False
        dlg = NewProjectDialog(self, presets=getattr(self, '_grid_presets', None))
        if dlg.exec() != QDialog.Accepted:
            # If user cancels, keep current state; user can still draw freely.
            try:
                self.statusBar().showMessage("Ακυρώθηκε η δημιουργία νέας μελέτης.", 3000)
            except Exception:
                pass
            return False
        type_label, w, h = dlg.get_values()
        # Don't set project name yet; the user will pick it on first Save/Save As
        self._project_name = None
        self._project_path = None

        # Apply chosen grid based on type
        chosen_w, chosen_h = None, None
        try:
            if type_label in getattr(self, '_grid_presets', {}):
                preset = self._grid_presets[type_label]
                if preset is None:
                    # Custom
                    chosen_w, chosen_h = float(w), float(h)
                else:
                    chosen_w, chosen_h = float(preset[0]), float(preset[1])
            else:
                # Fallback to dialog values
                chosen_w, chosen_h = float(w), float(h)
        except Exception:
            chosen_w, chosen_h = float(w), float(h)

        # Set view grid values
        try:
            self.view.grid_w_m = chosen_w
            self.view.grid_h_m = chosen_h
        except Exception:
            pass
        # Remember chosen type label for status display
        try:
            self._project_type_label = str(type_label) if type_label else None
        except Exception:
            self._project_type_label = None

        # Clear drawing and state for new project
        self.view.clear_all()
        self._last_xy = None
        self._dirty = False
        self._suppress_save_prompt = False
        try:
            self._update_window_title()
            self._project_type_label = str(type_label) if type_label else None
            self._update_status_labels()
            self.statusBar().showMessage(
                f"Ξεκίνησε νέα μελέτη – Τύπος: {self._project_type_label or '—'}, Πλέγμα {self.view.grid_w_m:g}×{self.view.grid_h_m:g} m",
                5000,
            )
            # Ensure the main window is visible and focused
            self.show()
            self._focus_main_window()
        except Exception:
            pass
        return True

    def _project_open(self) -> bool:
        # Ask to save unsaved changes first
        if not self._maybe_save_before_loss():
            return False
        try:
            fname, _ = QFileDialog.getOpenFileName(self, "Φόρτωση Μελέτης", str(Path.cwd()), f"Greenhouse Project (*{PROJECT_EXT});;Όλα τα αρχεία (*)")
            if not fname:
                return False
            path = Path(fname)
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία φόρτωσης μελέτης: {e}")
            return False
        ok = self._apply_project_dict(data)
        if ok:
            self._project_path = path
            # Use explicit name if present; else derive from path
            try:
                self._project_name = (data or {}).get("meta", {}).get("name") or path.stem
            except Exception:
                self._project_name = path.stem
            self._project_defined = True
            self._dirty = False
            self._suppress_save_prompt = False
            try:
                self._update_window_title()
                self.statusBar().showMessage(f"Φορτώθηκε: {path.name}", 5000)
                self._update_status_labels()
            except Exception:
                pass
            return True
        return False

    def _project_save(self):
        if not self._project_path:
            return self._project_save_as()
        data = self._project_to_dict()
        try:
            self._project_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            try:
                self.statusBar().showMessage(f"Αποθηκεύτηκε: {self._project_path.name}", 4000)
            except Exception:
                pass
            self._dirty = False
            self._suppress_save_prompt = False
            try:
                self._update_window_title()
                self._update_status_labels()
            except Exception:
                pass
            return True
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία αποθήκευσης: {e}")
            return False

    def _project_save_as(self):
        try:
            suggested = (self._project_name or "project") + PROJECT_EXT
            fname, _ = QFileDialog.getSaveFileName(self, "Αποθήκευση Μελέτης ως…", str(self._projects_dir_path() / suggested), f"Greenhouse Project (*{PROJECT_EXT});;Όλα τα αρχεία (*)")
            if not fname:
                return False
            path = Path(fname)
            if path.suffix.lower() != PROJECT_EXT:
                path = path.with_suffix(PROJECT_EXT)
            data = self._project_to_dict()
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            self._project_path = path
            # Use explicit project name (stem) if not already set
            if not self._project_name:
                try:
                    self._project_name = path.stem
                except Exception:
                    pass
            self._project_defined = True
            self._dirty = False
            self._suppress_save_prompt = False
            try:
                self._update_window_title()
                self.statusBar().showMessage(f"Αποθηκεύτηκε: {path.name}", 5000)
                self._update_status_labels()
            except Exception:
                pass
            return True
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία αποθήκευσης: {e}")
            return False

    def _project_to_dict(self) -> dict:
        # Serialize current view state and minimal app settings into JSON-ready dict
        pts = []
        try:
            for p in self.view.state.points:
                try:
                    pts.append([float(p.x()), float(p.y())])
                except Exception:
                    pts.append([float(p[0]), float(p[1])])
        except Exception:
            pts = []
        guides = []
        try:
            for s, e in self.view.state.guides:
                guides.append([[float(s.x()), float(s.y())], [float(e.x()), float(e.y())]])
        except Exception:
            guides = []

        # Materials source hint (optional metadata)
        mat_src = "defaults"
        csv_path = None
        try:
            if getattr(self, '_current_csv_path', None):
                mat_src = "csv"
                csv_path = str(self._current_csv_path)
            elif getattr(self, '_user_defaults_active', False):
                mat_src = "user_defaults"
        except Exception:
            pass

        data = {
            "version": "1.0",
            "grid": {
                "w_m": float(getattr(self.view, 'grid_w_m', 5.0) or 5.0),
                "h_m": float(getattr(self.view, 'grid_h_m', 3.0) or 3.0),
                "scale_factor": float(getattr(self.view, 'scale_factor', 5.0) or 5.0),
            },
            "geometry": {
                "points": pts,
                "guides": guides,
                "breaks": list(getattr(self.view.state, 'breaks', []) or []),
                "start_new_chain_pending": bool(getattr(self.view.state, 'start_new_chain_pending', False)),
            },
            "columns": {
                "large": float(self.large_column_height or 0.0),
                "small": float(self.small_column_height or 0.0),
            },
            "materials": {
                "source": mat_src,
                "csv_path": csv_path,
            },
            "meta": {
                "name": self._project_name,
                "original_path": str(self._project_path) if self._project_path else None,
                "autosave": False,
            },
        }
        return data

    def _apply_project_dict(self, data: dict) -> bool:
        try:
            g = (data or {}).get("grid", {})
            self.view.grid_w_m = float(g.get("w_m", getattr(self.view, 'grid_w_m', 5.0)))
            self.view.grid_h_m = float(g.get("h_m", getattr(self.view, 'grid_h_m', 3.0)))
            sf = float(g.get("scale_factor", getattr(self.view, 'scale_factor', 5.0)))
            try:
                # Only update scale_factor if positive
                if sf > 0:
                    self.view.scale_factor = sf
            except Exception:
                pass

            geom = (data or {}).get("geometry", {})
            pts = geom.get("points", []) or []
            guides = geom.get("guides", []) or []
            breaks = geom.get("breaks", []) or []
            start_pending = bool(geom.get("start_new_chain_pending", False))
            # Apply to view state
            self.view.state.points = [QPointF(float(x), float(y)) for (x, y) in pts]
            self.view.state.guides = [(QPointF(float(sx), float(sy)), QPointF(float(ex), float(ey))) for ((sx, sy), (ex, ey)) in guides]
            try:
                self.view.state.breaks = [int(i) for i in (breaks or [])]
            except Exception:
                self.view.state.breaks = []
            self.view.state.start_new_chain_pending = start_pending
            self.view.state.save_state()
            self.view.perimeter_manager.refresh_perimeter()
            self.view._refresh_guides()
            try:
                self.view.triangle_manager.grid_w_m = self.view.grid_w_m
                self.view.triangle_manager.grid_h_m = self.view.grid_h_m
                self.view.triangle_manager.clear_triangles()
                if len(self.view.state.points) >= 3 and (self.view.state.points[0] == self.view.state.points[-1]):
                    self.view.triangle_manager.draw_north_triagonals(self.view.state.points)
                    self.view.state.perimeter_locked = True
            except Exception:
                pass

            cols = (data or {}).get("columns", {})
            try:
                self.large_column_height = float(cols.get("large", 0.0) or 0.0)
                self.small_column_height = float(cols.get("small", 0.0) or 0.0)
            except Exception:
                self.large_column_height, self.small_column_height = None, None

            # Optional: restore material price source hint (no auto-load for safety)
            mats = (data or {}).get("materials", {})
            try:
                src = mats.get("source")
                path = mats.get("csv_path")
                # We only annotate UI; do not auto-load external files without user consent
                if src == "csv" and path:
                    self._current_csv_path = Path(path)
                    self._csv_applied = False
                elif src == "user_defaults":
                    self._user_defaults_active = True
                else:
                    self._current_csv_path = None
                    self._user_defaults_active = False
                self._update_price_source_label()
            except Exception:
                pass

            # Cache xy for recompute, recompute overlays/BOM
            self._last_xy = [(float(p.x()), float(p.y())) for p in self.view.state.points]
            self._recompute_info_if_possible()
            self._recompute_bom_if_possible()
            self.view.recompute_overlay_if_possible()
            try:
                self.view.viewport().update()
            except Exception:
                pass
            # Meta: name
            try:
                meta = (data or {}).get("meta", {})
                nm = meta.get("name")
                if nm:
                    self._project_name = nm
            except Exception:
                pass
            self._project_defined = True
            self._dirty = False
            return True
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία εφαρμογής μελέτης: {e}")
            return False
    
    def _preset_label_for_grid(self, w: float, h: float) -> str | None:
        try:
            for lbl, dims in (self._grid_presets or {}).items():
                if not dims:
                    continue
                gw, gh = dims
                if abs(float(gw) - float(w)) < 1e-6 and abs(float(gh) - float(h)) < 1e-6:
                    return lbl
        except Exception:
            pass
        return None

    def _update_status_labels(self):
        """Update permanent status bar labels: project name, type, grid."""
        try:
            name = self._project_name or "(χωρίς όνομα)"
            self.status_project_label.setText(f"Μελέτη: {name}")
        except Exception:
            pass
        try:
            # Prefer remembered label; else try to infer from grid dims
            lbl = self._project_type_label or self._preset_label_for_grid(getattr(self.view, 'grid_w_m', 5.0), getattr(self.view, 'grid_h_m', 3.0))
            self.status_type_label.setText(f"Τύπος: {lbl}" if lbl else "Τύπος: —")
        except Exception:
            pass
        try:
            self.status_grid_label.setText(f"Πλέγμα: {getattr(self.view, 'grid_w_m', 5.0):g}×{getattr(self.view, 'grid_h_m', 3.0):g} m")
        except Exception:
            pass

    # ---------------------------
    # Startup & Autosave helpers
    # ---------------------------
    def _focus_main_window(self):
        """Bring the main window to the foreground after modal dialogs."""
        try:
            if self.isMinimized():
                self.showNormal()
        except Exception:
            pass
        try:
            self.raise_()
        except Exception:
            pass
        try:
            self.activateWindow()
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_startup_prompt_scheduled", False):
            self._startup_prompt_scheduled = True
            try:
                QTimer.singleShot(0, self._run_startup_prompt_sequence)
            except Exception:
                # Fallback: run synchronously if timer fails
                self._run_startup_prompt_sequence()

    def _run_startup_prompt_sequence(self):
        # Ensure the main window is visible before prompting
        try:
            self._focus_main_window()
        except Exception:
            pass

        try:
            self._startup_project_prompt()
        finally:
            try:
                self._start_autosave_timer()
            except Exception:
                pass

    def _projects_dir_path(self) -> Path:
        try:
            root = Path(__file__).resolve().parent.parent
        except Exception:
            root = Path.cwd()
        p = root / "projects"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _autosave_file_path(self) -> Path:
        try:
            root = Path(__file__).resolve().parent.parent
        except Exception:
            root = Path.cwd()
        cfg = root / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        return cfg / "autosave.ghp"

    def _startup_project_prompt(self):
        """Prompt on startup: continue previous autosave or create a new project by name."""
        has_autosave = self._autosave_path.exists()
        # Loop allows returning to choices if user cancels file open
        for _ in range(2):  # at most 2 cycles to avoid infinite loop
            if has_autosave:
                m = QMessageBox(self)
                m.setWindowTitle("Έναρξη Μελέτης")
                m.setText("Θέλεις να συνεχίσεις από την τελευταία αυτόματη αποθήκευση, να ανοίξεις αποθηκευμένη μελέτη ή να ξεκινήσεις νέα μελέτη;")
                btn_cont = m.addButton("Συνέχεια", QMessageBox.AcceptRole)
                btn_open = m.addButton("Άνοιγμα…", QMessageBox.ActionRole)
                btn_new = m.addButton("Νέα Μελέτη", QMessageBox.DestructiveRole)
                m.setIcon(QMessageBox.Question)
                m.exec()
                if m.clickedButton() is btn_cont:
                    try:
                        data = json.loads(self._autosave_path.read_text(encoding='utf-8'))
                        if isinstance(data, dict):
                            data.setdefault("meta", {})
                            data["meta"]["autosave"] = False
                        if self._apply_project_dict(data):
                            try:
                                op = (data or {}).get("meta", {}).get("original_path")
                                if op:
                                    self._project_path = Path(op)
                            except Exception:
                                pass
                            self._project_name = (data or {}).get("meta", {}).get("name") or (self._project_path.stem if self._project_path else None)
                            self._project_defined = True
                            try:
                                self._update_window_title()
                                self.statusBar().showMessage("Συνέχεια από αυτόματη αποθήκευση.", 4000)
                            except Exception:
                                pass
                            self._focus_main_window()
                            return
                    except Exception:
                        pass
                if m.clickedButton() is btn_open:
                    ok = False
                    try:
                        ok = self._project_open()
                    except Exception:
                        ok = False
                    if ok:
                        self._focus_main_window()
                        return
                    # else: loop again to show choices
                    continue
                # New project (from startup)
                if self._project_new(from_startup=True):
                    self._focus_main_window()
                    return
                else:
                    # user canceled new; allow drawing and exit prompt
                    self._focus_main_window()
                    return
            else:
                m = QMessageBox(self)
                m.setWindowTitle("Έναρξη Μελέτης")
                m.setText("Θέλεις να ανοίξεις αποθηκευμένη μελέτη ή να ξεκινήσεις νέα;")
                btn_open = m.addButton("Άνοιγμα…", QMessageBox.AcceptRole)
                btn_new = m.addButton("Νέα Μελέτη", QMessageBox.DestructiveRole)
                m.setIcon(QMessageBox.Question)
                m.exec()
                if m.clickedButton() is btn_open:
                    ok = False
                    try:
                        ok = self._project_open()
                    except Exception:
                        ok = False
                    if ok:
                        self._focus_main_window()
                        return
                    # try again once
                    continue
                if self._project_new(from_startup=True):
                    self._focus_main_window()
                    return
                else:
                    self._focus_main_window()
                    return

    def closeEvent(self, event):
        # Temporarily disabled save prompt on close
        # try:
        #     proceed = self._maybe_save_before_loss()
        #     if not proceed:
        #         event.ignore()
        #         return
        # except Exception:
        #     pass
        return super().closeEvent(event)

    def _start_autosave_timer(self, interval_ms: int = 30000):
        if not self._autosave_enabled:
            return
        if self._autosave_timer:
            try:
                self._autosave_timer.stop()
            except Exception:
                pass
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(interval_ms)
        self._autosave_timer.timeout.connect(self._do_autosave)
        self._autosave_timer.start()

    def _do_autosave(self):
        # Autosave unsaved sessions too, but only if there's content
        has_content = False
        try:
            has_content = bool(self.view.state.points or self.view.state.guides)
        except Exception:
            has_content = False
        if not has_content:
            return
        try:
            data = self._project_to_dict()
            # mark as autosave
            try:
                data.setdefault("meta", {})
                data["meta"]["autosave"] = True
            except Exception:
                pass
            self._autosave_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            # Also drop a tiny meta file with timestamp if needed in future
            try:
                self.statusBar().showMessage("Αυτόματη αποθήκευση", 1500)
            except Exception:
                pass
        except Exception:
            # Silent fail is acceptable for autosave
            pass

    def _apply_new_project_name(self, name: str):
        self._project_name = name
        self._project_defined = True
        # Do not assign a path yet; Save As will set it. Title updates automatically.

    def _recompute_bom_if_possible(self):
        if not self._last_xy:
            return
        xy = self._last_xy
        try:
            posts = estimate_triangle_posts_3x5_with_sides(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
            )
        except Exception:
            posts = None
        try:
            gutters = estimate_gutters_length(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
            )
        except Exception:
            gutters = None
        est = self._ensure_estimator()
        if est is not None:
            try:
                bom = est.compute_bom(posts, gutters, grid_h_m=getattr(self.view, 'grid_h_m', 3.0))
                self._update_bom_pane(bom)
            except Exception:
                pass

    def _recompute_info_if_possible(self):
        if not self._last_xy:
            return
        xy = self._last_xy
        try:
            coverage = geom_compute_grid_coverage(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
            )
        except Exception:
            coverage = None
        perimeter_m = 0.0
        for i in range(1, len(xy)):
            x0, y0 = xy[i-1]
            x1, y1 = xy[i]
            perimeter_m += ((x1 - x0)**2 + (y1 - y0)**2) ** 0.5 / self.view.scale_factor
        # area (m^2) via shoelace
        area_m2 = 0.0
        try:
            pts = list(xy)
            if pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            s = 0.0
            for i in range(len(pts)-1):
                x1, y1 = pts[i]
                x2, y2 = pts[i+1]
                s += x1*y2 - x2*y1
            area_px2 = abs(s) * 0.5
            area_m2 = area_px2 / (self.view.scale_factor ** 2)
        except Exception:
            pass

        if coverage:
            poly_area = coverage['polygon_area_m2']
            full_count = coverage['full_count']
            full_area = coverage['full_area_m2']
            partials = coverage['partial_details']
            partial_count = len(partials)
            partial_area = sum(p['area_m2'] for p in partials)
            self._update_info_pane({
                "Περίμετρος": f"{perimeter_m:.2f} m",
                "Εμβαδόν Πολυγώνου": f"{poly_area:.3f} m²",
                "Πλήρη Κελιά": f"{full_count} (εμβαδόν {full_area:.3f} m²)",
                "Μερικά Κελιά": f"{partial_count} (εμβαδόν {partial_area:.3f} m²)",
                "Σύνολο Πλήρη+Μερικά": f"{(full_area + partial_area):.3f} m²",
                "Πλέγμα": f"{getattr(self.view, 'grid_w_m', 5.0):g} m × {getattr(self.view, 'grid_h_m', 3.0):g} m",
            })
        else:
            self._update_info_pane({
                "Περίμετρος": f"{perimeter_m:.2f} m",
                "Εμβαδόν": f"{area_m2:.2f} m²",
                "Πλέγμα": f"{getattr(self.view, 'grid_w_m', 5.0):g} m × {getattr(self.view, 'grid_h_m', 3.0):g} m",
            })

    def _clear_all_and_reset(self):
        # Clear the drawing and reset panels
        self.view.clear_all()
        self._last_xy = None
        try:
            self.bom_tree.clear()
            self.bom_total_label.setText("Υποσύνολο: 0.00 EUR")
        except Exception:
            pass
        try:
            self.info_tree.clear()
        except Exception:
            pass
        # Clearing everything is a modification
        try:
            self._mark_dirty()
        except Exception:
            pass

    def _clear_guides_and_mark_dirty(self):
        try:
            self.view.clear_guides()
        finally:
            try:
                self._mark_dirty()
            except Exception:
                pass

    def _delete_selected_and_mark_dirty(self):
        try:
            self.view.delete_selected()
        finally:
            try:
                self._mark_dirty()
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
                try:
                    self._mark_dirty()
                except Exception:
                    pass
            else:
                QMessageBox.warning(
                    self,
                    "Invalid Input",
                    "Please enter valid numeric values for column heights."
                )

    def _update_price_source_label(self):
        """Ενημερώνει το label με την τρέχουσα πηγή τιμών (CSV, User Defaults, ή Προεπιλογές)."""
        try:
            lbl = getattr(self, 'price_source_label', None)
            if lbl is None:
                return
            # Απλή λογική: αν υπάρχει ενεργό CSV δείξε το, αλλιώς defaults
            p = self._current_csv_path
            if p and isinstance(p, Path) and self._csv_applied:
                lbl.setText(f"Τιμές: {p.name}")
                lbl.setToolTip(str(p))
            elif getattr(self, '_user_defaults_active', False):
                lbl.setText("Τιμές: User Defaults")
                lbl.setToolTip("Φορτώθηκαν μόνιμες προσαρμογές από config/userdefaults.csv")
            else:
                lbl.setText("Τιμές: Προεπιλογές")
                lbl.setToolTip("Ενσωματωμένες προεπιλεγμένες τιμές")
        except Exception:
            pass