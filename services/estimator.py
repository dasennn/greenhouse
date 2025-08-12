from PyQt5.QtWidgets import QMainWindow, QMessageBox, QWidget, QAction, QFileDialog, QVBoxLayout
from PyQt5.QtCore import Qt

# Optional estimator import (supports either project layout)
try:
    from backend.estimator import Estimator, MaterialItem
except Exception:
    try:
        from services.estimator import Estimator, MaterialItem
    except Exception:
        Estimator = None  # type: ignore
        MaterialItem = None  # type: ignore

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1024, 768)

        # Lazy-created estimator (connected to backend/services if available)
        self.estimator = None

        # ... rest of __init__ ...

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

    def _on_perimeter_closed(self, xy):
        full, partial = self.compute_grid_coverage(xy)
        if full is None:
            # No counting available at all
            QMessageBox.information(self, "Perimeter Closed", "Perimeter closed, but no counting backend is available yet.")
            return

        # Try to compute a basic bill/geometry if an Estimator is available
        bill_lines = []
        est = self._ensure_estimator()
        if est is not None:
            try:
                # Estimator.compute_bill(xy) is called by UI/main_window.py with perimeter points.
                # Returns bill dict with geometry, grid_cells, subtotal, etc.
                bill = est.compute_bill(xy)
                geom = bill.get("geometry", {})
                area_m2 = geom.get("area_m2")
                perim_m = geom.get("perimeter_m")
                cells = bill.get("grid_cells", {})
                currency = bill.get("currency", "EUR")
                subtotal = bill.get("subtotal", 0.0)
                bill_lines.append(f"Area: {area_m2:.2f} m²")
                bill_lines.append(f"Perimeter: {perim_m:.2f} m")
                bill_lines.append(f"Complete cells: {cells.get('full', full)}")
                bill_lines.append(f"Partial cells: {cells.get('partial', partial)}")
                bill_lines.append(f"Estimated subtotal: {subtotal:.2f} {currency}")
            except Exception:
                # Fall back to simple grid summary if estimator fails
                bill_lines = []

        if not bill_lines:
            bill_lines = [
                f"Complete grid boxes: {full}",
                f"Partial grid boxes:  {partial}",
                "",
                "Grid size: 5m x 3m",
            ]

        QMessageBox.information(
            self,
            "Greenhouse Summary",
            "\n".join(bill_lines),
        )