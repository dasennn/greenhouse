"""Estimator service module.

Contains the core calculation logic for computing the Bill of Materials (BOM)
given geometric estimations. This keeps all critical estimation logic in one
place and leaves services/models.py only for data models.
"""

from typing import Dict, Optional, List

from .models import MaterialItem, BillLine, BillOfMaterials
from .material_estimator import estimate_material_quantities
from .default_materials import default_material_catalog


class Estimator:
    def __init__(self, materials: Optional[Dict[str, MaterialItem]] = None, scale_factor: float = 5.0, currency: str = "EUR"):
        # Use provided materials or fall back to defaults
        self.materials: Dict[str, MaterialItem] = materials or default_material_catalog()
        self.scale_factor = scale_factor
        self.currency = currency

    def _get_material(self, code: str) -> MaterialItem:
        mat = self.materials.get(code)
        if mat is None:
            # Fallback to generic piece with zero price
            return MaterialItem(code=code, name=code, unit="piece", unit_price=0.0)
        return mat

    def compute_bom(self, posts_est: Optional[dict], gutters_est: Optional[dict], grid_h_m: float) -> BillOfMaterials:
        """Build a bill of materials from geometric estimates.

        Flow:
        1) Use material_estimator.estimate_material_quantities to convert
           geometry outputs into {material_code: quantity}.
        2) For each entry, look up MaterialItem (name/unit/price) and create
           a BillLine with calculated total and accumulate subtotal.
        """
        quantities = estimate_material_quantities(posts_est, gutters_est, grid_h_m)

        lines: List[BillLine] = []
        subtotal = 0.0
        for code, qty in quantities.items():
            m = self._get_material(code)
            # If generic gutter piece, reflect actual length in name
            name = m.name if code != "gutter_piece" else f"Gutter {grid_h_m:g}m"
            total = float(qty) * float(m.unit_price)
            lines.append(BillLine(code=m.code, name=name, unit=m.unit, quantity=float(qty), unit_price=m.unit_price, total=total))
            subtotal += total

        return BillOfMaterials(lines=lines, subtotal=subtotal, currency=self.currency)