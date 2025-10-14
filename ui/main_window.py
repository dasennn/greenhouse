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
    QPushButton,
    QHBoxLayout,
    QFileDialog,
)
from PySide6.QtCore import Qt
from services.estimator import Estimator
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
import json
import csv

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

        # Create toolbar first, then docks so toggles can be added
        self._create_toolbar()
        # Create BOM dock then info dock, then stack them on the right
        self._create_bom_dock()
        self._create_info_dock()
        self.view.perimeter_closed.connect(self._on_perimeter_closed)
        self._last_xy = None  # cache last perimeter points for optional recompute

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

        # Εισαγωγή τιμών από CSV (νέο)
        import_csv_action = QAction("Εισαγωγή Τιμών (CSV)", self)
        import_csv_action.setObjectName("ImportCSVPrices")
        import_csv_action.triggered.connect(self._import_prices_csv_dialog)
        self.toolbar.addAction(import_csv_action)

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
        # Add initially to right area and stack with BOM dock
        self.addDockWidget(Qt.RightDockWidgetArea, self.info_dock)
        try:
            # Stack info_dock above the BOM dock (vertical split)
            self.splitDockWidget(self.bom_dock, self.info_dock, Qt.Vertical)
        except Exception:
            # Fallback: leave both docks in the right area
            pass
        # Toolbar toggle for info dock
        try:
            info_toggle = self.info_dock.toggleViewAction()
            info_toggle.setText("Πάνελ Στοιχείων Σχεδίου")
            self.toolbar.addAction(info_toggle)
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
        self.bom_tree.setHeaderLabels(["Είδος", "Μονάδα", "Ποσότητα", "Τιμή Μονάδας", "Σύνολο", "Κατάσταση"]) 
        self.bom_tree.setRootIsDecorated(False)
        # Θα επιτρέψουμε edit στο πεδίο τιμής (στήλη 3)
        self.bom_tree.itemChanged.connect(self._on_bom_item_changed)
        layout.addWidget(self.bom_tree)

        self.bom_total_label = QLabel("Υποσύνολο: 0.00 EUR", container)
        layout.addWidget(self.bom_total_label)

        container.setLayout(layout)
        self.bom_dock.setWidget(container)
        self.addDockWidget(Qt.RightDockWidgetArea, self.bom_dock)
        # Add a toolbar toggle to show/hide this dock
        try:
            toggle_action = self.bom_dock.toggleViewAction()
            toggle_action.setText("Πάνελ Υλικών & Κόστους")
            self.toolbar.addAction(toggle_action)
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
            # Φόρτωση τιμών από CSV (αν υπάρχει), αλλιώς JSON (παλαιό)
            # Πάντα εκκίνηση με defaults και συγχώνευση των φορτωμένων, ώστε να μη χαθούν υλικά που δεν υπάρχουν στο αρχείο (π.χ. ridge_cap)
            loaded_materials = self._load_materials_from_csv_disk()
            if not loaded_materials:
                loaded_materials = self._load_materials_from_disk()
            # Δημιουργία estimator με defaults
            self.estimator = Estimator(scale_factor=self.view.scale_factor)
            # Συγχώνευση τιμών χρήστη πάνω από τα defaults
            if loaded_materials:
                self.estimator.materials.update(loaded_materials)
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
                # Επιτρέπουμε edit σε όλο το item, αλλά θα χειριστούμε μόνο τη στήλη 3
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.bom_tree.addTopLevelItem(item)
            self.bom_total_label.setText(f"Υποσύνολο: {bom.subtotal:.2f} {bom.currency}")
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
            txt = item.text(3).strip().replace(",", ".")
            new_price = float(txt) if txt else 0.0
            # Ενημέρωση υλικού στον estimator
            mat = est.materials.get(code)
            if mat is None:
                est.materials[code] = MaterialItem(code=code, name=item.text(0), unit=item.text(1), unit_price=new_price)
            else:
                mat.unit_price = new_price
                # Συγχρονίζουμε προαιρετικά name/unit από στήλες (αν αλλάξουν)
                mat.name = item.text(0)
                mat.unit = item.text(1)
            # Αναυπολογισμός γραμμής και υποσυνόλου
            try:
                qty = float(item.text(2)) if item.text(2) else 0.0
            except Exception:
                qty = 0.0
            total = qty * new_price
            self.bom_tree.blockSignals(True)
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

    def _load_materials_from_disk(self) -> dict:
        path = self._materials_file_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            materials = {}
            for code, info in data.items():
                materials[code] = MaterialItem(
                    code=code,
                    name=info.get('name', code),
                    unit=info.get('unit', 'piece'),
                    unit_price=float(info.get('unit_price', 0.0)),
                )
            return materials
        except Exception:
            return {}

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
            # Φόρτωση CSV
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                loaded_codes = set()
                error_codes = set()
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
                        unit_price = None
                    if unit_price is None:
                        error_codes.add(code)
                        continue
                    materials[code] = MaterialItem(code=code, name=name, unit=unit, unit_price=unit_price)
                    loaded_codes.add(code)

            est = self._ensure_estimator()
            if est is None:
                return

            if materials:
                # Συγχώνευση με τα ήδη υπάρχοντα (κρατάμε defaults και ενημερώνουμε/προσθέτουμε όσα υπάρχουν στο CSV)
                est.materials.update(materials)
                self._last_loaded_codes = loaded_codes
                self._last_loaded_errors = error_codes
                self._recompute_bom_if_possible()
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

    def _save_materials_json(self):
        est = self._ensure_estimator()
        if est is None:
            return
        path = self._materials_file_path()
        try:
            # Προαιρετικό backup
            if path.exists():
                backup = path.with_suffix('.json.bak')
                try:
                    backup.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
                except Exception:
                    pass
            data = {}
            for code, m in est.materials.items():
                data[code] = {
                    'name': m.name,
                    'unit': m.unit,
                    'unit_price': float(m.unit_price or 0.0),
                }
            tmp = path.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            tmp.replace(path)
            try:
                self.statusBar().showMessage(f"Αποθηκεύτηκαν οι τιμές στο {path.name}", 5000)
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία αποθήκευσης τιμών: {e}")

    def _load_materials_json(self):
        # Άνοιγμα διαλόγου αρχείου και φόρτωση από επιλεγμένο JSON
        try:
            fname, _ = QFileDialog.getOpenFileName(
                self,
                "Επιλογή αρχείου τιμών (JSON)",
                str(self._materials_file_path().parent),
                "JSON αρχεία (*.json);;Όλα τα αρχεία (*)",
            )
            if not fname:
                return
            path = Path(fname)
            if not path.exists():
                QMessageBox.warning(self, "Σφάλμα", "Το αρχείο δεν υπάρχει.")
                return
            # Διάβασε και επικύρωσε δεδομένα
            raw = json.loads(path.read_text(encoding='utf-8'))
            loaded_codes = set()
            error_codes = set()
            materials = {}
            for code, info in (raw.items() if isinstance(raw, dict) else []):
                try:
                    unit_price = float(info.get('unit_price', 0.0))
                except Exception:
                    error_codes.add(code)
                    continue
                materials[code] = MaterialItem(
                    code=code,
                    name=info.get('name', code),
                    unit=info.get('unit', 'piece'),
                    unit_price=unit_price,
                )
                loaded_codes.add(code)

            est = self._ensure_estimator()
            if est is None:
                return

            if materials:
                # Συγχώνευση με τα ήδη υπάρχοντα (κρατάμε defaults και ενημερώνουμε/προσθέτουμε όσα υπάρχουν στο JSON)
                est.materials.update(materials)
                # Αποθήκευση status σε ιδιότητες για εμφάνιση στη στήλη "Κατάσταση"
                self._last_loaded_codes = loaded_codes
                self._last_loaded_errors = error_codes
                # Επανυπολογισμός BOM
                self._recompute_bom_if_possible()
                # Περίληψη αποτελεσμάτων
                updated_list = sorted(list(loaded_codes - error_codes))
                error_list = sorted(list(error_codes))
                # Μήνυμα περίληψης
                msg = [
                    f"Ενημερώθηκαν: {len(updated_list)}",
                    f"Με σφάλμα: {len(error_list)}",
                ]
                if updated_list:
                    msg.append("\nΚωδικοί ενημερώθηκαν (ενδεικτικά): " + ", ".join(updated_list[:10]) + (" …" if len(updated_list) > 10 else ""))
                if error_list:
                    msg.append("Κωδικοί με σφάλμα: " + ", ".join(error_list[:10]) + (" …" if len(error_list) > 10 else ""))
                QMessageBox.information(self, "Φόρτωση Τιμών", "\n".join(msg))
                try:
                    self.statusBar().showMessage(f"Φορτώθηκαν τιμές από: {path.name}", 5000)
                except Exception:
                    pass
            else:
                QMessageBox.information(self, "Φόρτωση Τιμών", "Δεν βρέθηκαν έγκυρες τιμές στο αρχείο.")
        except Exception as e:
            QMessageBox.warning(self, "Σφάλμα", f"Αποτυχία φόρτωσης τιμών: {e}")

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