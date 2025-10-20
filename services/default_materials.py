"""Embedded default materials catalog.

Modify MATERIAL_DEFAULTS to add/update built‑in material items.
Users can provide a CSV at runtime to override prices without editing
this file. Deleting the user CSV restores these defaults automatically.
"""
from typing import Dict
from .models import MaterialItem

# List of tuples: (code, name, unit, unit_price, thickness, height, length)
MATERIAL_DEFAULTS = [
    ("post_tall",    "Στύλος Ψηλός",       "piece", 18.50, "2\"", "3m", "-"),
    ("post_low",     "Στύλος Χαμηλός",      "piece", 12.90, "2\"", "2m", "-"),
    ("ridge_cap",    "Κορφιάτης",          "piece", 7.20,  "1.5\"", "-", "2.54m"),
    ("gutter_3m",    "Υδρορροή 3m",        "piece", 9.80,  "2\"", "-", "3m"),
    ("gutter_4m",    "Υδρορροή 4m",        "piece", 12.40, "2\"", "-", "4m"),
    ("gutter_piece", "Υδρορροή (κομμάτι)", "piece", 10.50, "2\"", "-", "-"),  # generic fallback
    ("gutter_3m_half", "Υδρορροή 3m Μισή", "piece", 5.40,  "2\"", "-", "1.5m"),  # Μισή υδρορροή 3m
    ("gutter_4m_half", "Υδρορροή 4m Μισή", "piece", 6.80,  "2\"", "-", "2m"),  # Μισή υδρορροή 4m
    ("koutelou_pair", "Ζεύγη Κουτελού",    "piece", 8.50,  "1\"", "-", "2.54m"),  # ανά ζεύγος (2 τεμάχια)
    ("plevra",       "Πλευρά",            "piece", 6.50,  "1\"", "-", "2.54m"),  # ανά πλευρό
]

def default_material_catalog() -> Dict[str, MaterialItem]:
    return {
        code: MaterialItem(
            code=code, 
            name=name, 
            unit=unit, 
            unit_price=price,
            thickness=thickness,
            height=height,
            length=length
        )
        for code, name, unit, price, thickness, height, length in MATERIAL_DEFAULTS
    }
