"""Material settings dialog for customizing material parameters and prices."""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QDoubleSpinBox,
    QComboBox,
    QLabel,
    QPushButton,
    QDialogButtonBox,
    QScrollArea,
    QWidget,
)
from PySide6.QtCore import Qt, Signal


class MaterialSettingsDialog(QDialog):
    """Dialog for customizing material parameters and prices."""
    
    settings_changed = Signal(dict)
    
    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Προσαρμογή Υλικών")
        self.setMinimumWidth(600)
        self.setMinimumHeight(700)
        
        self.current_settings = current_settings or {}
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Scroll area for settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # === Στύλοι ===
        posts_group = QGroupBox("Στύλοι")
        posts_layout = QFormLayout()
        
        # Πάχος σωλήνα στύλων
        self.post_thickness = QComboBox()
        self.post_thickness.addItems([
            '2" (50.8 mm)',
            '1.5" (38.1 mm)',
            '1" (25.4 mm)',
        ])
        self.post_thickness.setCurrentIndex(0)  # Default: 2"
        posts_layout.addRow("Πάχος Σωλήνα:", self.post_thickness)
        
        posts_layout.addRow(QLabel(""))  # Spacer
        
        self.post_tall_height = QDoubleSpinBox()
        self.post_tall_height.setRange(0.1, 50.0)
        self.post_tall_height.setDecimals(2)
        self.post_tall_height.setSuffix(" m")
        self.post_tall_height.setValue(3.0)
        posts_layout.addRow("Ύψος Ψηλού Στύλου:", self.post_tall_height)
        
        self.post_low_height = QDoubleSpinBox()
        self.post_low_height.setRange(0.1, 50.0)
        self.post_low_height.setDecimals(2)
        self.post_low_height.setSuffix(" m")
        self.post_low_height.setValue(2.0)
        posts_layout.addRow("Ύψος Χαμηλού Στύλου:", self.post_low_height)
        
        self.post_tall_price = QDoubleSpinBox()
        self.post_tall_price.setRange(0.0, 10000.0)
        self.post_tall_price.setDecimals(2)
        self.post_tall_price.setSuffix(" EUR")
        self.post_tall_price.setValue(18.50)
        posts_layout.addRow("Τιμή Ψηλού Στύλου:", self.post_tall_price)
        
        self.post_low_price = QDoubleSpinBox()
        self.post_low_price.setRange(0.0, 10000.0)
        self.post_low_price.setDecimals(2)
        self.post_low_price.setSuffix(" EUR")
        self.post_low_price.setValue(12.90)
        posts_layout.addRow("Τιμή Χαμηλού Στύλου:", self.post_low_price)
        
        posts_group.setLayout(posts_layout)
        scroll_layout.addWidget(posts_group)
        
        # === Υδρορροές ===
        gutters_group = QGroupBox("Υδρορροές")
        gutters_layout = QFormLayout()
        
        # Πάχος σωλήνα υδρορροών
        self.gutter_thickness = QComboBox()
        self.gutter_thickness.addItems([
            '2" (50.8 mm)',
            '1.5" (38.1 mm)',
            '1" (25.4 mm)',
        ])
        self.gutter_thickness.setCurrentIndex(0)  # Default: 2"
        gutters_layout.addRow("Πάχος Σωλήνα:", self.gutter_thickness)
        
        gutters_layout.addRow(QLabel(""))  # Spacer
        
        self.gutter_side_type = QComboBox()
        self.gutter_side_type.addItems(["Ολόκληρες", "Μισές"])
        self.gutter_side_type.setCurrentIndex(0)
        gutters_layout.addRow("Πλαϊνές Υδρορροές:", self.gutter_side_type)
        
        self.gutter_3m_price = QDoubleSpinBox()
        self.gutter_3m_price.setRange(0.0, 10000.0)
        self.gutter_3m_price.setDecimals(2)
        self.gutter_3m_price.setSuffix(" EUR")
        self.gutter_3m_price.setValue(9.80)
        gutters_layout.addRow("Τιμή Υδρορροής 3m:", self.gutter_3m_price)
        
        self.gutter_4m_price = QDoubleSpinBox()
        self.gutter_4m_price.setRange(0.0, 10000.0)
        self.gutter_4m_price.setDecimals(2)
        self.gutter_4m_price.setSuffix(" EUR")
        self.gutter_4m_price.setValue(12.40)
        gutters_layout.addRow("Τιμή Υδρορροής 4m:", self.gutter_4m_price)
        
        gutters_group.setLayout(gutters_layout)
        scroll_layout.addWidget(gutters_group)
        
        # === Ζεύγη Κουτελού ===
        koutelou_group = QGroupBox("Ζεύγη Κουτελού")
        koutelou_layout = QFormLayout()
        
        # Πάχος σωλήνα κουτελού
        self.koutelou_thickness = QComboBox()
        self.koutelou_thickness.addItems([
            '1" (25.4 mm)',
            '1.5" (38.1 mm)',
            '2" (50.8 mm)',
        ])
        self.koutelou_thickness.setCurrentIndex(0)  # Default: 1"
        koutelou_layout.addRow("Πάχος Σωλήνα:", self.koutelou_thickness)
        
        koutelou_layout.addRow(QLabel(""))  # Spacer
        
        self.koutelou_length = QDoubleSpinBox()
        self.koutelou_length.setRange(0.1, 50.0)
        self.koutelou_length.setDecimals(2)
        self.koutelou_length.setSuffix(" m")
        self.koutelou_length.setValue(2.54)
        koutelou_layout.addRow("Μήκος Ζεύγους:", self.koutelou_length)
        
        self.koutelou_price = QDoubleSpinBox()
        self.koutelou_price.setRange(0.0, 10000.0)
        self.koutelou_price.setDecimals(2)
        self.koutelou_price.setSuffix(" EUR")
        self.koutelou_price.setValue(8.50)
        koutelou_layout.addRow("Τιμή ανά Ζεύγος:", self.koutelou_price)
        
        koutelou_group.setLayout(koutelou_layout)
        scroll_layout.addWidget(koutelou_group)
        
        # === Πλευρά ===
        plevra_group = QGroupBox("Πλευρά")
        plevra_layout = QFormLayout()
        
        # Πάχος σωλήνα πλευρών
        self.plevra_thickness = QComboBox()
        self.plevra_thickness.addItems([
            '1" (25.4 mm)',
            '1.5" (38.1 mm)',
            '2" (50.8 mm)',
        ])
        self.plevra_thickness.setCurrentIndex(0)  # Default: 1"
        plevra_layout.addRow("Πάχος Σωλήνα:", self.plevra_thickness)
        
        plevra_layout.addRow(QLabel(""))  # Spacer
        
        self.plevra_length = QDoubleSpinBox()
        self.plevra_length.setRange(0.1, 50.0)
        self.plevra_length.setDecimals(2)
        self.plevra_length.setSuffix(" m")
        self.plevra_length.setValue(2.54)
        plevra_layout.addRow("Μήκος Πλευρού:", self.plevra_length)
        
        self.plevra_offset = QDoubleSpinBox()
        self.plevra_offset.setRange(0.0, 10.0)
        self.plevra_offset.setDecimals(2)
        self.plevra_offset.setSuffix(" m")
        self.plevra_offset.setValue(0.5)
        plevra_layout.addRow("Απόσταση από Προσόψεις:", self.plevra_offset)
        
        self.plevra_spacing = QDoubleSpinBox()
        self.plevra_spacing.setRange(0.1, 10.0)
        self.plevra_spacing.setDecimals(2)
        self.plevra_spacing.setSuffix(" m")
        self.plevra_spacing.setValue(1.0)
        plevra_layout.addRow("Απόσταση Μεταξύ Πλευρών:", self.plevra_spacing)
        
        self.plevra_price = QDoubleSpinBox()
        self.plevra_price.setRange(0.0, 10000.0)
        self.plevra_price.setDecimals(2)
        self.plevra_price.setSuffix(" EUR")
        self.plevra_price.setValue(6.50)
        plevra_layout.addRow("Τιμή ανά Πλευρό:", self.plevra_price)
        
        plevra_group.setLayout(plevra_layout)
        scroll_layout.addWidget(plevra_group)
        
        # === Κορφιάτες ===
        ridge_group = QGroupBox("Κορφιάτες")
        ridge_layout = QFormLayout()
        
        # Πάχος σωλήνα κορφιατών
        self.ridge_thickness = QComboBox()
        self.ridge_thickness.addItems([
            '2" (50.8 mm)',
            '1.5" (38.1 mm)',
            '1" (25.4 mm)',
        ])
        self.ridge_thickness.setCurrentIndex(0)  # Default: 2"
        ridge_layout.addRow("Πάχος Σωλήνα:", self.ridge_thickness)
        
        ridge_layout.addRow(QLabel(""))  # Spacer
        
        self.ridge_price = QDoubleSpinBox()
        self.ridge_price.setRange(0.0, 10000.0)
        self.ridge_price.setDecimals(2)
        self.ridge_price.setSuffix(" EUR")
        self.ridge_price.setValue(7.20)
        ridge_layout.addRow("Τιμή ανά Κορφιάτη:", self.ridge_price)
        
        ridge_group.setLayout(ridge_layout)
        scroll_layout.addWidget(ridge_group)
        
        # === Σωλήνες Καλλιέργειας ===
        cultivation_group = QGroupBox("Σωλήνες Καλλιέργειας")
        cultivation_layout = QFormLayout()
        
        # Πάχος σωλήνα καλλιέργειας
        self.cultivation_thickness = QComboBox()
        self.cultivation_thickness.addItems([
            '1" (25.4 mm)',
            '1.5" (38.1 mm)',
            '2" (50.8 mm)',
        ])
        self.cultivation_thickness.setCurrentIndex(0)  # Default: 1"
        cultivation_layout.addRow("Πάχος Σωλήνα:", self.cultivation_thickness)
        
        cultivation_layout.addRow(QLabel(""))  # Spacer
        
        self.cultivation_pipe_length = QDoubleSpinBox()
        self.cultivation_pipe_length.setRange(0.1, 50.0)
        self.cultivation_pipe_length.setDecimals(2)
        self.cultivation_pipe_length.setSuffix(" m")
        self.cultivation_pipe_length.setValue(5.0)
        cultivation_layout.addRow("Μήκος Σωλήνα:", self.cultivation_pipe_length)
        
        self.cultivation_pipe_price = QDoubleSpinBox()
        self.cultivation_pipe_price.setRange(0.0, 10000.0)
        self.cultivation_pipe_price.setDecimals(2)
        self.cultivation_pipe_price.setSuffix(" EUR")
        self.cultivation_pipe_price.setValue(8.00)
        cultivation_layout.addRow("Τιμή ανά Σωλήνα:", self.cultivation_pipe_price)
        
        cultivation_group.setLayout(cultivation_layout)
        scroll_layout.addWidget(cultivation_group)
        
        # Stretch at the end
        scroll_layout.addStretch()
        
        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply | QDialogButtonBox.RestoreDefaults
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.Apply).clicked.connect(self._apply_settings)
        button_box.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)
        
        # Customize button text to Greek
        button_box.button(QDialogButtonBox.Apply).setText("Εφαρμογή")
        button_box.button(QDialogButtonBox.Ok).setText("OK")
        button_box.button(QDialogButtonBox.Cancel).setText("Άκυρο")
        button_box.button(QDialogButtonBox.RestoreDefaults).setText("Επαναφορά")
        
        layout.addWidget(button_box)
    
    def _load_settings(self):
        """Load settings from current_settings dict."""
        if not self.current_settings:
            return
        
        # Posts
        if "post_tall_height" in self.current_settings:
            self.post_tall_height.setValue(self.current_settings["post_tall_height"])
        if "post_low_height" in self.current_settings:
            self.post_low_height.setValue(self.current_settings["post_low_height"])
        if "post_tall_price" in self.current_settings:
            self.post_tall_price.setValue(self.current_settings["post_tall_price"])
        if "post_low_price" in self.current_settings:
            self.post_low_price.setValue(self.current_settings["post_low_price"])
        
        # Gutters
        if "gutter_side_type" in self.current_settings:
            idx = 0 if self.current_settings["gutter_side_type"] == "full" else 1
            self.gutter_side_type.setCurrentIndex(idx)
        if "gutter_3m_price" in self.current_settings:
            self.gutter_3m_price.setValue(self.current_settings["gutter_3m_price"])
        if "gutter_4m_price" in self.current_settings:
            self.gutter_4m_price.setValue(self.current_settings["gutter_4m_price"])
        
        # Koutelou
        if "koutelou_length" in self.current_settings:
            self.koutelou_length.setValue(self.current_settings["koutelou_length"])
        if "koutelou_price" in self.current_settings:
            self.koutelou_price.setValue(self.current_settings["koutelou_price"])
        
        # Plevra
        if "plevra_length" in self.current_settings:
            self.plevra_length.setValue(self.current_settings["plevra_length"])
        if "plevra_offset" in self.current_settings:
            self.plevra_offset.setValue(self.current_settings["plevra_offset"])
        if "plevra_spacing" in self.current_settings:
            self.plevra_spacing.setValue(self.current_settings["plevra_spacing"])
        if "plevra_price" in self.current_settings:
            self.plevra_price.setValue(self.current_settings["plevra_price"])
        
        # Ridge
        if "ridge_price" in self.current_settings:
            self.ridge_price.setValue(self.current_settings["ridge_price"])
        
        # Cultivation pipes
        if "cultivation_pipe_length" in self.current_settings:
            self.cultivation_pipe_length.setValue(self.current_settings["cultivation_pipe_length"])
        if "cultivation_pipe_price" in self.current_settings:
            self.cultivation_pipe_price.setValue(self.current_settings["cultivation_pipe_price"])
    
    def _apply_settings(self):
        """Apply current settings and emit signal without closing dialog."""
        settings = self.get_settings()
        self.settings_changed.emit(settings)
    
    def _restore_defaults(self):
        """Restore default values."""
        # Posts
        self.post_thickness.setCurrentIndex(0)  # 2"
        self.post_tall_height.setValue(3.0)
        self.post_low_height.setValue(2.0)
        self.post_tall_price.setValue(18.50)
        self.post_low_price.setValue(12.90)
        
        # Gutters
        self.gutter_thickness.setCurrentIndex(0)  # 2"
        self.gutter_side_type.setCurrentIndex(0)
        self.gutter_3m_price.setValue(9.80)
        self.gutter_4m_price.setValue(12.40)
        
        # Koutelou
        self.koutelou_thickness.setCurrentIndex(0)  # 1"
        self.koutelou_length.setValue(2.54)
        self.koutelou_price.setValue(8.50)
        
        # Plevra
        self.plevra_thickness.setCurrentIndex(0)  # 1"
        self.plevra_length.setValue(2.54)
        self.plevra_offset.setValue(0.5)
        self.plevra_spacing.setValue(1.0)
        self.plevra_price.setValue(6.50)
        
        # Ridge
        self.ridge_thickness.setCurrentIndex(0)  # 2"
        self.ridge_price.setValue(7.20)
        
        # Cultivation pipes
        self.cultivation_thickness.setCurrentIndex(0)  # 1"
        self.cultivation_pipe_length.setValue(5.0)
        self.cultivation_pipe_price.setValue(8.00)
    
    def get_settings(self):
        """Return current settings as dict."""
        return {
            # Posts
            "post_thickness": self.post_thickness.currentText(),
            "post_tall_height": self.post_tall_height.value(),
            "post_low_height": self.post_low_height.value(),
            "post_tall_price": self.post_tall_price.value(),
            "post_low_price": self.post_low_price.value(),
            
            # Gutters
            "gutter_thickness": self.gutter_thickness.currentText(),
            "gutter_side_type": "full" if self.gutter_side_type.currentIndex() == 0 else "half",
            "gutter_3m_price": self.gutter_3m_price.value(),
            "gutter_4m_price": self.gutter_4m_price.value(),
            
            # Koutelou
            "koutelou_thickness": self.koutelou_thickness.currentText(),
            "koutelou_length": self.koutelou_length.value(),
            "koutelou_price": self.koutelou_price.value(),
            
            # Plevra
            "plevra_thickness": self.plevra_thickness.currentText(),
            "plevra_length": self.plevra_length.value(),
            "plevra_offset": self.plevra_offset.value(),
            "plevra_spacing": self.plevra_spacing.value(),
            "plevra_price": self.plevra_price.value(),
            
            # Ridge
            "ridge_thickness": self.ridge_thickness.currentText(),
            "ridge_price": self.ridge_price.value(),
            
            # Cultivation pipes
            "cultivation_thickness": self.cultivation_thickness.currentText(),
            "cultivation_pipe_length": self.cultivation_pipe_length.value(),
            "cultivation_pipe_price": self.cultivation_pipe_price.value(),
        }
