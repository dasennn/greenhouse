from dataclasses import dataclass
from typing import List


@dataclass
class MaterialItem:
    code: str
    name: str
    unit: str = "piece"  # e.g., piece, m, kg
    unit_price: float = 0.0


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
