from dataclasses import dataclass
from typing import List


@dataclass
class MaterialItem:
    code: str
    name: str
    unit: str = "κομμάτι"  # e.g., piece, m, kg
    unit_price: float = 0.0
    thickness: str = "-"  # Πάχος (π.χ. 2", 1.5", 1")
    height: str = "-"     # Ύψος (π.χ. 2m60, 2m00)
    length: str = "-"     # Μήκος (π.χ. 3m, 4m)


@dataclass
class BillLine:
    code: str
    name: str
    unit: str
    quantity: float
    unit_price: float
    total: float


@dataclass
class BillOfMaterials:
    lines: List[BillLine]
    subtotal: float
    currency: str = "EUR"

"""Data models only. Estimation logic lives in services/estimator.py"""

__all__ = [
    "MaterialItem",
    "BillLine",
    "BillOfMaterials",
]
