"""Embedded default materials catalog.

Modify MATERIAL_DEFAULTS to add/update built‑in material items.
Users can provide a CSV at runtime to override prices without editing
this file. Deleting the user CSV restores these defaults automatically.
"""
from typing import Dict
from .models import MaterialItem

# List of tuples: (code, name, unit, unit_price)
MATERIAL_DEFAULTS = [
    ("post_tall",    "Κολόνα Υψηλή",       "piece", 18.50),
    ("post_low",     "Κολόνα Χαμηλή",      "piece", 12.90),
    ("ridge_cap",    "Κορφιάτης",          "piece", 7.20),
    ("gutter_3m",    "Υδρορροή 3m",        "piece", 9.80),
    ("gutter_4m",    "Υδρορροή 4m",        "piece", 12.40),
    ("gutter_piece", "Υδρορροή (κομμάτι)", "piece", 10.50),  # generic fallback
]

def default_material_catalog() -> Dict[str, MaterialItem]:
    return {
        code: MaterialItem(code=code, name=name, unit=unit, unit_price=price)
        for code, name, unit, price in MATERIAL_DEFAULTS
    }
