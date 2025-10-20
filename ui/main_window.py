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
from PySide6.QtCore import Qt, QPointF, QTimer, QSettings
from PySide6.QtGui import QAction, QActionGroup

from services.estimator import Estimator, default_material_catalog
from services.models import MaterialItem, BillOfMaterials
from services.geometry_utils import (
    compute_grid_coverage as geom_compute_grid_coverage,
    estimate_triangle_posts_3x5_with_sides,
    estimate_gutters_length,
    estimate_koutelou_pairs,
    estimate_plevra,
)
from ui.drawing_view import DrawingView
from ui.column_height_dialog import ColumnHeightDialog
from ui.material_settings_dialog import MaterialSettingsDialog

from pathlib import Path
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

        # Ανοιγμα σε full screen/maximized
        self.showMaximized()
        
        self.estimator = None  # lazy-created when needed
        self.material_settings = {}  # Ρυθμίσεις υλικών από το dialog

        self.view = DrawingView(self)
        self.setCentralWidget(self.view)
        self.large_column_height = None
        self.small_column_height = None
        
        # Project state
        self._project_path = None
        self._project_name = None
        self._project_defined = False
        self._autosave_timer = None
        self._autosave_path = self._autosave_file_path()
        self._autosave_enabled = True
        self._last_directory = None  # Track last opened/saved directory
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

        # Initialize QSettings for persistent user preferences
        self.settings = QSettings("Greenhouse", "GreenhouseApp")
        
        # Load user settings
        self._load_user_settings()

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
        # Κουμπί Προσαρμογής Υλικών
        self.toolbar.addSeparator()
        self.material_settings_button = QToolButton(self.toolbar)
        self.material_settings_button.setText("Προσαρμογή Υλικών")
        self.material_settings_button.clicked.connect(self._show_material_settings)
        self.toolbar.addWidget(self.material_settings_button)

    def _zoom_to_drawing(self):
        try:
            self.view.zoom_to_drawing()
        except Exception:
            pass

    def _create_bom_dock(self):
        self.bom_dock = QDockWidget("Υπολογισμός Κόστους Υλικών", self)
        self.bom_dock.setObjectName("MaterialsCostDock")
        # Ορισμός μεγαλύτερου πλάτους για να φαίνονται όλες οι στήλες
        self.bom_dock.setMinimumWidth(550)
        
        container = QWidget(self.bom_dock)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)

        self.bom_tree = QTreeWidget(container)
        self.bom_tree.setColumnCount(8)
        self.bom_tree.setHeaderLabels(["Είδος", "Πάχος", "Ύψος", "Μήκος", "Μονάδα", "Ποσότητα", "Τιμή Μονάδας", "Υποσύνολο"]) 
        self.bom_tree.setRootIsDecorated(False)
        
        # Ορισμός πλατών στηλών για καλύτερη εμφάνιση
        self.bom_tree.setColumnWidth(0, 100)  # Είδος
        self.bom_tree.setColumnWidth(1, 80)   # Πάχος
        self.bom_tree.setColumnWidth(2, 80)   # Ύψος
        self.bom_tree.setColumnWidth(3, 80)   # Μήκος
        self.bom_tree.setColumnWidth(4, 80)   # Μονάδα
        self.bom_tree.setColumnWidth(5, 100)  # Ποσότητα
        self.bom_tree.setColumnWidth(6, 120)  # Τιμή Μονάδας
        self.bom_tree.setColumnWidth(7, 120)  # Υποσύνολο
        
        layout.addWidget(self.bom_tree)

        self.bom_total_label = QLabel("Σύνολο: 0.00 EUR", container)
        layout.addWidget(self.bom_total_label)

        container.setLayout(layout)
        self.bom_dock.setWidget(container)
        self.addDockWidget(Qt.RightDockWidgetArea, self.bom_dock)
        try:
            toggle_action = self.bom_dock.toggleViewAction()
            toggle_action.setText("Πάνελ Υπολογισμού Κόστους")
            self.toolbar.addAction(toggle_action)
        except Exception:
            pass

    def _create_info_dock(self):
        self.info_dock = QDockWidget("Στοιχεία Σχεδίου", self)
        self.info_dock.setObjectName("DrawingInfoDock")
        # Ορισμός μεγαλύτερου πλάτους
        self.info_dock.setMinimumWidth(550)
        
        container = QWidget(self.info_dock)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        self.info_tree = QTreeWidget(container)
        self.info_tree.setColumnCount(2)
        self.info_tree.setHeaderLabels(["Πεδίο", "Τιμή"])
        self.info_tree.setRootIsDecorated(False)
        # Ορισμός πλατών στηλών
        self.info_tree.setColumnWidth(0, 250)  # Πεδίο
        self.info_tree.setColumnWidth(1, 200)  # Τιμή
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
                self._save_user_settings()  # Save the setting
                self.statusBar().showMessage(f"Το μέγιστο όριο zoom out ορίστηκε σε {value} μέτρα", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία αλλαγής ορίου: {e}")

    def _toggle_autosave(self):
        """Toggle autosave on/off."""
        self._autosave_enabled = self.act_autosave.isChecked()
        
        if self._autosave_enabled:
            self._start_autosave_timer()
            self.statusBar().showMessage("Αυτόματη αποθήκευση ενεργοποιήθηκε", 3000)
        else:
            if self._autosave_timer:
                self._autosave_timer.stop()
            self.statusBar().showMessage("Αυτόματη αποθήκευση απενεργοποιήθηκε", 3000)
        
        self._save_user_settings()  # Save the preference

    def _load_user_settings(self):
        """Load user preferences from QSettings."""
        try:
            # Load max zoom limit
            max_grid_meters = self.settings.value("view/max_grid_meters", 500, type=float)
            self.view.max_grid_meters = max_grid_meters
            
            # Load autosave enabled state
            self._autosave_enabled = self.settings.value("general/autosave_enabled", True, type=bool)
            
            # Load autosave interval (in milliseconds, default 30 seconds)
            autosave_interval = self.settings.value("general/autosave_interval", 30000, type=int)
            
            # Load last opened directory
            last_dir = self.settings.value("paths/last_directory", "", type=str)
            if last_dir:
                self._last_directory = Path(last_dir)
            
            # Future settings can be added here:
            # - Window geometry/state
            # - Default grid presets
            # - Material catalog path
            # - Export preferences
            # - UI theme/language
            
        except Exception as e:
            print(f"Warning: Failed to load user settings: {e}")

    def _save_user_settings(self):
        """Save user preferences to QSettings."""
        try:
            # Save max zoom limit
            self.settings.setValue("view/max_grid_meters", self.view.max_grid_meters)
            
            # Save autosave settings
            self.settings.setValue("general/autosave_enabled", self._autosave_enabled)
            if hasattr(self, '_autosave_timer') and self._autosave_timer:
                self.settings.setValue("general/autosave_interval", self._autosave_timer.interval())
            
            # Save last opened directory if exists
            if hasattr(self, '_last_directory') and self._last_directory:
                self.settings.setValue("paths/last_directory", str(self._last_directory))
            
            # Future settings can be added here
            
            self.settings.sync()  # Ensure settings are written to disk
        except Exception as e:
            print(f"Warning: Failed to save user settings: {e}")

    def _ensure_estimator(self):
        """Create an Estimator once, if available. Returns the instance or None."""
        if getattr(self, "estimator", None) is not None:
            return self.estimator
        if Estimator is None or MaterialItem is None:
            self.estimator = None
            return None
        try:
            # Δημιουργία estimator με defaults
            self.estimator = Estimator(scale_factor=self.view.scale_factor)
        except Exception:
            self.estimator = None
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
        
        # Παίρνουμε ρυθμίσεις από το material_settings (αν υπάρχουν)
        koutelou_length = self.material_settings.get('koutelou_length', 2.54)
        plevra_length = self.material_settings.get('plevra_length', 2.54)
        plevra_offset = self.material_settings.get('plevra_offset', 0.5)
        plevra_spacing = self.material_settings.get('plevra_spacing', 1.0)
        gutter_side_type = self.material_settings.get('gutter_side_type', 'full')  # "full" ή "half"
        
        try:
            posts = estimate_triangle_posts_3x5_with_sides(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
            )
            
            # Classification στύλων
            if posts:
                from services.geometry import classify_all_posts
                posts_classified = classify_all_posts(posts, xy, getattr(self.view, 'scale_factor', 5.0))
                if posts_classified:
                    posts["classification"] = posts_classified
        except Exception:
            posts = None
        try:
            gutters = estimate_gutters_length(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
                side_gutter_type=gutter_side_type,
            )
        except Exception:
            gutters = None
        try:
            koutelou = estimate_koutelou_pairs(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
                pipe_length_m=koutelou_length,
            )
        except Exception:
            koutelou = None
        try:
            plevra = estimate_plevra(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
                pipe_length_m=plevra_length,
                first_offset_m=plevra_offset,
                spacing_m=plevra_spacing,
            )
        except Exception:
            plevra = None
        est = self._ensure_estimator()
        if est is not None:
            try:
                bom = est.compute_bom(posts, gutters, koutelou, plevra, grid_h_m=getattr(self.view, 'grid_h_m', 3.0))
                self._update_bom_pane(bom, posts)
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

    def _update_bom_pane(self, bom: BillOfMaterials | None, posts_data: dict | None = None):
        if bom is None:
            return
        try:
            self.bom_tree.blockSignals(True)
            self.bom_tree.clear()
            
            # Αποθήκευση classification για χρήση
            classification = None
            if posts_data and "classification" in posts_data:
                classification = posts_data["classification"]
            
            # Πάρε τα materials από τον estimator για τις επιπλέον ιδιότητες
            est = self._ensure_estimator()
            materials_dict = est.materials if est else {}
            
            for line in bom.lines:
                # Πάρε το material για τις επιπλέον ιδιότητες
                material = materials_dict.get(line.code)
                thickness = material.thickness if material else "-"
                height = material.height if material else "-"
                length = material.length if material else "-"
                
                # Στήλες: Είδος, Πάχος, Ύψος, Μήκος, Μονάδα, Ποσότητα, Τιμή Μονάδας, Υποσύνολο
                item = QTreeWidgetItem([
                    line.name,           # 0: Είδος
                    thickness,           # 1: Πάχος
                    height,              # 2: Ύψος
                    length,              # 3: Μήκος
                    line.unit,           # 4: Μονάδα
                    f"{line.quantity:g}",  # 5: Ποσότητα
                    f"{line.unit_price:.2f}",  # 6: Τιμή Μονάδας
                    f"{line.total:.2f}",     # 7: Υποσύνολο
                ])
                # Αποθήκευση του code για πιθανή μελλοντική χρήση
                item.setData(0, Qt.UserRole, line.code)
                
                # Αν είναι στύλοι και έχουμε classification, προσθήκη υποκατηγοριών
                if classification and line.code in ["post_tall", "post_low"]:
                    post_type = "tall" if line.code == "post_tall" else "low"
                    summary = classification.get("summary", {})
                    
                    # Προσθήκη υποστοιχείων
                    locations = [
                        ("Βόρειοι", f"{post_type}_north"),
                        ("Νότιοι", f"{post_type}_south"),
                        ("Ανατολικοί", f"{post_type}_east"),
                        ("Δυτικοί", f"{post_type}_west"),
                        ("Εσωτερικοί", f"{post_type}_internal"),
                    ]
                    
                    for loc_name, loc_key in locations:
                        count = summary.get(loc_key, 0)
                        if count > 0:
                            child = QTreeWidgetItem([
                                f"  └─ {loc_name}",  # 0: Είδος
                                thickness,           # 1: Πάχος
                                height,              # 2: Ύψος
                                length,              # 3: Μήκος
                                line.unit,           # 4: Μονάδα
                                f"{count:g}",        # 5: Ποσότητα
                                f"{line.unit_price:.2f}",  # 6: Τιμή Μονάδας
                                f"{count * line.unit_price:.2f}",  # 7: Υποσύνολο
                            ])
                            item.addChild(child)
                
                self.bom_tree.addTopLevelItem(item)
            
            self.bom_total_label.setText(f"Σύνολο: {bom.subtotal:.2f} {bom.currency}")
            
            # Αυτόματη προσαρμογή πλάτους στηλών μετά την ενημέρωση
            for i in range(self.bom_tree.columnCount()):
                self.bom_tree.resizeColumnToContents(i)
            
            self.bom_tree.blockSignals(False)
        except Exception:
            try:
                self.bom_tree.blockSignals(False)
            except Exception:
                pass

    def _show_material_settings(self):
        """Εμφανίζει το dialog προσαρμογής υλικών και αποθηκεύει τις ρυθμίσεις."""
        dialog = MaterialSettingsDialog(self)
        
        # Αν υπάρχουν αποθηκευμένες ρυθμίσεις, φόρτωσέ τες στο dialog
        if self.material_settings:
            # Μπορείς να προσθέσεις setter methods στο dialog για να φορτώσεις τις τιμές
            pass
        
        if dialog.exec() == QDialog.Accepted:
            # Αποθήκευση ρυθμίσεων
            self.material_settings = dialog.get_settings()
            
            # Ενημέρωση τιμών υλικών στον estimator
            est = self._ensure_estimator()
            if est is not None:
                settings = self.material_settings
                
                # Ενημέρωση τιμών και ύψους στύλων
                if 'post_tall_price' in settings:
                    if 'post_tall' in est.materials:
                        est.materials['post_tall'].unit_price = settings['post_tall_price']
                
                if 'post_tall_height' in settings:
                    if 'post_tall' in est.materials:
                        height_m = settings['post_tall_height']
                        est.materials['post_tall'].height = f"{int(height_m)}m{int((height_m % 1) * 100):02d}"
                
                if 'post_low_price' in settings:
                    if 'post_low' in est.materials:
                        est.materials['post_low'].unit_price = settings['post_low_price']
                
                if 'post_low_height' in settings:
                    if 'post_low' in est.materials:
                        height_m = settings['post_low_height']
                        est.materials['post_low'].height = f"{int(height_m)}m{int((height_m % 1) * 100):02d}"
                
                if 'gutter_3m_price' in settings:
                    if 'gutter_3m' in est.materials:
                        est.materials['gutter_3m'].unit_price = settings['gutter_3m_price']
                
                if 'gutter_4m_price' in settings:
                    if 'gutter_4m' in est.materials:
                        est.materials['gutter_4m'].unit_price = settings['gutter_4m_price']
                
                # Half gutters (μισές υδρορροές)
                if 'gutter_3m_price' in settings:
                    if 'gutter_3m_half' in est.materials:
                        est.materials['gutter_3m_half'].unit_price = settings['gutter_3m_price'] / 2.0
                
                if 'gutter_4m_price' in settings:
                    if 'gutter_4m_half' in est.materials:
                        est.materials['gutter_4m_half'].unit_price = settings['gutter_4m_price'] / 2.0
                
                if 'koutelou_price' in settings:
                    if 'koutelou_pair' in est.materials:
                        est.materials['koutelou_pair'].unit_price = settings['koutelou_price']
                
                if 'plevra_price' in settings:
                    if 'plevra' in est.materials:
                        est.materials['plevra'].unit_price = settings['plevra_price']
                
                if 'ridge_cap_price' in settings:
                    if 'ridge_cap' in est.materials:
                        est.materials['ridge_cap'].unit_price = settings['ridge_cap_price']
            
            # Επανυπολογισμός BOM με τις νέες ρυθμίσεις
            self._recompute_bom_if_possible()
            
            try:
                self.statusBar().showMessage("Οι ρυθμίσεις υλικών ενημερώθηκαν.", 3000)
            except Exception:
                pass

    def _export_shape_debug(self):
        """Export current shape to JSON for debugging and analysis."""
        if not self._last_xy or len(self._last_xy) < 3:
            QMessageBox.information(self, "Export Shape", "Δεν υπάρχει σχεδιασμένο σχήμα για export.")
            return
        
        # Import corner detection
        from services.geometry import detect_corners
        
        # Συλλογή δεδομένων σχήματος
        shape_data = {
            "corners": list(self._last_xy),
            "num_corners": len(self._last_xy),
            "grid": {
                "grid_w_m": getattr(self.view, 'grid_w_m', 5.0),
                "grid_h_m": getattr(self.view, 'grid_h_m', 3.0),
                "scale_factor": getattr(self.view, 'scale_factor', 5.0),
            },
            "perimeter_m": 0.0,
            "area_m2": 0.0,
        }
        
        # Υπολογισμός περιμέτρου
        perimeter_m = 0.0
        for i in range(len(self._last_xy)):
            p1 = self._last_xy[i]
            p2 = self._last_xy[(i + 1) % len(self._last_xy)]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            perimeter_m += ((dx**2 + dy**2) ** 0.5) / shape_data["grid"]["scale_factor"]
        shape_data["perimeter_m"] = round(perimeter_m, 2)
        
        # Υπολογισμός εμβαδού (shoelace)
        area_px2 = 0.0
        for i in range(len(self._last_xy)):
            p1 = self._last_xy[i]
            p2 = self._last_xy[(i + 1) % len(self._last_xy)]
            area_px2 += p1[0] * p2[1] - p2[0] * p1[1]
        area_px2 = abs(area_px2) * 0.5
        area_m2 = area_px2 / (shape_data["grid"]["scale_factor"] ** 2)
        shape_data["area_m2"] = round(area_m2, 2)
        
        # Εντοπισμός γωνιών
        try:
            corner_analysis = detect_corners(self._last_xy)
            shape_data["corner_analysis"] = {
                "internal_corners": corner_analysis.get("internal_corners", []),
                "external_corners": corner_analysis.get("external_corners", []),
                "num_internal": len(corner_analysis.get("internal_corners", [])),
                "num_external": len(corner_analysis.get("external_corners", [])),
            }
        except Exception:
            shape_data["corner_analysis"] = None
        
        # Διαλογος αποθήκευσης
        fname, _ = QFileDialog.getSaveFileName(
            self,
            "Export Shape Debug",
            f"shape_debug.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not fname:
            return
        
        try:
            import json
            with open(fname, 'w', encoding='utf-8') as f:
                json.dump(shape_data, f, indent=2, ensure_ascii=False)
            
            corner_info = ""
            if shape_data.get("corner_analysis"):
                ca = shape_data["corner_analysis"]
                corner_info = f"\nΕσωτερικές γωνίες: {ca['num_internal']}\nΕξωτερικές γωνίες: {ca['num_external']}"
            
            QMessageBox.information(
                self,
                "Export Shape",
                f"Το σχήμα αποθηκεύτηκε στο:\n{fname}\n\n"
                f"Γωνίες: {shape_data['num_corners']}\n"
                f"Περίμετρος: {shape_data['perimeter_m']:.2f} m\n"
                f"Εμβαδόν: {shape_data['area_m2']:.2f} m²{corner_info}"
            )
            
            try:
                self.statusBar().showMessage(f"Shape exported to {Path(fname).name}", 5000)
            except Exception:
                pass
                
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία αποθήκευσης: {e}")

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
        
        # Max zoom out setting
        act_max_zoom = QAction("Μέγιστο Όριο Zoom Out…", self)
        act_max_zoom.triggered.connect(self._settings_max_zoom)
        settings.addAction(act_max_zoom)
        
        # Autosave toggle
        self.act_autosave = QAction("Αυτόματη Αποθήκευση", self)
        self.act_autosave.setCheckable(True)
        self.act_autosave.setChecked(self._autosave_enabled)
        self.act_autosave.triggered.connect(self._toggle_autosave)
        settings.addAction(self.act_autosave)
        
        # Export Shape Debug
        settings.addSeparator()
        act_export_shape = QAction("Export Shape (JSON Debug)…", self)
        act_export_shape.triggered.connect(self._export_shape_debug)
        settings.addAction(act_export_shape)

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
        
        # Καθαρισμός των panels υπολογισμών
        try:
            self.bom_tree.clear()
            self.bom_total_label.setText("Σύνολο: 0.00 EUR")
        except Exception:
            pass
        
        try:
            self.info_tree.clear()
        except Exception:
            pass
        
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
            # Use last directory if available
            start_dir = str(self._last_directory) if self._last_directory else str(Path.cwd())
            fname, _ = QFileDialog.getOpenFileName(self, "Φόρτωση Μελέτης", start_dir, f"Greenhouse Project (*{PROJECT_EXT});;Όλα τα αρχεία (*)")
            if not fname:
                return False
            path = Path(fname)
            # Remember this directory
            self._last_directory = path.parent
            self._save_user_settings()
            
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
            # Use last directory if available
            start_dir = self._last_directory if self._last_directory else self._projects_dir_path()
            fname, _ = QFileDialog.getSaveFileName(self, "Αποθήκευση Μελέτης ως…", str(start_dir / suggested), f"Greenhouse Project (*{PROJECT_EXT});;Όλα τα αρχεία (*)")
            if not fname:
                return False
            path = Path(fname)
            if path.suffix.lower() != PROJECT_EXT:
                path = path.with_suffix(PROJECT_EXT)
            
            # Remember this directory
            self._last_directory = path.parent
            self._save_user_settings()
            
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
        
        # Παίρνουμε ρυθμίσεις από το material_settings (αν υπάρχουν)
        koutelou_length = self.material_settings.get('koutelou_length', 2.54)
        plevra_length = self.material_settings.get('plevra_length', 2.54)
        plevra_offset = self.material_settings.get('plevra_offset', 0.5)
        plevra_spacing = self.material_settings.get('plevra_spacing', 1.0)
        gutter_side_type = self.material_settings.get('gutter_side_type', 'full')  # "full" ή "half"
        
        try:
            posts = estimate_triangle_posts_3x5_with_sides(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
            )
            
            # Classification στύλων
            if posts:
                from services.geometry import classify_all_posts
                posts_classified = classify_all_posts(posts, xy, getattr(self.view, 'scale_factor', 5.0))
                if posts_classified:
                    posts["classification"] = posts_classified
        except Exception:
            posts = None
        try:
            gutters = estimate_gutters_length(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
                side_gutter_type=gutter_side_type,
            )
        except Exception:
            gutters = None
        try:
            koutelou = estimate_koutelou_pairs(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
                pipe_length_m=koutelou_length,
            )
        except Exception:
            koutelou = None
        try:
            plevra = estimate_plevra(
                xy,
                grid_w_m=getattr(self.view, 'grid_w_m', 5.0),
                grid_h_m=getattr(self.view, 'grid_h_m', 3.0),
                scale_factor=self.view.scale_factor,
                pipe_length_m=plevra_length,
                first_offset_m=plevra_offset,
                spacing_m=plevra_spacing,
            )
        except Exception:
            plevra = None
        est = self._ensure_estimator()
        if est is not None:
            try:
                bom = est.compute_bom(posts, gutters, koutelou, plevra, grid_h_m=getattr(self.view, 'grid_h_m', 3.0))
                self._update_bom_pane(bom, posts)
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
