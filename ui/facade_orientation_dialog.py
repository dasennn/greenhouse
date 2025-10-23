"""Dialog για επεξεργασία προσανατολισμών πλευρών."""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QListView,
    QPushButton,
    QHeaderView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


ORIENTATIONS = ["Βόρεια", "Νότια", "Ανατολική", "Δυτική"]
COLORS = {
    "Βόρεια": "#0077FF",
    "Νότια": "#E53935",
    "Ανατολική": "#8E24AA",
    "Δυτική": "#2E7D32",
}


class FacadeOrientationDialog(QDialog):
    """Dialog για προβολή και επεξεργασία προσανατολισμών."""
    
    row_selected = Signal(int)  # Εκπέμπεται όταν επιλέγεται γραμμή
    
    def __init__(self, segments, scale_factor=5.0, parent=None):
        super().__init__(parent)
        self.segments = segments
        self.scale_factor = scale_factor
        self.setWindowTitle("Προσανατολισμός Πλευρών")
        self.resize(900, 500)
        
        layout = QVBoxLayout(self)
        
        # Οδηγίες
        label = QLabel(
            "Επέλεξε μία πλευρά και άλλαξε τον προσανατολισμό της. "
            "Το χρώμα ενημερώνεται μετά την αποθήκευση."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        
        # Πίνακας
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "#", "Από (x, y)", "Προς (x, y)", "Μήκος (m)", "Γωνία (°)", "Προσανατολισμός"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        
        self._populate_table()
        
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        
        layout.addWidget(self.table)
        
        # Κουμπιά
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("Αποθήκευση")
        save_btn.clicked.connect(self.accept)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Άκυρο")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _populate_table(self):
        """Γέμισμα πίνακα με δεδομένα."""
        self.table.setRowCount(len(self.segments))
        
        for row, seg in enumerate(self.segments):
            idx = seg.get("index", row)
            start = seg.get("start", [0, 0])
            end = seg.get("end", [0, 0])
            length_px = seg.get("length", 0.0)
            length_m = length_px / self.scale_factor
            angle = seg.get("angle", 0.0)
            orientation = seg.get("orientation", "Ανατολική")
            
            # Στήλη #
            self.table.setItem(row, 0, QTableWidgetItem(str(idx + 1)))
            
            # Στήλη Από
            self.table.setItem(row, 1, QTableWidgetItem(f"({start[0]:.0f}, {start[1]:.0f})"))
            
            # Στήλη Προς
            self.table.setItem(row, 2, QTableWidgetItem(f"({end[0]:.0f}, {end[1]:.0f})"))
            
            # Στήλη Μήκος
            self.table.setItem(row, 3, QTableWidgetItem(f"{length_m:.2f}"))
            
            # Στήλη Γωνία
            self.table.setItem(row, 4, QTableWidgetItem(f"{angle:.1f}"))
            
            # Στήλη Προσανατολισμός (ComboBox)
            combo = QComboBox()
            combo.addItems(ORIENTATIONS)
            combo.setCurrentText(orientation)
            combo.currentTextChanged.connect(lambda text, r=row: self._on_combo_changed(r, text))
            self._style_combo(combo, orientation)
            self.table.setCellWidget(row, 5, combo)
    
    def _style_combo(self, combo, orientation):
        """Στυλ ComboBox: λευκό φόντο/μαύρα γράμματα τόσο κλειστό όσο και στο dropdown."""
        # Dropdown (popup) με custom QListView για συνεπή εμφάνιση
        view = QListView()
        view.setStyleSheet(
            "QListView { background: white; color: black; }"
            "QListView::item { color: black; }"
            "QListView::item:selected { background: #E0E0E0; color: black; }"
        )
        combo.setView(view)
        # Καθαρισμός per-item roles
        for i, _ in enumerate(ORIENTATIONS):
            combo.setItemData(i, None, Qt.ForegroundRole)
            combo.setItemData(i, None, Qt.BackgroundRole)
        # Κλειστό combobox: ουδέτερο (λευκό/μαύρο), χωρίς εξωτερικά χρώματα
        combo.setStyleSheet(
            "QComboBox { background-color: white; color: black; font-weight: bold; }"
            "QComboBox::drop-down { width: 24px; }"
        )
    
    def _on_combo_changed(self, row, text):
        """Όταν αλλάζει το combo, ενημέρωσε το style."""
        combo = self.table.cellWidget(row, 5)
        if combo:
            self._style_combo(combo, text)
        # Επιλογή γραμμής
        self.table.selectRow(row)
    
    def _on_selection_changed(self):
        """Όταν αλλάζει η επιλογή γραμμής."""
        row = self.table.currentRow()
        if 0 <= row < len(self.segments):
            idx = self.segments[row].get("index", row)
            self.row_selected.emit(idx)
    
    def get_updated_segments(self):
        """Επιστρέφει τα ενημερωμένα segments."""
        updated = []
        for row, seg in enumerate(self.segments):
            combo = self.table.cellWidget(row, 5)
            if combo:
                orientation = combo.currentText()
                seg_copy = dict(seg)
                seg_copy["orientation"] = orientation
                seg_copy["color"] = COLORS.get(orientation, "#CCCCCC")
                updated.append(seg_copy)
            else:
                updated.append(seg)
        return updated
