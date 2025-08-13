from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton

class ColumnHeightDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Column Heights")

        # Layout
        layout = QVBoxLayout()

        # Large Column Height
        self.large_column_label = QLabel("Large Column Height (m):")
        self.large_column_input = QLineEdit()
        layout.addWidget(self.large_column_label)
        layout.addWidget(self.large_column_input)

        # Small Column Height
        self.small_column_label = QLabel("Small Column Height (m):")
        self.small_column_input = QLineEdit()
        layout.addWidget(self.small_column_label)
        layout.addWidget(self.small_column_input)

        # Buttons
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        layout.addWidget(self.ok_button)

        self.setLayout(layout)

    def get_values(self):
        """Return the entered values as a tuple (large_column_height, small_column_height)."""
        try:
            large_height = float(self.large_column_input.text())
            small_height = float(self.small_column_input.text())
            return large_height, small_height
        except ValueError:
            return None, None
