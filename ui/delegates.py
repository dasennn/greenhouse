"""UI delegates for custom cell editing behavior."""

from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit
from PySide6.QtGui import QDoubleValidator


class PriceOnlyDelegate(QStyledItemDelegate):
    """Delegate that allows editing only for the Unit Price column (index 3)."""
    
    def createEditor(self, parent, option, index):
        if index.column() == 3:
            editor = QLineEdit(parent)
            editor.setValidator(QDoubleValidator(0.0, 1e12, 4, parent))
            return editor
        return None
