from PySide6.QtGui import QPalette, QColor, QDoubleValidator
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
    QPushButton,
    QHBoxLayout,
    QFileDialog,
    QStyledItemDelegate,
    QLineEdit,
    QToolButton,
    QMenu,
)
from PySide6.QtCore import Qt
from services.estimator import Estimator, default_material_catalog
from services.models import MaterialItem, BillOfMaterials
from ui.drawing_view import DrawingView
from PySide6.QtGui import QAction, QActionGroup
from ui.column_height_dialog import ColumnHeightDialog
from services.geometry_utils import (
    compute_grid_coverage as geom_compute_grid_coverage,
    estimate_triangle_posts_3x5_with_sides,
    estimate_gutters_length,
)
from pathlib import Path
import csv

class PriceOnlyDelegate(QStyledItemDelegate):
    """Delegate that allows editing only for the Unit Price column (index 3)."""
    def createEditor(self, parent, option, index):
        if index.column() == 3:
            editor = QLineEdit(parent)
            editor.setValidator(QDoubleValidator(0.0, 1e12, 4, parent))
            return editor
        return None

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

        # Create toolbar first, then docks so toggles can be added
        self._create_toolbar()
        # Create BOM dock then info dock, then stack them on the right
        self._create_bom_dock()
        self._create_info_dock()
        self.view.perimeter_closed.connect(self._on_perimeter_closed)
        self._last_xy = None  # cache last perimeter points for optional recompute
        # Ensure estimator (and user defaults) are loaded immediately at startup
        try:
            self._ensure_estimator()
        except Exception:
            pass

    def _create_toolbar(self):
        self.toolbar = QToolBar("Εργαλεία", self)
        self.addToolBar(self.toolbar)

        # OSnap
        osnap_act = QAction("OSnap", self)
        osnap_act.setCheckable(True)
        osnap_act.setChecked(True)
        osnap_act.toggled.connect(self.view.toggle_osnap_mode)
        self.toolbar.addAction(osnap_act)
        self.toolbar.addSeparator()

        # Κατάσταση λειτουργίας (αμοιβαία αποκλειόμενες)
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)
        modes = [
            ("Δείκτης",      self.view.toggle_pointer_mode),
            ("Πολυγραμμή",   self.view.toggle_polyline_mode),
            ("Οδηγοί",       self.view.toggle_guide_mode),
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

        # Άλλα εργαλεία
        tools = [
            ("Αναίρεση",            self.view.undo,            "Ctrl+Z"),
            ("Επανάληψη",           self.view.redo,            "Ctrl+Y"),
            ("Διαγραφή",            self.view.delete_selected, "Del"),
            ("Διαγραφή όλων",       self._clear_all_and_reset, None),
            ("Κλείσιμο Περιμέτρου", self._close_perimeter,     None),
            ("Διαγραφή Οδηγών",     self.view.clear_guides,    None),
        ]
        for label, handler, shortcut in tools:
            act = QAction(label, self)
            act.setObjectName(label)
            if shortcut:
                act.setShortcut(shortcut)
            act.triggered.connect(handler)
            self.toolbar.addAction(act)

        # Ύψη κολόνων (διάλογος)
        column_height_action = QAction("Ύψη Κολόνων", self)
        column_height_action.triggered.connect(self._set_column_heights)
        self.toolbar.addAction(column_height_action)

        # Επιλογή τύπου/πλέγματος θερμοκηπίου
        self.grid_selector = QComboBox(self)
        self.grid_selector.setObjectName("GreenhouseTypeSelector")
        # Presets: label -> (grid_w_m, grid_h_m)
        self._grid_presets = {
            "3x5 με πλευρές (5x3 m)": (5.0, 3.0),
            "5x4 (5x4 m)": (5.0, 4.0),
            "4x4 (4x4 m)": (4.0, 4.0),
            "Προσαρμοσμένο…": None,
        }
        for label in self._grid_presets.keys():
            self.grid_selector.addItem(label)
        # Set default to 5x3
        self.grid_selector.setCurrentIndex(0)
        self.grid_selector.currentTextChanged.connect(self._on_grid_selector_changed)
        self.toolbar.addWidget(self.grid_selector)

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
        act_save_user_defaults = QAction("Ορισμός ως Προεπιλογές", self)
        act_save_user_defaults.triggered.connect(self._save_user_defaults)
        menu.addAction(act_save_user_defaults)

        act_reset = QAction("Επαναφορά Προεπιλογών", self)
        act_reset.triggered.connect(self._reset_prices_to_defaults)
        menu.addAction(act_reset)

        act_factory_reset = QAction("Επαναφορά Εργοστασιακών", self)
        act_factory_reset.triggered.connect(self._factory_reset)
        menu.addAction(act_factory_reset)

        self.prices_button.setMenu(menu)
        self.toolbar.addWidget(self.prices_button)

    def _create_bom_dock(self):
        self.bom_dock = QDockWidget("Υλικά & Κόστος", self)
        self.bom_dock.setObjectName("MaterialsCostDock")
        container = QWidget(self.bom_dock)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)

        self.bom_tree = QTreeWidget(container)
        self.bom_tree.setColumnCount(6)
        self.bom_tree.setHeaderLabels(["Είδος", "Μονάδα", "Ποσότητα", "Τιμή Μονάδας", "Σύνολο", "Κατάσταση"]) 
        self.bom_tree.setRootIsDecorated(False)
        self.bom_tree.setItemDelegate(PriceOnlyDelegate(self.bom_tree))
        self.bom_tree.itemChanged.connect(self._on_bom_item_changed)
        layout.addWidget(self.bom_tree)

        self.bom_total_label = QLabel("Υποσύνολο: 0.00 EUR", container)
        layout.addWidget(self.bom_total_label)

        self.price_source_label = QLabel("Αρχείο τιμών: Προεπιλογές", container)
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
            self.view.viewport().update()
        except Exception:
            pass
        # Optionally recompute BOM and info if a perimeter exists (using cached xy)
        self._recompute_bom_if_possible()
        self._recompute_info_if_possible()

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
            # Ξαναφορτώνουμε defaults + user defaults (αν υπάρχουν)
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
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία επαναφοράς προεπιλογών: {e}")


    def _materials_file_path(self) -> Path:
        # Legacy JSON default path in repo root
        try:
            return Path(__file__).resolve().parent.parent / "materials.json"
        except Exception:
            return Path.cwd() / "materials.json"

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
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία επαναφοράς εργοστασιακών: {e}")

    # JSON-based materials are no longer supported; only embedded defaults + CSV overrides are used.

    def _load_materials_from_csv_disk(self) -> dict:
        path = self._materials_csv_path()
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

    # JSON import/export removed: only CSV import + embedded defaults supported.

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

    # Επαναφόρτωση αφαιρέθηκε: η εκκίνηση δεν φορτώνει αυτόματα CSV πλέον.