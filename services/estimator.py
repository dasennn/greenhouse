"""Estimator service module.

Contains the core calculation logic for computing the Bill of Materials (BOM)
given geometric estimations. This keeps all critical estimation logic in one
place and leaves services/models.py only for data models.
"""

from typing import Dict, Optional, List

from .models import MaterialItem, BillLine, BillOfMaterials


def default_material_catalog() -> Dict[str, MaterialItem]:
	"""Embedded default catalog so the app works out-of-the-box.
	Users can import a CSV to override these values at runtime.
	"""
	return {
		"post_tall": MaterialItem(code="post_tall", name="Κολόνα Υψηλή", unit="piece", unit_price=18.50),
		"post_low": MaterialItem(code="post_low", name="Κολόνα Χαμηλή", unit="piece", unit_price=12.90),
		"gutter_3m": MaterialItem(code="gutter_3m", name="Υδρορροή 3m", unit="piece", unit_price=9.80),
		"gutter_4m": MaterialItem(code="gutter_4m", name="Υδρορροή 4m", unit="piece", unit_price=12.40),
		# Generic, if grid height is not 3 or 4 exactly
		"gutter_piece": MaterialItem(code="gutter_piece", name="Υδρορροή (κομμάτι)", unit="piece", unit_price=10.50),
	}


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
		"""Build a bill of materials from geometry estimations.

		posts_est: dict from estimate_triangle_posts_3x5_with_sides (or None)
		gutters_est: dict from estimate_gutters_length (or None)
		grid_h_m: height of grid (m), used to pick gutter piece type
		"""
		lines: List[BillLine] = []
		subtotal = 0.0

		# Posts
		if posts_est:
			tall_qty = float(posts_est.get("total_tall_posts", 0) or 0)
			low_qty = float(posts_est.get("total_low_posts", 0) or 0)
			if tall_qty:
				m = self._get_material("post_tall")
				total = tall_qty * m.unit_price
				lines.append(BillLine(code=m.code, name=m.name, unit=m.unit, quantity=tall_qty, unit_price=m.unit_price, total=total))
				subtotal += total
			if low_qty:
				m = self._get_material("post_low")
				total = low_qty * m.unit_price
				lines.append(BillLine(code=m.code, name=m.name, unit=m.unit, quantity=low_qty, unit_price=m.unit_price, total=total))
				subtotal += total

		# Gutters – choose piece by grid height (3m, 4m, else generic)
		if gutters_est:
			qty = float(gutters_est.get("total_pieces", 0) or 0)
			if qty:
				code = "gutter_3m" if abs(grid_h_m - 3.0) < 1e-6 else ("gutter_4m" if abs(grid_h_m - 4.0) < 1e-6 else "gutter_piece")
				m = self._get_material(code)
				# If generic, reflect actual length in name
				name = m.name if code != "gutter_piece" else f"Gutter {grid_h_m:g}m"
				total = qty * m.unit_price
				lines.append(BillLine(code=m.code, name=name, unit=m.unit, quantity=qty, unit_price=m.unit_price, total=total))
				subtotal += total

		return BillOfMaterials(lines=lines, subtotal=subtotal, currency=self.currency)